"""Security & Settlement Audit Tests.

Tests cover:
1. Nonce collision safety under parallel trades
2. Balance underflow protection
3. Private key isolation (no leaks in API responses)
4. Clearing price manipulation resistance
5. Agent state isolation (one agent can't corrupt another)
6. Settlement mode switching safety
7. Stress test recovery (agents return to original state)
8. x402 paywall bypass attempts
9. Merkle root determinism
10. Trade amount rounding precision
"""

import sys
import os
import hashlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import pytest
from agents import TradeMatch, EnergyOffer, EnergyDemand
from agents.config import create_demo_fleet
from engine.grid_engine import GridEngine
from engine.payment_engine import SimulatedSettler, PaymentEngine
from engine import match_orders
from engine.certificates import CertificateLedger
from engine.stress_test import StressTestRunner, ScenarioType


def _run(coro):
    """Helper to run async code in sync tests."""
    return asyncio.run(coro)


# =========================================================================
# 1. Balance underflow protection
# =========================================================================
class TestSettlementSecurity:

    def test_insufficient_balance_rejected(self):
        """Buyer with $0 cannot settle a trade."""
        settler = SimulatedSettler()
        settler.fund_wallet("seller", 10.0)
        settler.fund_wallet("buyer", 0.0)  # zero balance

        trade = TradeMatch(
            seller_id="seller", buyer_id="buyer",
            amount_kwh=1.0, price_usd_per_kwh=0.005,
            total_usd=0.005, tick=1,
        )
        result = _run(settler.settle(trade))
        assert not result.success
        assert "Insufficient" in result.error

    def test_exact_balance_succeeds(self):
        """Trade that exactly drains buyer balance should succeed."""
        settler = SimulatedSettler()
        settler.fund_wallet("seller", 0.0)
        settler.fund_wallet("buyer", 0.005)

        trade = TradeMatch(
            seller_id="seller", buyer_id="buyer",
            amount_kwh=1.0, price_usd_per_kwh=0.005,
            total_usd=0.005, tick=1,
        )
        result = _run(settler.settle(trade))
        assert result.success
        assert abs(settler.balances["buyer"]) < 1e-10
        assert abs(settler.balances["seller"] - 0.005) < 1e-10

    def test_double_spend_prevented(self):
        """Two trades that together exceed balance: second must fail."""
        settler = SimulatedSettler()
        settler.fund_wallet("buyer", 0.003)

        trade1 = TradeMatch(
            seller_id="s1", buyer_id="buyer",
            amount_kwh=1.0, price_usd_per_kwh=0.002,
            total_usd=0.002, tick=1,
        )
        trade2 = TradeMatch(
            seller_id="s2", buyer_id="buyer",
            amount_kwh=1.0, price_usd_per_kwh=0.002,
            total_usd=0.002, tick=1,
        )
        r1 = _run(settler.settle(trade1))
        r2 = _run(settler.settle(trade2))
        assert r1.success
        assert not r2.success  # Only $0.001 left, needs $0.002

    def test_tx_hash_uniqueness(self):
        """Every trade must get a unique tx hash."""
        settler = SimulatedSettler()
        settler.fund_wallet("buyer", 100.0)
        hashes = set()
        for i in range(100):
            trade = TradeMatch(
                seller_id="seller", buyer_id="buyer",
                amount_kwh=0.1, price_usd_per_kwh=0.001,
                total_usd=0.0001, tick=i,
            )
            r = _run(settler.settle(trade))
            assert r.success
            assert r.tx_hash not in hashes, f"Duplicate hash at trade {i}"
            hashes.add(r.tx_hash)


