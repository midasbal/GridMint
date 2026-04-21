"""Retroactive Energy Futures via Commit-Reveal Protocol.

Agents can trade energy that hasn't been produced yet using a two-phase
cryptographic commit-reveal scheme with USDC staking and slashing.

Protocol:
    Phase 1 - COMMIT (tick N):
        - Producer commits hash(predicted_kwh || nonce) + USDC deposit
        - Consumer commits hash(predicted_demand || nonce) + USDC deposit
        - Commitments are binding; hash prevents front-running

    Phase 2 - REVEAL (tick N + delivery_window):
        - Both parties reveal their values and nonces
        - Engine verifies hash(revealed_value || nonce) == commitment
        - Compare actual delivery vs commitment:
            * Delivered >= committed: producer earns futures premium
            * Under-delivered: deposit slashed proportionally
            * Over-delivered: excess sold at spot (no penalty)

Pricing:
    futures_price = spot_price * (1 + spread)
    spread is forecast by Gemini Brain based on:
        - Historical delivery accuracy of the producer
        - Time-of-day solar prediction confidence
        - Recent price volatility

Slashing formula:
    slash_fraction = min(1.0, (committed - delivered) / committed)
    slash_amount = deposit * slash_fraction
    Slashed USDC is redistributed to the buyer as compensation.

This creates a derivatives market on top of the spot market, giving
agents skin-in-the-game for accurate forecasting.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger("gridmint.futures")


class FuturesState(str, Enum):
    """Lifecycle states of a futures contract."""
    COMMITTED = "committed"
    REVEALED = "revealed"
    SETTLED = "settled"
    EXPIRED = "expired"
    SLASHED = "slashed"


@dataclass
class FuturesCommitment:
    """A single side of a futures contract commitment."""
    agent_id: str
    role: str  # "producer" or "consumer"
    commitment_hash: str  # SHA-256 of (predicted_value || nonce)
    deposit_usd: float  # USDC staked as collateral
    commit_tick: int
    # Filled during reveal phase
    revealed_value: Optional[float] = None
    revealed_nonce: Optional[str] = None
    verified: bool = False


@dataclass
class FuturesContract:
    """A bilateral futures contract between producer and consumer."""
    contract_id: str
    producer: FuturesCommitment
    consumer: FuturesCommitment
    delivery_tick: int  # When energy must be delivered
    futures_price: float  # $/kWh agreed price (spot + spread)
    spot_price_at_commit: float  # Spot price when contract was created
    spread: float  # Premium/discount factor
    state: FuturesState = FuturesState.COMMITTED
    # Settlement results
    actual_delivery_kwh: float = 0.0
    settlement_amount_usd: float = 0.0
    slash_amount_usd: float = 0.0
    producer_pnl_usd: float = 0.0
    consumer_pnl_usd: float = 0.0
    settled_at: float = 0.0


def create_commitment_hash(predicted_value: float, nonce: str) -> str:
    """Create a cryptographic commitment hash.

    H = SHA-256(predicted_value_6dp || ":" || nonce)

    The value is rounded to 6 decimal places for deterministic hashing.
    """
    # Normalize to 6 decimal places for determinism
    normalized = f"{predicted_value:.6f}:{nonce}"
    return "0x" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def verify_commitment(
    commitment_hash: str,
    revealed_value: float,
    revealed_nonce: str,
) -> bool:
    """Verify that a revealed value matches its commitment hash."""
    expected = create_commitment_hash(revealed_value, revealed_nonce)
    return expected == commitment_hash


# Default deposit as fraction of expected trade value
DEFAULT_DEPOSIT_FRACTION = 0.10  # 10% collateral
# Delivery window: how many ticks in the future
DEFAULT_DELIVERY_WINDOW = 3
# Maximum spread (premium) for futures over spot
MAX_SPREAD = 0.50  # 50% maximum premium


class FuturesEngine:
    """Manages the energy futures market with commit-reveal settlement.

    Integrates with:
        - PaymentEngine: for deposit staking and settlement
        - GeminiBrain: for spread forecasting
        - GridEngine: for actual delivery verification

    Lifecycle per contract:
        1. commit_producer() + commit_consumer() -> creates contract
        2. After delivery_window ticks: reveal_producer() + reveal_consumer()
        3. settle_contract() -> compares actual vs committed, applies slashing
    """

    def __init__(self, delivery_window: int = DEFAULT_DELIVERY_WINDOW):
        self.delivery_window = delivery_window
        self.contracts: dict[str, FuturesContract] = {}
        self.historical: list[FuturesContract] = []
        self._contract_counter = 0
        # Track producer accuracy for Gemini spread forecasting
        self.producer_accuracy: dict[str, list[float]] = {}  # agent_id -> [accuracy_ratios]

    @property
    def stats(self) -> dict:
        """Futures market statistics for the dashboard."""
        total = len(self.historical)
        slashed = sum(1 for c in self.historical if c.state == FuturesState.SLASHED)
        total_volume = sum(c.actual_delivery_kwh for c in self.historical)
        total_deposits = sum(
            c.producer.deposit_usd + c.consumer.deposit_usd
            for c in self.historical
        )
        total_slashed = sum(c.slash_amount_usd for c in self.historical)
        avg_spread = (
            sum(c.spread for c in self.historical) / max(total, 1)
        )
        # Producer accuracy leaderboard
        leaderboard = {}
        for aid, accuracies in self.producer_accuracy.items():
            if accuracies:
                leaderboard[aid] = round(sum(accuracies) / len(accuracies), 4)

        return {
            "total_contracts": total,
            "active_contracts": len(self.contracts),
            "settled_contracts": total - len(self.contracts),
            "slashed_count": slashed,
            "total_volume_kwh": round(total_volume, 6),
            "total_deposits_usd": round(total_deposits, 8),
            "total_slashed_usd": round(total_slashed, 8),
            "avg_spread": round(avg_spread, 4),
            "delivery_window_ticks": self.delivery_window,
            "producer_accuracy": leaderboard,
        }

    def forecast_spread(
        self,
        producer_id: str,
        sim_hour: float,
        price_volatility: float,
        gemini_brain=None,
    ) -> float:
        """Forecast the futures spread (premium over spot).

        Factors:
        1. Producer track record (more accurate = lower spread)
        2. Time of day (solar more predictable at noon, less at dawn/dusk)
        3. Recent price volatility (higher vol = higher spread)
        4. Gemini override (if available)

        Returns:
            Spread as a fraction (e.g., 0.15 = 15% premium over spot).
        """
        # Base spread from producer accuracy
        accuracies = self.producer_accuracy.get(producer_id, [])
        if accuracies:
            avg_accuracy = sum(accuracies) / len(accuracies)
            # Higher accuracy -> lower spread (reward reliable producers)
            # accuracy 1.0 -> spread 0.05, accuracy 0.5 -> spread 0.30
            accuracy_spread = max(0.05, 0.35 * (1.0 - avg_accuracy))
        else:
            # No track record: default moderate spread
            accuracy_spread = 0.20

        # Time-of-day factor: solar is most predictable 10:00-14:00
        if 10.0 <= sim_hour <= 14.0:
            tod_factor = 0.8  # reduce spread at peak solar hours
        elif 6.0 <= sim_hour <= 18.0:
            tod_factor = 1.0
        else:
            tod_factor = 1.5  # nighttime solar futures are risky

        # Volatility factor
        vol_factor = 1.0 + min(price_volatility * 10, 0.5)  # cap at +50%

        spread = accuracy_spread * tod_factor * vol_factor
        return min(spread, MAX_SPREAD)

    def create_contract(
        self,
        producer_id: str,
        consumer_id: str,
        predicted_production_kwh: float,
        predicted_demand_kwh: float,
        producer_nonce: str,
        consumer_nonce: str,
        spot_price: float,
        spread: float,
        current_tick: int,
        deposit_fraction: float = DEFAULT_DEPOSIT_FRACTION,
    ) -> FuturesContract:
        """Create a new futures contract with cryptographic commitments.

        Both sides commit hashes of their predicted values. The contract
        settles at current_tick + delivery_window.
        """
        self._contract_counter += 1
        contract_id = f"futures-{self._contract_counter}"

        futures_price = round(spot_price * (1.0 + spread), 6)
        contracted_kwh = min(predicted_production_kwh, predicted_demand_kwh)
        expected_value = contracted_kwh * futures_price

        producer_deposit = round(expected_value * deposit_fraction, 8)
        consumer_deposit = round(expected_value * deposit_fraction, 8)

        producer_commitment = FuturesCommitment(
            agent_id=producer_id,
            role="producer",
            commitment_hash=create_commitment_hash(predicted_production_kwh, producer_nonce),
            deposit_usd=producer_deposit,
            commit_tick=current_tick,
        )

        consumer_commitment = FuturesCommitment(
            agent_id=consumer_id,
            role="consumer",
            commitment_hash=create_commitment_hash(predicted_demand_kwh, consumer_nonce),
            deposit_usd=consumer_deposit,
            commit_tick=current_tick,
        )

        contract = FuturesContract(
            contract_id=contract_id,
            producer=producer_commitment,
            consumer=consumer_commitment,
            delivery_tick=current_tick + self.delivery_window,
            futures_price=futures_price,
            spot_price_at_commit=spot_price,
            spread=spread,
        )

        self.contracts[contract_id] = contract

        logger.info(
            "Futures contract %s created: %s -> %s | %.4f kWh @ $%.6f/kWh "
            "(spot $%.6f + %.1f%% spread) | deposits: $%.8f + $%.8f | "
            "delivery at tick %d",
            contract_id,
            producer_id, consumer_id,
            contracted_kwh, futures_price,
            spot_price, spread * 100,
            producer_deposit, consumer_deposit,
            contract.delivery_tick,
        )

        return contract

    def reveal(
        self,
        contract_id: str,
        agent_id: str,
        revealed_value: float,
        nonce: str,
    ) -> bool:
        """Reveal a commitment value. Returns True if hash matches.

        Both producer and consumer must reveal before settlement.
        """
        contract = self.contracts.get(contract_id)
        if not contract:
            logger.warning("Reveal failed: contract %s not found", contract_id)
            return False

        # Find which side is revealing
        if contract.producer.agent_id == agent_id:
            commitment = contract.producer
        elif contract.consumer.agent_id == agent_id:
            commitment = contract.consumer
        else:
            logger.warning("Reveal failed: %s not in contract %s", agent_id, contract_id)
            return False

        # Verify cryptographic commitment
        if not verify_commitment(commitment.commitment_hash, revealed_value, nonce):
            logger.warning(
                "Reveal FAILED verification for %s in %s: "
                "hash mismatch (possible tampering)",
                agent_id, contract_id,
            )
            return False

        commitment.revealed_value = revealed_value
        commitment.revealed_nonce = nonce
        commitment.verified = True

        # Check if both sides have revealed
        if contract.producer.verified and contract.consumer.verified:
            contract.state = FuturesState.REVEALED

        logger.info(
            "Reveal verified: %s in %s | value: %.6f kWh",
            agent_id, contract_id, revealed_value,
        )
        return True

    def settle_contract(
        self,
        contract_id: str,
        actual_delivery_kwh: float,
    ) -> FuturesContract:
        """Settle a futures contract by comparing actual vs committed delivery.

        Slashing:
            If actual < committed: producer loses deposit proportionally
            slash = deposit * (committed - actual) / committed
            Consumer receives the slashed amount as compensation

        Full delivery:
            Producer earns the futures premium (spread over spot)
            Both deposits are returned
        """
        contract = self.contracts.get(contract_id)
        if not contract:
            raise ValueError(f"Contract {contract_id} not found")

        if not contract.producer.verified:
            # Producer didn't reveal -- full slash
            contract.state = FuturesState.SLASHED
            contract.slash_amount_usd = contract.producer.deposit_usd
            contract.consumer_pnl_usd = contract.producer.deposit_usd
            contract.producer_pnl_usd = -contract.producer.deposit_usd
            contract.settled_at = time.time()
            self._archive(contract)
            return contract

        committed_kwh = contract.producer.revealed_value or 0.0
        contract.actual_delivery_kwh = actual_delivery_kwh

        if committed_kwh <= 0:
            # Degenerate contract
            contract.state = FuturesState.SETTLED
            contract.settled_at = time.time()
            self._archive(contract)
            return contract

        delivery_ratio = min(actual_delivery_kwh / committed_kwh, 1.0)

        # Track producer accuracy
        if contract.producer.agent_id not in self.producer_accuracy:
            self.producer_accuracy[contract.producer.agent_id] = []
        self.producer_accuracy[contract.producer.agent_id].append(delivery_ratio)

        if delivery_ratio >= 0.95:  # 5% tolerance for measurement noise
            # Full delivery: producer earns the spread premium
            contract.state = FuturesState.SETTLED
            premium_kwh = min(committed_kwh, actual_delivery_kwh)
            premium_usd = premium_kwh * (contract.futures_price - contract.spot_price_at_commit)
            contract.settlement_amount_usd = premium_kwh * contract.futures_price
            contract.producer_pnl_usd = round(premium_usd, 8)
            contract.consumer_pnl_usd = round(-premium_usd, 8)  # Consumer pays premium but gets guaranteed energy
            contract.slash_amount_usd = 0.0
        else:
            # Under-delivery: slash producer deposit proportionally
            contract.state = FuturesState.SLASHED
            shortfall = 1.0 - delivery_ratio
            slash = round(contract.producer.deposit_usd * shortfall, 8)
            contract.slash_amount_usd = slash
            # Producer loses slash, consumer gains it as compensation
            contract.producer_pnl_usd = round(-slash, 8)
            contract.consumer_pnl_usd = round(slash, 8)
            # Settlement for what WAS delivered
            contract.settlement_amount_usd = round(
                actual_delivery_kwh * contract.futures_price, 8
            )

        contract.settled_at = time.time()

        logger.info(
            "Futures %s settled: committed %.4f kWh, delivered %.4f kWh "
            "(%.1f%%) | slash: $%.8f | producer PnL: $%.8f | consumer PnL: $%.8f",
            contract_id,
            committed_kwh, actual_delivery_kwh,
            delivery_ratio * 100,
            contract.slash_amount_usd,
            contract.producer_pnl_usd,
            contract.consumer_pnl_usd,
        )

        self._archive(contract)
        return contract

    def get_pending_deliveries(self, current_tick: int) -> list[FuturesContract]:
        """Get contracts that are due for delivery at the current tick."""
        due = []
        for contract in self.contracts.values():
            if (contract.delivery_tick <= current_tick and
                    contract.state in (FuturesState.COMMITTED, FuturesState.REVEALED)):
                due.append(contract)
        return due

    def tick_maintenance(self, current_tick: int) -> list[FuturesContract]:
        """Expire contracts that were not revealed/settled in time.

        Called each tick. Contracts more than 2x delivery_window past
        their delivery tick are expired with full producer slash.
        """
        expired = []
        expiry_limit = self.delivery_window * 2

        for cid in list(self.contracts.keys()):
            contract = self.contracts[cid]
            if current_tick > contract.delivery_tick + expiry_limit:
                contract.state = FuturesState.EXPIRED
                contract.slash_amount_usd = contract.producer.deposit_usd
                contract.producer_pnl_usd = -contract.producer.deposit_usd
                contract.consumer_pnl_usd = contract.producer.deposit_usd
                contract.settled_at = time.time()
                self._archive(contract)
                expired.append(contract)
                logger.warning(
                    "Futures %s EXPIRED: producer %s slashed $%.8f",
                    cid, contract.producer.agent_id, contract.slash_amount_usd,
                )

        return expired

    def _archive(self, contract: FuturesContract) -> None:
        """Move a contract from active to historical."""
        self.historical.append(contract)
        self.contracts.pop(contract.contract_id, None)
