/**
 * GridMint — Circle Nanopayments Buyer Demo
 *
 * Demonstrates the full Circle Gateway x402 payment flow:
 *   1. Initialize GatewayClient on Arc Testnet
 *   2. Check / deposit USDC into Gateway (one-time onchain tx)
 *   3. Pay for premium GridMint endpoints gaslessly via EIP-3009
 *   4. Print balances before/after
 *
 * Usage:
 *   PRIVATE_KEY=0x<your_key> npx tsx buyer-demo.ts
 *
 * The buyer wallet must have testnet USDC from faucet.circle.com
 */

import { GatewayClient } from "@circle-fin/x402-batching/client";
import * as dotenv from "dotenv";
import { resolve } from "path";

dotenv.config({ path: resolve(process.cwd(), "../.env") });

const GATEWAY_SERVER = process.env.NANOPAYMENTS_URL ?? "http://localhost:4402";
const PRIVATE_KEY = (process.env.CONSUMER_1_PRIVATE_KEY
  ? `0x${process.env.CONSUMER_1_PRIVATE_KEY}`
  : process.env.PRIVATE_KEY) as `0x${string}`;

if (!PRIVATE_KEY || PRIVATE_KEY === "0x") {
  console.error("✗ Set CONSUMER_1_PRIVATE_KEY or PRIVATE_KEY in .env");
  process.exit(1);
}

async function main() {
  console.log("═══════════════════════════════════════════════════════");
  console.log(" GridMint — Circle Nanopayments Buyer Demo");
  console.log(" Network:  Arc Testnet (eip155:5042002)");
  console.log(" Protocol: x402 + Circle Gateway EIP-3009");
  console.log("═══════════════════════════════════════════════════════\n");

  // Initialize Circle Gateway client on Arc Testnet
  const client = new GatewayClient({
    chain: "arcTestnet",
    privateKey: PRIVATE_KEY,
  });

  // ── Step 1: Check balances ──────────────────────────────────────────────
  const balances = await client.getBalances();
  console.log("Initial balances:");
  console.log(`  Wallet USDC:          ${balances.wallet.formatted}`);
  console.log(`  Gateway available:    ${balances.gateway.formattedAvailable}`);
  console.log(`  Gateway withdrawing:  ${balances.gateway.formattedWithdrawing}\n`);

  // ── Step 2: Deposit if needed ───────────────────────────────────────────
  // Minimum $0.01 USDC in Gateway to cover a few nanopayments
  const MIN_GATEWAY_BALANCE = 10_000n; // 0.01 USDC in 6-decimal units
  if (balances.gateway.available < MIN_GATEWAY_BALANCE) {
    console.log("Gateway balance too low. Depositing 0.1 USDC...");
    const deposit = await client.deposit("0.1");
    console.log(`✓ Deposit tx: https://testnet.arcscan.app/tx/${deposit.depositTxHash}\n`);
  } else {
    console.log(`✓ Gateway balance sufficient (${balances.gateway.formattedAvailable} USDC)\n`);
  }

  // ── Step 3: Pay for premium endpoints ──────────────────────────────────
  const endpoints = [
    { path: "/api/certificates",   price: "$0.001", name: "Energy Certificates" },
    { path: "/api/schelling",      price: "$0.002", name: "Schelling Coordination Data" },
    { path: "/api/economic-proof", price: "$0.003", name: "Full Economic Proof" },
  ];

  for (const ep of endpoints) {
    const url = `${GATEWAY_SERVER}${ep.path}`;
    console.log(`─── Paying for ${ep.name} (${ep.price} USDC) ───`);
    console.log(`    URL: ${url}`);

    // Check if this endpoint supports Gateway batching
    const support = await client.supports(url);
    if (!support.supported) {
      console.log(`    ✗ Endpoint does not support Circle Gateway payments\n`);
      continue;
    }

    try {
      const { data, status } = await client.pay(url);
      console.log(`    ✓ Payment accepted — HTTP ${status}`);
      console.log(`    ✓ Data keys: ${Object.keys(data as object).join(", ")}\n`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      console.log(`    ✗ Payment failed: ${msg}\n`);
    }
  }

  // ── Step 4: Final balances ──────────────────────────────────────────────
  const updated = await client.getBalances();
  console.log("Final balances:");
  console.log(`  Wallet USDC:          ${updated.wallet.formatted}`);
  console.log(`  Gateway available:    ${updated.gateway.formattedAvailable}`);

  const spent = balances.gateway.available - updated.gateway.available;
  const spentFormatted = (Number(spent) / 1_000_000).toFixed(6);
  console.log(`\n  Total spent on nanopayments: $${spentFormatted} USDC`);
  console.log("  (gasless — no gas fees paid)");
  console.log("\n═══════════════════════════════════════════════════════");
  console.log(" Circle Nanopayments demo complete.");
  console.log("═══════════════════════════════════════════════════════");
}

main().catch((err) => {
  console.error("Fatal:", err);
  process.exit(1);
});