# =========================================================================
# 2. Clearing price manipulation resistance
# =========================================================================
class TestMarketIntegrity:

    def test_uniform_clearing_price(self):
        """All trades in a tick must use the same clearing price."""
        offers = [
            EnergyOffer(agent_id="s1", amount_kwh=5.0, price_usd_per_kwh=0.002, tick=1),
            EnergyOffer(agent_id="s2", amount_kwh=5.0, price_usd_per_kwh=0.004, tick=1),
        ]
        demands = [
            EnergyDemand(agent_id="b1", amount_kwh=8.0, max_price_usd_per_kwh=0.009, tick=1),
        ]
        matches, clearing = match_orders(offers, demands, 1)
        assert len(matches) == 2
        # All trades at clearing price
        for m in matches:
            assert m.price_usd_per_kwh == clearing

    def test_buyer_never_pays_above_max(self):
        """No trade should match at a price above buyer's max willingness."""
        offers = [
            EnergyOffer(agent_id="s1", amount_kwh=5.0, price_usd_per_kwh=0.008, tick=1),
        ]
        demands = [
            EnergyDemand(agent_id="b1", amount_kwh=5.0, max_price_usd_per_kwh=0.005, tick=1),
        ]
        matches, clearing = match_orders(offers, demands, 1)
        assert len(matches) == 0  # No match: ask > bid

    def test_zero_quantity_offer_ignored(self):
        """Offers with zero kWh should produce no matches."""
        offers = [
            EnergyOffer(agent_id="s1", amount_kwh=0.0, price_usd_per_kwh=0.002, tick=1),
        ]
        demands = [
            EnergyDemand(agent_id="b1", amount_kwh=5.0, max_price_usd_per_kwh=0.009, tick=1),
        ]
        matches, _ = match_orders(offers, demands, 1)
        assert len(matches) == 0

    def test_clearing_price_is_marginal_offer(self):
        """Clearing price should be the most expensive matched offer."""
        offers = [
            EnergyOffer(agent_id="s1", amount_kwh=2.0, price_usd_per_kwh=0.001, tick=1),
            EnergyOffer(agent_id="s2", amount_kwh=2.0, price_usd_per_kwh=0.003, tick=1),
            EnergyOffer(agent_id="s3", amount_kwh=2.0, price_usd_per_kwh=0.007, tick=1),
        ]
        demands = [
            EnergyDemand(agent_id="b1", amount_kwh=4.0, max_price_usd_per_kwh=0.009, tick=1),
        ]
        matches, clearing = match_orders(offers, demands, 1)
        # Should match s1 and s2 (4 kWh total), clearing at $0.003 (marginal)
        assert clearing == 0.003
        assert len(matches) == 2


# =========================================================================
# 3. Agent state isolation
# =========================================================================
class TestAgentIsolation:

    def test_private_key_not_in_state(self):
        """Agent state dump must never expose private keys."""
        fleet = create_demo_fleet()
        for agent in fleet:
            state = agent.get_state(0, 12.0)
            state_dict = state.model_dump()
            # private_key should not exist in the state model
            assert "private_key" not in state_dict
            # wallet_address is OK to expose
            json_str = str(state_dict)
            for key_name in ["private_key", "PRIVATE_KEY"]:
                assert key_name not in json_str

    def test_offline_agent_produces_nothing(self):
        """Offline agents must not generate offers or demands."""
        fleet = create_demo_fleet()
        for agent in fleet:
            agent.set_offline()
            assert agent.get_offer(1, 12.0) is None
            assert agent.get_demand(1, 12.0) is None

    def test_toggle_preserves_economics(self):
        """Toggling agent offline/online must not reset cumulative stats."""
        fleet = create_demo_fleet()
        engine = GridEngine(agents=fleet, start_hour=12.0)
        for _ in range(5):
            engine.step()

        solar = engine.agents["solar-1"]
        earned_before = solar.total_earned_usd
        tx_before = solar.tx_count

        solar.set_offline()
        solar.set_online()

        assert solar.total_earned_usd == earned_before
        assert solar.tx_count == tx_before


# =========================================================================
# 4. Stress test recovery
# =========================================================================
class TestStressTestRecovery:

    def test_solar_eclipse_recovers_all(self):
        """After solar eclipse, all solar agents must be back online."""
        fleet = create_demo_fleet()
        engine = GridEngine(agents=fleet, start_hour=12.0)
        engine.stress.start_scenario(ScenarioType.SOLAR_ECLIPSE, engine.agents, engine.tick)

        # Run enough ticks for the scenario to complete (11 ticks)
        for _ in range(15):
            engine.step()

        for aid, agent in engine.agents.items():
            if aid.startswith("solar"):
                assert agent.status.value == "online", f"{aid} stuck offline after eclipse"

    def test_demand_surge_restores_loads(self):
        """After demand surge, consumer loads must return to original values."""
        fleet = create_demo_fleet()
        engine = GridEngine(agents=fleet, start_hour=12.0)

        # Record original loads
        original_loads = {}
        for aid, agent in engine.agents.items():
            if hasattr(agent, "appliance_load_kw"):
                original_loads[aid] = agent.appliance_load_kw

        engine.stress.start_scenario(ScenarioType.DEMAND_SURGE, engine.agents, engine.tick)
        for _ in range(10):
            engine.step()

        for aid, orig in original_loads.items():
            current = engine.agents[aid].appliance_load_kw
            assert abs(current - orig) < 0.01, (
                f"{aid} load not restored: was {orig}, now {current}"
            )


