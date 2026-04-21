/**
 * GridMint — Circle Nanopayments Gateway Server
 *
 * This Express server implements Circle's official x402 Nanopayments protocol
 * using the @circle-fin/x402-batching SDK. It acts as an authenticated proxy
 * in front of the FastAPI backend (port 8000), gating premium endpoints behind
 * real USDC gasless payments via Circle Gateway batched settlement.
 *
 * Architecture:
 *   Browser/Agent → :4402 (this server, Circle Nanopayments middleware)
 *                       ↓ payment verified
 *                   → :8000 (FastAPI, raw data endpoints)
 *
 * Payment flow (Circle Nanopayments / x402):
 *   1. Client GETs /api/economic-proof
 *   2. Server returns 402 with `accepts` array (EIP-3009, GatewayWalletBatched scheme)
 *   3. Client (GatewayClient) signs EIP-3009 TransferWithAuthorization offchain
 *   4. Client retries with PAYMENT-SIGNATURE header (base64 encoded payload)
 *   5. Circle Gateway BatchFacilitatorClient verifies + batches settlement
 *   6. Resource served with PAYMENT-RESPONSE header
 *
 * Seller address = GridMint gateway wallet (receives all nanopayment revenue)
 * Network: Arc Testnet (eip155:5042002) — supported by Circle Gateway
 */

import express from "express";
import { createGatewayMiddleware } from "@circle-fin/x402-batching/server";
import { createProxyMiddleware } from "http-proxy-middleware";
import * as dotenv from "dotenv";
import { readFileSync } from "fs";
import { resolve } from "path";

// Load .env from gridmint root
dotenv.config({ path: resolve(process.cwd(), "../.env") });

const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://localhost:8000";
const SELLER_ADDRESS =
  (process.env.GATEWAY_WALLET_ADDRESS as `0x${string}`) ??
  "0x0077777d7EBA4688BDeF3E311b846F25870A19B9";
const PORT = parseInt(process.env.NANOPAYMENTS_PORT ?? "4402");

// ---------------------------------------------------------------------------
// Circle Gateway Nanopayments middleware — Arc Testnet only
// ---------------------------------------------------------------------------
const gateway = createGatewayMiddleware({
  sellerAddress: SELLER_ADDRESS,
  networks: ["eip155:5042002"], // Arc Testnet
});

const app = express();
app.use(express.json());

// In-memory store for pending settlements
const pendingSettlements = new Map<string, {
  trade_id: string;
  buyer_id?: string;
  seller_id?: string;
  amount_usd: number;
  amount_str: string;
  seller_address: string;
}>();

// ---------------------------------------------------------------------------
// Health + info (free, no payment required)
// ---------------------------------------------------------------------------
app.get("/nanopayments/health", (_req, res) => {
  res.json({
    status: "ok",
    server: "GridMint Circle Nanopayments Gateway",
    protocol: "x402 + Circle Gateway batched settlement",
    seller: SELLER_ADDRESS,
    network: "Arc Testnet (eip155:5042002)",
    sdk: "@circle-fin/x402-batching",
    upstream: FASTAPI_URL,
    paywalled_endpoints: {
      "/api/economic-proof": "$0.003 USDC",
      "/api/certificates": "$0.001 USDC",
      "/api/schelling": "$0.002 USDC",
    },
    agent_settlement: {
      endpoint: "POST /nanopayments/agent-settle",
      description: "Route agent-to-agent energy trades through Circle Gateway (EIP-3009 gasless)",
      required_fields: ["buyer_private_key", "seller_address", "amount_usd", "trade_id"],
    },
    payment_instructions: {
      step1: "Deposit USDC into Circle Gateway: GatewayClient({ chain: 'arcTestnet', privateKey }).deposit('1')",
      step2: "Call GatewayClient.pay(url) — signs EIP-3009 offchain, zero gas",
      step3: "Gateway batches your authorization with others and settles onchain",
      docs: "https://developers.circle.com/gateway/nanopayments/quickstarts/buyer",
    },
  });
});

// ---------------------------------------------------------------------------
// Agent-to-Agent Settlement via Circle Gateway (the core hackathon requirement)
// POST /nanopayments/agent-settle
// Called by GatewaySettler in payment_engine.py for each agent trade.
//
// Flow:
//   1. Python (GatewaySettler) posts trade details + buyer private key
//   2. This endpoint creates a GatewayClient for the buyer
//   3. Ensures buyer has a Gateway deposit (auto-deposits if needed)
//   4. Calls client.pay() to sign EIP-3009 TransferWithAuthorization offchain
//   5. Circle Gateway batches + settles on Arc Testnet — fully gasless
//   6. Returns tx hash (from batch settlement) to Python
// ---------------------------------------------------------------------------
import { GatewayClient } from "@circle-fin/x402-batching/client";

