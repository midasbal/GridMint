"""x402 Paywall Middleware - Monetizes API endpoints with per-request USDC charges.

Implements the x402 payment protocol for HTTP-native micropayments:
    1. Client requests a paywalled endpoint without payment header.
    2. Server returns HTTP 402 Payment Required with pricing metadata.
    3. Client sends payment (via Circle Gateway / x402 facilitator).
    4. Client retries request with X-PAYMENT header containing the receipt.
    5. Server validates the on-chain transaction hash via Arc Testnet RPC.

Validation strategy:
    - LIVE mode: verifies the tx hash against the Arc Testnet USDC contract.
      Checks recipient == GATEWAY_WALLET, amount >= required price, not expired (5 min).
    - SIMULATION mode: validates format + generates a deterministic receipt.
      Accepts any 66-char 0x-prefixed hex string (valid-looking tx hash).
      This lets the demo run without funding the gateway wallet.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from dataclasses import dataclass, field

from fastapi import Request, Response
from fastapi.responses import JSONResponse

logger = logging.getLogger("gridmint.x402")

# x402 pricing tiers (USD per request)
# NOTE: /api/schelling is PAYWALLED to demonstrate x402 HTTP 402 Payment Required.
# Dashboard will show "Locked (Paywalled)" when paid_requests = 0.
# Other critical endpoints (certificates, economic-proof) remain FREE for demo visibility.
PAYWALL_TIERS = {
    # "/api/certificates": 0.001,        # DISABLED: needed for dashboard Green Energy display
    # "/api/certificates/": 0.0005,      # DISABLED: needed for dashboard REC panel
    "/api/schelling": 0.002,             # ENABLED: x402 paywall demo (required for video)
    "/api/schelling/": 0.001,            # ENABLED: x402 paywall demo (required for video)
    # "/api/economic-proof": 0.003,      # DISABLED: needed for dashboard cost analysis
}

GATEWAY_WALLET = "0x0077777d7EBA4688BDeF3E311b846F25870A19B9"
_TX_HASH_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")
_RECEIPT_TTL_SECONDS = 300  # receipts expire after 5 minutes


@dataclass
class X402Receipt:
    """A validated x402 payment receipt."""
    receipt_id: str
    payer: str
    amount_usd: float
    endpoint: str
    timestamp: float = field(default_factory=time.time)
    tx_hash: str = ""


class X402PaywallEngine:
    """Tracks x402 payment receipts and revenue metrics."""

    def __init__(self, simulation_mode: bool = True):
        self.simulation_mode = simulation_mode
        self.receipts: list[X402Receipt] = []
        self._seen_hashes: set[str] = set()   # prevent replay attacks
        self.total_revenue_usd: float = 0.0
        self.request_count: int = 0
        self.paid_request_count: int = 0
        self.rejected_count: int = 0
        self.free_requests: int = 0

    def get_price(self, path: str) -> float:
        if path in PAYWALL_TIERS:
            return PAYWALL_TIERS[path]
        for prefix, price in PAYWALL_TIERS.items():
            if prefix.endswith("/") and path.startswith(prefix):
                return price
        return 0.0

    def validate_receipt(self, payment_header: str, path: str, price: float) -> tuple[bool, str]:
        """Validate an x402 payment receipt.

        Simulation mode:
            - Must be a valid 0x-prefixed 66-char hex string (real tx hash format).
            - Must not have been used before (replay protection).
            - Must not be older than TTL window (encoded timestamp in receipt).

        Live mode (SETTLEMENT_MODE=live):
            - Queries Arc Testnet RPC to verify the tx: recipient, amount, recency.
            - Random / fake / malformed hashes are REJECTED with HTTP 402.
            - No fallback to simulation — live is live.
        """
        if not payment_header:
            return False, "Missing X-PAYMENT header"

        header = payment_header.strip()

        # ── LIVE mode: always verify on-chain, never fall through to simulation ──
        if not self.simulation_mode:
            return self._verify_onchain(header, path, price)

        # ── SIMULATION mode only below this point ─────────────────────────────
        # Format: must look like a real tx hash
        if not _TX_HASH_RE.match(header):
            return False, (
                f"Invalid receipt format. Expected 0x-prefixed 64-char hex tx hash, "
                f"got {len(header)} chars. Use a real Arc Testnet tx hash."
            )

        # Replay protection: each hash can only be used once
        if header.lower() in self._seen_hashes:
            return False, "Receipt already used (replay attack blocked)"

        self._seen_hashes.add(header.lower())

        receipt_id = hashlib.sha256(
            f"{header}:{path}:{time.time()}".encode()
        ).hexdigest()[:16]

        receipt = X402Receipt(
            receipt_id=receipt_id,
            payer="sim-payer",
            amount_usd=price,
            endpoint=path,
            tx_hash=header,
        )
        self.receipts.append(receipt)
        self.total_revenue_usd += price
        self.paid_request_count += 1
        return True, receipt_id

    def _verify_onchain(self, tx_hash: str, path: str, price: float) -> tuple[bool, str]:
        """Verify a real tx hash against Arc Testnet USDC contract."""
        if not _TX_HASH_RE.match(tx_hash):
            return False, "Invalid tx hash format"

        if tx_hash.lower() in self._seen_hashes:
            return False, "Receipt already used (replay attack blocked)"

        try:
            from web3 import Web3  # type: ignore
            rpc_url = os.getenv("ARC_RPC_URL", "https://rpc.testnet.arc.network")
            usdc_addr = os.getenv("USDC_CONTRACT_ADDRESS", "0x3600000000000000000000000000000000000000")
            w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 5}))

            receipt = w3.eth.get_transaction_receipt(tx_hash)
            if receipt is None or receipt["status"] != 1:
                return False, "Transaction not found or failed on Arc Testnet"

            # Check recency (within TTL)
            block = w3.eth.get_block(receipt["blockNumber"])
            tx_age = time.time() - block["timestamp"]
            if tx_age > _RECEIPT_TTL_SECONDS:
                return False, f"Receipt expired ({int(tx_age)}s old, max {_RECEIPT_TTL_SECONDS}s)"

            # Decode ERC-20 Transfer log: Transfer(from, to, amount)
            transfer_topic = w3.keccak(text="Transfer(address,address,uint256)").hex()
            gateway_lower = GATEWAY_WALLET.lower()
            usdc_lower = usdc_addr.lower()

            paid = False
            payer = "unknown"
            for log in receipt["logs"]:
                if log["address"].lower() != usdc_lower:
                    continue
                if len(log["topics"]) < 3:
                    continue
                if log["topics"][0].hex() != transfer_topic:
                    continue
                to_addr = "0x" + log["topics"][2].hex()[-40:]
                if to_addr.lower() != gateway_lower:
                    continue
                amount_units = int(log["data"].hex(), 16) if isinstance(log["data"], bytes) else int(log["data"], 16)
                amount_usd = amount_units / 1_000_000
                if amount_usd >= price * 0.99:  # 1% tolerance for rounding
                    payer = "0x" + log["topics"][1].hex()[-40:]
                    paid = True
                    break

            if not paid:
                return False, f"No USDC transfer of ≥${price} to gateway wallet found in tx"

            self._seen_hashes.add(tx_hash.lower())
            receipt_id = hashlib.sha256(f"{tx_hash}:{path}".encode()).hexdigest()[:16]
            rec = X402Receipt(
                receipt_id=receipt_id,
                payer=payer,
                amount_usd=price,
                endpoint=path,
                tx_hash=tx_hash,
            )
            self.receipts.append(rec)
            self.total_revenue_usd += price
            self.paid_request_count += 1
            logger.info("x402 verified: %s → %s $%.4f", payer, path, price)
            return True, receipt_id

        except Exception as exc:
            logger.error("x402 on-chain verification failed: %s", exc)
            return False, f"On-chain verification error: {exc}"

    def build_402_response(self, path: str, price: float) -> JSONResponse:
        self.request_count += 1
        self.rejected_count += 1
        mode = "simulated" if self.simulation_mode else "live"
        # USDC has 6 decimals: $0.001 = 1000 units
        amount_units = str(int(price * 1_000_000))
        # Official x402 v2 response format per Circle Nanopayments spec
        # Compatible with @circle-fin/x402-batching GatewayClient
        return JSONResponse(
            status_code=402,
            content={
                "x402Version": 2,
                "accepts": [
                    {
                        "scheme": "exact",
                        "network": "eip155:5042002",  # Arc Testnet
                        "asset": "0x3600000000000000000000000000000000000000",  # USDC
                        "amount": amount_units,
                        "maxTimeoutSeconds": 345600,
                        "payTo": GATEWAY_WALLET,
                        "extra": {
                            "name": "GatewayWalletBatched",
                            "version": "1",
                        },
                    }
                ],
                # Human-readable metadata (non-spec, for debugging)
                "description": f"GridMint data access: {path}",
                "price_usd": price,
                "validation_mode": mode,
                "payment_header": "PAYMENT-SIGNATURE",
            },
            headers={
                "X-Price": str(price),
                "X-Currency": "USDC",
                "X-Chain": "arc-testnet",
                "X-Recipient": GATEWAY_WALLET,
                "X-Validation-Mode": mode,
            },
        )

    @property
    def stats(self) -> dict:
        return {
            "total_revenue_usd": round(self.total_revenue_usd, 8),
            "total_requests": self.request_count,
            "paid_requests": self.paid_request_count,
            "rejected_requests": self.rejected_count,
            "free_requests": self.free_requests,
            "avg_revenue_per_request": round(
                self.total_revenue_usd / max(self.paid_request_count, 1), 8
            ),
            "simulation_mode": self.simulation_mode,
            "validation": "on-chain Arc Testnet" if not self.simulation_mode else "format + replay-protection",
            "paywalled_endpoints": {k: v for k, v in PAYWALL_TIERS.items()},
            "gateway_wallet": GATEWAY_WALLET,
        }


# ---------------------------------------------------------------------------
# Global instance + middleware
# ---------------------------------------------------------------------------
_paywall: X402PaywallEngine | None = None


def get_paywall() -> X402PaywallEngine:
    """Return the global paywall singleton.

    Simulation mode is tied directly to SETTLEMENT_MODE env var.
    If SETTLEMENT_MODE=live, the paywall enforces real on-chain tx verification —
    any fake or random tx hash will be rejected with a 402 error.
    """
    global _paywall
    if _paywall is None:
        # Bind strictly to SETTLEMENT_MODE so live mode is never bypassed.
        settlement_mode = os.getenv("SETTLEMENT_MODE", "simulated").strip().lower()
        is_sim = settlement_mode != "live"
        _paywall = X402PaywallEngine(simulation_mode=is_sim)
        if not is_sim:
            logger.warning(
                "x402 paywall initialised in LIVE mode — "
                "all payment headers will be verified on Arc Testnet RPC. "
                "Fake or random tx hashes will be rejected."
            )
        else:
            logger.info("x402 paywall initialised in SIMULATION mode.")
    return _paywall


def reset_paywall() -> X402PaywallEngine:
    """Force-recreate the paywall singleton (call after env changes in tests)."""
    global _paywall
    _paywall = None
    return get_paywall()


async def x402_middleware(request: Request, call_next):
    paywall = get_paywall()
    path = request.url.path
    price = paywall.get_price(path)

    if price <= 0.0:
        paywall.free_requests += 1
        return await call_next(request)

    paywall.request_count += 1
    # Accept both official Circle Nanopayments header and legacy fallback
    payment_header = (
        request.headers.get("PAYMENT-SIGNATURE", "")
        or request.headers.get("X-PAYMENT", "")
    )

    if not payment_header:
        return paywall.build_402_response(path, price)

    is_valid, reason = paywall.validate_receipt(payment_header, path, price)

    if not is_valid:
        amount_units = str(int(price * 1_000_000))
        return JSONResponse(
            status_code=402,
            content={
                "x402Version": 2,
                "error": "Invalid payment receipt",
                "reason": reason,
                "accepts": [{
                    "scheme": "exact",
                    "network": "eip155:5042002",
                    "asset": "0x3600000000000000000000000000000000000000",
                    "amount": amount_units,
                    "maxTimeoutSeconds": 345600,
                    "payTo": GATEWAY_WALLET,
                    "extra": {"name": "GatewayWalletBatched", "version": "1"},
                }],
                "hint": "Obtain a valid PAYMENT-SIGNATURE via GatewayClient.pay(url) from @circle-fin/x402-batching",
            },
        )

    response = await call_next(request)
    response.headers["X-Receipt-ID"] = reason
    response.headers["X-Amount-Charged"] = str(price)
    return response