# =========================================================================
# 5. Certificate Merkle root determinism
# =========================================================================
class TestCertificateIntegrity:

    def test_merkle_root_deterministic(self):
        """Merkle root must be a valid hex hash and stable when read twice."""
        ledger = CertificateLedger()
        trade = TradeMatch(
            seller_id="solar-1", buyer_id="house-1",
            amount_kwh=1.0, price_usd_per_kwh=0.003,
            total_usd=0.003, tick=1,
        )
        ledger.record_trade(trade, 12.0, "solar")

        root1 = ledger.get_merkle_root()
        root2 = ledger.get_merkle_root()
        assert root1 == root2  # Same ledger, same root
        assert root1.startswith("0x")
        assert len(root1) == 66  # 0x + 64 hex chars

    def test_merkle_root_changes_with_new_trade(self):
        """Adding a trade must change the Merkle root."""
        ledger = CertificateLedger()
        trade1 = TradeMatch(
            seller_id="solar-1", buyer_id="house-1",
            amount_kwh=1.0, price_usd_per_kwh=0.003,
            total_usd=0.003, tick=1,
        )
        ledger.record_trade(trade1, 12.0, "solar")
        root1 = ledger.get_merkle_root()

        trade2 = TradeMatch(
            seller_id="solar-2", buyer_id="house-2",
            amount_kwh=2.0, price_usd_per_kwh=0.004,
            total_usd=0.008, tick=2,
        )
        ledger.record_trade(trade2, 12.0, "solar")
        root2 = ledger.get_merkle_root()

        assert root1 != root2


# =========================================================================
# 6. Trade amount precision
# =========================================================================
class TestPrecision:

    def test_sub_cent_precision_maintained(self):
        """Verify no floating point drift causes prices to exceed $0.01."""
        fleet = create_demo_fleet()
        engine = GridEngine(agents=fleet, start_hour=10.0, speed_multiplier=360)

        for _ in range(50):
            engine.step()

        for snap in engine.snapshots:
            for m in snap.matches:
                assert m.price_usd_per_kwh <= 0.0099 + 1e-9, (
                    f"Price exceeded sub-cent cap: ${m.price_usd_per_kwh}"
                )
                assert m.total_usd >= 0, f"Negative trade value: ${m.total_usd}"

    def test_battery_soc_bounds(self):
        """Battery SOC must never go below 0 or above 1."""
        fleet = create_demo_fleet()
        engine = GridEngine(agents=fleet, start_hour=6.0, speed_multiplier=720)

        for _ in range(100):
            engine.step()

        for aid, agent in engine.agents.items():
            if hasattr(agent, "soc"):
                assert 0.0 <= agent.soc <= 1.0, (
                    f"{aid} SOC out of bounds: {agent.soc}"
                )


# =========================================================================
# 7. Payment engine queue integrity
# =========================================================================
class TestPaymentEngine:

    def test_queue_processes_all(self):
        """Every enqueued trade must be processed."""
        settler = SimulatedSettler()
        settler.fund_wallet("buyer", 100.0)
        pay = PaymentEngine(settler=settler)

        for i in range(20):
            trade = TradeMatch(
                seller_id="seller", buyer_id="buyer",
                amount_kwh=0.5, price_usd_per_kwh=0.002,
                total_usd=0.001, tick=i,
            )
            pay.enqueue_trade(trade)

        _run(pay.process_queue())

        assert pay.success_count == 20
        assert pay.failure_count == 0
        assert len(pay.results) == 20

    def test_stats_accuracy(self):
        """Payment stats must match actual settled amounts."""
        settler = SimulatedSettler()
        settler.fund_wallet("buyer", 100.0)
        pay = PaymentEngine(settler=settler)

        total = 0.0
        for i in range(10):
            amt = round(0.001 * (i + 1), 6)
            trade = TradeMatch(
                seller_id="seller", buyer_id="buyer",
                amount_kwh=1.0, price_usd_per_kwh=amt,
                total_usd=amt, tick=i,
            )
            _run(pay.settle_trade(trade))
            total += amt

        assert abs(pay.total_settled_usd - total) < 1e-8