// In-memory deposit cache: private_key_hash → deposited
const depositedKeys = new Set<string>();

app.post("/nanopayments/agent-settle", async (req, res) => {
  const {
    buyer_private_key,
    seller_address,
    amount_usd,
    trade_id,
    buyer_id,
    seller_id,
  } = req.body as {
    buyer_private_key: string;
    seller_address: string;
    amount_usd: number;
    trade_id: string;
    buyer_id?: string;
    seller_id?: string;
  };

  if (!buyer_private_key || !seller_address || !amount_usd || !trade_id) {
    res.status(400).json({
      error: "Missing required fields: buyer_private_key, seller_address, amount_usd, trade_id",
    });
    return;
  }

  // Normalize private key
  const privateKey = (
    buyer_private_key.startsWith("0x") ? buyer_private_key : `0x${buyer_private_key}`
  ) as `0x${string}`;

  // Key fingerprint (first 10 chars) for logging only — never log full key
  const keyFingerprint = privateKey.slice(0, 12) + "...";

  try {
    const client = new GatewayClient({
      chain: "arcTestnet",
      privateKey,
    });

    // One-time deposit: ensure buyer has USDC in Gateway (~$0.10 for ~100 trades)
    const cacheKey = privateKey.slice(2, 14); // short fingerprint
    if (!depositedKeys.has(cacheKey)) {
      const balances = await client.getBalances();
      const MIN_BALANCE = 10_000n; // 0.01 USDC
      if (balances.gateway.available < MIN_BALANCE) {
        console.log(`[agent-settle] Auto-depositing 0.10 USDC for ${buyer_id ?? keyFingerprint}`);
        try {
          const deposit = await client.deposit("0.10");
          console.log(`[agent-settle] Deposit tx: ${deposit.depositTxHash}`);
          depositedKeys.add(cacheKey);
        } catch (depositErr) {
          // Insufficient wallet balance — fall back gracefully
          console.warn(`[agent-settle] Auto-deposit failed: ${depositErr}. Trade ${trade_id} will use direct ERC-20.`);
          res.status(402).json({
            success: false,
            error: "gateway_deposit_required",
            message: `Buyer ${buyer_id} needs USDC in Circle Gateway. Deposit from faucet.circle.com first.`,
            fallback: "direct_erc20",
            trade_id,
          });
          return;
        }
      } else {
        depositedKeys.add(cacheKey);
      }
    }

    // Build the paywalled settlement URL on this server
    // We store the settlement data and use a wildcard route
    const amountStr = `$${amount_usd.toFixed(6)}`;
    const settlementKey = Buffer.from(trade_id).toString('base64url');
    const settleUrl = `http://localhost:${PORT}/nanopayments/settle/${settlementKey}`;
    
    // Store settlement data for retrieval
    pendingSettlements.set(settlementKey, {
      trade_id,
      buyer_id,
      seller_id,
      amount_usd,
      amount_str: amountStr,
      seller_address,
    });

    // Execute the gasless payment via Circle Gateway
    const { data, status } = await client.pay(settleUrl);

    console.log(
      `[agent-settle] ✅ ${buyer_id} → ${seller_id} | $${amount_usd.toFixed(6)} USDC | HTTP ${status} | trade ${trade_id}`
    );

    res.json({
      success: true,
      trade_id,
      buyer_id,
      seller_id,
      amount_usd,
      seller_address,
      gateway_status: status,
      data,
      protocol: "circle_gateway_x402_eip3009",
      network: "arc_testnet",
      sdk: "@circle-fin/x402-batching",
    });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    console.error(`[agent-settle] ✗ trade ${trade_id}: ${msg}`);
    res.status(500).json({
      success: false,
      trade_id,
      error: msg,
      fallback: "direct_erc20",
    });
  }
});

// ---------------------------------------------------------------------------
// Settlement completion route (paywalled with Circle Gateway)
// This handles the actual payment verification after GatewayClient.pay()
// ---------------------------------------------------------------------------
app.get("/nanopayments/settle/:key", (req, res) => {
  const { key } = req.params;
  const settlement = pendingSettlements.get(key);
  
  if (!settlement) {
    res.status(404).json({ error: "Settlement not found or already completed" });
    return;
  }
  
  // Apply Gateway payment requirement
  const middleware = gateway.require(settlement.amount_str);
  middleware(req, res, () => {
    // Payment verified by Circle Gateway middleware
    // Clean up and return success
    pendingSettlements.delete(key);
    
    res.json({
      settled: true,
      trade_id: settlement.trade_id,
      buyer_id: settlement.buyer_id,
      seller_id: settlement.seller_id,
      amount_usd: settlement.amount_usd,
      seller_address: settlement.seller_address,
      protocol: "circle_gateway_x402_eip3009",
      network: "arc_testnet",
    });
  });
});

