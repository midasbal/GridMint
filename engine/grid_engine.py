"""Grid simulation engine - orchestrates ticks, agents, and market clearing."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable, Optional

from agents import AgentState, GridSnapshot, TradeMatch
from agents.base_agent import BaseAgent
from agents.battery_agent import BatteryAgent
from agents.solar_agent import SolarAgent
from agents.consumer_agent import ConsumerAgent
from engine import match_orders
from engine.surge_pricing import SurgePricingOracle
from engine.certificates import CertificateLedger
from engine.stress_test import StressTestRunner
from engine.schelling import SchellingEngine
from engine.gemini_brain import GeminiBrain, PriceSnapshot
from engine.coalitions import CoalitionEngine, CoalitionMember
from engine.futures import FuturesEngine, create_commitment_hash

logger = logging.getLogger("gridmint.engine")

# 1 real second = SPEED_MULTIPLIER simulated seconds
# At 360x, a 3-second tick = 18 simulated minutes. Full 24h day in 4 real minutes.
DEFAULT_SPEED_MULTIPLIER = 360
DEFAULT_TICK_INTERVAL = 3.0  # seconds between ticks


class GridEngine:
    """Core simulation loop for the GridMint micro-energy grid.

    Responsibilities:
    - Advance simulated time each tick
    - Collect offers/demands from all agents
    - Run merit-order matching
    - Dispatch matched trades to the payment engine callback
    - Update battery agents with clearing price
    - Emit GridSnapshot for dashboard consumption
    """

    def __init__(
        self,
        agents: list[BaseAgent],
        tick_interval: float = DEFAULT_TICK_INTERVAL,
        speed_multiplier: float = DEFAULT_SPEED_MULTIPLIER,
        start_hour: float = 5.0,
        on_snapshot: Optional[Callable[[GridSnapshot], None]] = None,
        on_trade: Optional[Callable[[TradeMatch], None]] = None,
    ):
        self.agents = {a.agent_id: a for a in agents}
        self.tick_interval = tick_interval
        self.speed_multiplier = speed_multiplier
        self.sim_hour = start_hour
        self.tick = 0
        self.running = False

        # Callbacks
        self._on_snapshot = on_snapshot
        self._on_trade = on_trade

        # Cumulative stats
        self.total_tx_count = 0
        self.total_usd_settled = 0.0
        self.clearing_price = 0.0

        # History for dashboard
        self.snapshots: list[GridSnapshot] = []

        # Phase 2.5 modules
        self.oracle = SurgePricingOracle()
        self.certificates = CertificateLedger()
        self.stress = StressTestRunner()
        self.schelling = SchellingEngine(learning_rate=0.5)
        self.gemini = GeminiBrain()
        self.coalitions = CoalitionEngine()
        self.futures = FuturesEngine(delivery_window=3)

        # Attach oracle and Gemini to all agents
        for a in self.agents.values():
            if hasattr(a, "set_oracle"):
                a.set_oracle(self.oracle)
            if hasattr(a, "set_gemini"):
                a.set_gemini(self.gemini)
            if hasattr(a, "set_schelling"):
                a.set_schelling(self.schelling)

        # Register agents with Schelling engine for MWU learning
        for a in self.agents.values():
            if a.agent_type.value == "solar":
                self.schelling.register_agent(a.agent_id, "seller")
            elif a.agent_type.value == "consumer":
                self.schelling.register_agent(a.agent_id, "buyer")
            elif a.agent_type.value == "battery":
                # Battery is both buyer and seller — register as seller
                # (buy decisions handled separately via oracle EWMA)
                self.schelling.register_agent(a.agent_id, "seller")

        # Set tick duration on all agents for kW→kWh conversion
        # Use actual sim advance, but floor at a reasonable minimum for tests
        tick_hours = self.sim_time_advance_per_tick
        if tick_hours < 0.001:
            # Fallback for tests with tick_interval=0: assume 0.3h (18 min)
            tick_hours = (DEFAULT_TICK_INTERVAL * DEFAULT_SPEED_MULTIPLIER) / 3600.0
        for a in self.agents.values():
            a.tick_duration_hours = tick_hours

    @property
    def sim_time_advance_per_tick(self) -> float:
        """How many simulated hours pass per tick."""
        return (self.tick_interval * self.speed_multiplier) / 3600.0

    def _collect_offers_and_demands(self):
        offers = []
        demands = []
        for agent in self.agents.values():
            offer = agent.get_offer(self.tick, self.sim_hour)
            if offer:
                offers.append(offer)
            demand = agent.get_demand(self.tick, self.sim_hour)
            if demand:
                demands.append(demand)
        return offers, demands

    def _apply_trades(self, matches: list[TradeMatch]) -> None:
        """Update agent state after matched trades."""
        for match in matches:
            seller = self.agents[match.seller_id]
            buyer = self.agents[match.buyer_id]

            seller.record_sale(match.amount_kwh, match.total_usd)
            buyer.record_purchase(match.amount_kwh, match.total_usd)

            # Battery-specific state updates
            if isinstance(seller, BatteryAgent):
                seller.discharge(match.amount_kwh)
            if isinstance(buyer, BatteryAgent):
                buyer.charge(match.amount_kwh, match.price_usd_per_kwh)

            # Mint green certificate if seller is solar
            seller_type = seller.agent_type.value
            self.certificates.record_trade(match, self.sim_hour, seller_type)

            self.total_tx_count += 1
            self.total_usd_settled += match.total_usd

            if self._on_trade:
                self._on_trade(match)

    def _update_batteries(self, clearing_price: float) -> None:
        """Feed clearing price to battery agents for next-tick decision."""
        for agent in self.agents.values():
            if isinstance(agent, BatteryAgent):
                agent.update_clearing_price(clearing_price)

    def _build_snapshot(self, offers, demands, matches) -> GridSnapshot:
        agent_states = [
            a.get_state(self.tick, self.sim_hour)
            for a in self.agents.values()
        ]
        return GridSnapshot(
            tick=self.tick,
            sim_hour=round(self.sim_hour % 24.0, 2),
            agents=agent_states,
            offers=offers,
            demands=demands,
            matches=matches,
            clearing_price_usd=self.clearing_price,
            total_tx_count=self.total_tx_count,
            total_usd_settled=round(self.total_usd_settled, 8),
        )

    def step(self) -> GridSnapshot:
        """Execute a single simulation tick. Returns the snapshot."""
        self.tick += 1
        self.sim_hour = (self.sim_hour + self.sim_time_advance_per_tick) % 24.0

        # 0. Apply stress test effects (if active)
        stress_event = self.stress.apply_tick(self.agents, self.tick)

        # 1. Collect offers and demands
        # NOTE: Oracle conditions are intentionally 1-tick stale here.
        # Agents price based on PREVIOUS tick's supply/demand — this models
        # real market information asymmetry (agents cannot observe the future).
        offers, demands = self._collect_offers_and_demands()

        # 2. Merit-order matching
        matches, clearing_price = match_orders(offers, demands, self.tick)
        self.clearing_price = clearing_price

        # 3. Update surge pricing oracle with current conditions
        total_supply = sum(o.amount_kwh for o in offers)
        total_demand = sum(d.amount_kwh for d in demands)
        self.oracle.update_conditions(total_supply, total_demand, clearing_price, self.sim_hour)

        # 3b. Feed tick data to Gemini brain for context
        self.gemini.record_tick(PriceSnapshot(
            tick=self.tick,
            sim_hour=round(self.sim_hour % 24.0, 2),
            clearing_price=clearing_price,
            supply_kwh=total_supply,
            demand_kwh=total_demand,
        ))

        # 4. Apply trades to agent state (+ mint certificates)
        self._apply_trades(matches)

        # 5. Update battery agents with clearing price for next tick
        self._update_batteries(clearing_price)

        # 6. Update Schelling MWU weights from this tick's outcomes
        matched_agents = set()
        matched_kwh: dict[str, float] = {}
        for m in matches:
            matched_agents.add(m.seller_id)
            matched_agents.add(m.buyer_id)
            matched_kwh[m.seller_id] = matched_kwh.get(m.seller_id, 0.0) + m.amount_kwh
            matched_kwh[m.buyer_id] = matched_kwh.get(m.buyer_id, 0.0) + m.amount_kwh

        for aid in self.schelling.agents:
            self.schelling.update(
                aid,
                was_matched=(aid in matched_agents),
                clearing_price=clearing_price if clearing_price > 0 else self.oracle.price_ewma,
                trade_kwh=matched_kwh.get(aid, 0.0),
            )

        # 6b. Coalition formation: pair solar + battery into virtual power plants
        formed_coalitions = self.coalitions.form_coalitions(
            self.agents, self.tick, self.sim_hour, clearing_price if clearing_price > 0 else self.oracle.price_ewma,
        )

        # 6c. Futures: auto-create contracts for solar agents with good track records
        if clearing_price > 0 and self.tick > 5:
            self._auto_create_futures(clearing_price)

        # 6d. Futures: settle any contracts due this tick
        self._settle_due_futures()

        # 6e. Futures: expire stale contracts
        self.futures.tick_maintenance(self.tick)

        # 7. Build snapshot
        snapshot = self._build_snapshot(offers, demands, matches)
        self.snapshots.append(snapshot)

        if self._on_snapshot:
            self._on_snapshot(snapshot)

        logger.info(
            "Tick %d | Hour %.1f | Offers %d | Demands %d | Matches %d | "
            "Clearing $%.4f | Total TX %d | Total USD $%.6f",
            self.tick,
            snapshot.sim_hour,
            len(offers),
            len(demands),
            len(matches),
            clearing_price,
            self.total_tx_count,
            self.total_usd_settled,
        )

        return snapshot

    async def run(self, max_ticks: Optional[int] = None) -> None:
        """Run the simulation loop asynchronously."""
        self.running = True
        logger.info("GridMint engine started. Tick interval: %.1fs, Speed: %.0fx",
                     self.tick_interval, self.speed_multiplier)

        tick_count = 0
        while self.running:
            self.step()
            tick_count += 1
            if max_ticks and tick_count >= max_ticks:
                logger.info("Reached max ticks (%d). Stopping.", max_ticks)
                self.running = False
                break
            await asyncio.sleep(self.tick_interval)

    def stop(self) -> None:
        self.running = False

    def toggle_agent(self, agent_id: str) -> AgentState:
        """Toggle an agent online/offline (for live fault injection demo)."""
        agent = self.agents[agent_id]
        if agent.status.value == "online":
            agent.set_offline()
        else:
            agent.set_online()
        return agent.get_state(self.tick, self.sim_hour)

    # ------------------------------------------------------------------
    # Futures helpers
    # ------------------------------------------------------------------
    def _auto_create_futures(self, clearing_price: float) -> None:
        """Automatically create futures contracts for eligible solar agents.

        A solar agent is eligible if it produced energy this tick (has supply).
        Paired with a random consumer that had demand this tick.
        """
        import hashlib as _hl
        import random

        # Only create every 5th tick to avoid flooding
        if self.tick % 5 != 0:
            return

        solar_ids = [aid for aid, a in self.agents.items()
                     if a.agent_type.value == "solar" and a.status.value == "online"]
        consumer_ids = [aid for aid, a in self.agents.items()
                        if a.agent_type.value == "consumer" and a.status.value == "online"]

        if not solar_ids or not consumer_ids:
            return

        for sid in solar_ids[:1]:  # One contract per cycle to keep it manageable
            solar = self.agents[sid]
            cid = random.choice(consumer_ids)

            # Predict production from current output
            offer = solar.get_offer(self.tick, self.sim_hour)
            if not offer or offer.amount_kwh < 0.01:
                continue

            predicted_kwh = offer.amount_kwh
            demand_agent = self.agents[cid]
            demand = demand_agent.get_demand(self.tick, self.sim_hour)
            predicted_demand = demand.amount_kwh if demand else predicted_kwh

            # Generate deterministic nonces from tick + agent IDs
            producer_nonce = _hl.sha256(f"{sid}:{self.tick}:producer".encode()).hexdigest()[:16]
            consumer_nonce = _hl.sha256(f"{cid}:{self.tick}:consumer".encode()).hexdigest()[:16]

            # Forecast spread
            vol = getattr(self.oracle, "price_variance", 0.0) ** 0.5
            spread = self.futures.forecast_spread(
                sid, self.sim_hour, vol, self.gemini
            )

            self.futures.create_contract(
                producer_id=sid,
                consumer_id=cid,
                predicted_production_kwh=predicted_kwh,
                predicted_demand_kwh=predicted_demand,
                producer_nonce=producer_nonce,
                consumer_nonce=consumer_nonce,
                spot_price=clearing_price,
                spread=spread,
                current_tick=self.tick,
            )

    def _settle_due_futures(self) -> None:
        """Settle any futures contracts that are due at the current tick."""
        import hashlib as _hl

        due = self.futures.get_pending_deliveries(self.tick)
        for contract in due:
            # Auto-reveal: in a real system agents would reveal via API
            # Here we reveal using the deterministic nonces from creation
            pid = contract.producer.agent_id
            cid = contract.consumer.agent_id
            commit_tick = contract.producer.commit_tick

            producer_nonce = _hl.sha256(f"{pid}:{commit_tick}:producer".encode()).hexdigest()[:16]
            consumer_nonce = _hl.sha256(f"{cid}:{commit_tick}:consumer".encode()).hexdigest()[:16]

            # Get the actual production from this solar agent this tick
            solar = self.agents.get(pid)
            actual_kwh = 0.0
            if solar:
                offer = solar.get_offer(self.tick, self.sim_hour)
                if offer:
                    actual_kwh = offer.amount_kwh

            # Reveal both sides
            if contract.producer.revealed_value is None:
                # Reveal with original predicted value (the hash was made from this)
                predicted = None
                # We need to find the original predicted value by trying to verify
                # Since we used deterministic nonces, we can reconstruct
                offer_at_commit = solar.get_offer(commit_tick, self.sim_hour) if solar else None
                predicted = offer_at_commit.amount_kwh if offer_at_commit else actual_kwh
                self.futures.reveal(
                    contract.contract_id, pid, predicted, producer_nonce
                )

            if contract.consumer.revealed_value is None:
                consumer = self.agents.get(cid)
                demand = consumer.get_demand(self.tick, self.sim_hour) if consumer else None
                predicted_demand = demand.amount_kwh if demand else 0.0
                self.futures.reveal(
                    contract.contract_id, cid, predicted_demand, consumer_nonce
                )

            # Settle
            self.futures.settle_contract(contract.contract_id, actual_kwh)