// ---------------------------------------------------------------------------
// Gateway balance info (Plan B — free, no payment)
// ---------------------------------------------------------------------------
app.get("/nanopayments/gateway-info", (_req, res) => {
  const liveProofPath = resolve(process.cwd(), "../live_proof.json");
  let liveProof: Record<string, unknown> = {};
  try {
    liveProof = JSON.parse(readFileSync(liveProofPath, "utf-8"));
  } catch {
    /* no proof file yet */
  }

  res.json({
    gateway: {
      network: "Arc Testnet",
      chain_id: 5042002,
      eip155_network_id: "eip155:5042002",
      usdc_contract: "0x3600000000000000000000000000000000000000",
      seller_address: SELLER_ADDRESS,
      arcscan: `https://testnet.arcscan.app/address/${SELLER_ADDRESS}`,
      deposit_instructions:
        "Use Circle faucet (faucet.circle.com) to fund a wallet, then call GatewayClient.deposit() on arcTestnet",
      confirmations_required: 1,
      time_to_attestation: "~0.5 seconds",
    },
    nanopayments_live_proof: {
      total_real_transactions: (liveProof as any)?.summary?.total_transactions ?? 0,
      total_volume_usdc: (liveProof as any)?.summary?.total_volume_usdc ?? 0,
      arc_savings_vs_eth: (liveProof as any)?.summary?.arc_savings_vs_eth ?? "N/A",
      generated_at: (liveProof as any)?.generated_at ?? null,
    },
  });
});

// ---------------------------------------------------------------------------
// Paywalled endpoints — Circle Nanopayments middleware applied
// ---------------------------------------------------------------------------

// /api/economic-proof — $0.003 USDC per request (EIP-3009 gasless)
app.get(
  "/api/economic-proof",
  gateway.require("$0.003"),
  createProxyMiddleware({ target: FASTAPI_URL, changeOrigin: true })
);

// /api/certificates — $0.001 USDC per request
app.get(
  "/api/certificates",
  gateway.require("$0.001"),
  createProxyMiddleware({ target: FASTAPI_URL, changeOrigin: true })
);

// /api/schelling — $0.002 USDC per request
app.get(
  "/api/schelling",
  gateway.require("$0.002"),
  createProxyMiddleware({ target: FASTAPI_URL, changeOrigin: true })
);

// ---------------------------------------------------------------------------
// All other endpoints — free proxy to FastAPI (no payment)
// ---------------------------------------------------------------------------
app.use(
  "/",
  createProxyMiddleware({
    target: FASTAPI_URL,
    changeOrigin: true,
    on: {
      error: (err, _req, res) => {
        (res as express.Response).status(502).json({
          error: "FastAPI upstream unavailable",
          detail: String(err),
          hint: "Start the backend: uvicorn engine.orchestrator:app --port 8000",
        });
      },
    },
  })
);

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------
app.listen(PORT, () => {
  console.log(`
╔══════════════════════════════════════════════════════════════╗
║  GridMint — Circle Nanopayments Gateway Server               ║
║  Port:     ${PORT}                                              ║
║  Upstream: ${FASTAPI_URL}                          ║
║  Seller:   ${SELLER_ADDRESS.slice(0, 20)}...     ║
║  Protocol: x402 + Circle Gateway (Arc Testnet)               ║
║  SDK:      @circle-fin/x402-batching                         ║
╚══════════════════════════════════════════════════════════════╝

Paywalled endpoints (Circle Nanopayments):
  GET /api/economic-proof  →  $0.003 USDC (EIP-3009, gasless)
  GET /api/certificates    →  $0.001 USDC (EIP-3009, gasless)
  GET /api/schelling       →  $0.002 USDC (EIP-3009, gasless)

Free endpoints:
  GET /nanopayments/health       → server status
  GET /nanopayments/gateway-info → Gateway deposit info + live proof stats
  All other /api/* routes        → proxied to FastAPI free of charge

Buyer quickstart:
  import { GatewayClient } from "@circle-fin/x402-batching/client";
  const client = new GatewayClient({ chain: "arcTestnet", privateKey: "0x..." });
  await client.deposit("1"); // one-time onchain deposit
  const { data } = await client.pay("http://localhost:${PORT}/api/economic-proof");
  `);
});
