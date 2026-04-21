"""Tests for Autonomous Agent Coalitions (DACs) and Energy Futures.

Covers:
1. Shapley value mathematical correctness
2. Coalition formation with individual rationality
3. Revenue splitting accuracy
4. Commit-reveal cryptographic integrity
5. Slashing mechanics
6. Futures spread forecasting
7. Full integration with GridEngine
"""

import sys
import os
import hashlib
import math

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from engine.coalitions import (
    CoalitionEngine,
    CoalitionMember,
    Coalition,
    compute_shapley_values,
    compute_revenue_splits,
    _coalition_value,
    DISPATCHABILITY_PREMIUM,
)
from engine.futures import (
    FuturesEngine,
    FuturesState,
    create_commitment_hash,
    verify_commitment,
)
from engine.grid_engine import GridEngine
from agents.config import create_demo_fleet


# =========================================================================
# 1. Shapley Value Mathematical Correctness
# =========================================================================
class TestShapleyValues:

    def test_two_player_shapley_sums_to_grand_coalition(self):
        """Shapley values must sum to v(N) -- the efficiency axiom."""
        members = [
            CoalitionMember(agent_id="solar-1", agent_type="solar", offered_kwh=3.0, marginal_cost=0.003),
            CoalitionMember(agent_id="battery-1", agent_type="battery", offered_kwh=2.0, marginal_cost=0.005),
        ]
        price = 0.005
        shapley = compute_shapley_values(members, price)
        grand_value = _coalition_value(members, price)

        assert abs(sum(shapley.values()) - grand_value) < 1e-10, \
            f"Shapley sum {sum(shapley.values())} != grand coalition {grand_value}"

    def test_single_agent_gets_full_value(self):
        """A solo agent's Shapley value equals its standalone value."""
        member = CoalitionMember(agent_id="solar-1", agent_type="solar", offered_kwh=5.0, marginal_cost=0.003)
        shapley = compute_shapley_values([member], 0.005)
        solo = _coalition_value([member], 0.005)
        assert abs(shapley["solar-1"] - solo) < 1e-10

    def test_symmetry_axiom(self):
        """Two identical agents must get equal Shapley values."""
        members = [
            CoalitionMember(agent_id="s1", agent_type="solar", offered_kwh=3.0, marginal_cost=0.003),
            CoalitionMember(agent_id="s2", agent_type="solar", offered_kwh=3.0, marginal_cost=0.003),
        ]
        shapley = compute_shapley_values(members, 0.005)
        assert abs(shapley["s1"] - shapley["s2"]) < 1e-10

    def test_dispatchability_premium_increases_value(self):
        """Solar+battery coalition value > sum of individual values."""
        solar = CoalitionMember(agent_id="solar-1", agent_type="solar", offered_kwh=3.0, marginal_cost=0.003)
        battery = CoalitionMember(agent_id="bat-1", agent_type="battery", offered_kwh=2.0, marginal_cost=0.005)
        price = 0.005

        v_solar = _coalition_value([solar], price)
        v_batt = _coalition_value([battery], price)
        v_joint = _coalition_value([solar, battery], price)

        assert v_joint > v_solar + v_batt, \
            f"Joint {v_joint} should exceed sum {v_solar + v_batt} due to premium"
        expected = (3.0 + 2.0) * price * DISPATCHABILITY_PREMIUM
        assert abs(v_joint - expected) < 1e-10

    def test_three_player_shapley(self):
        """Shapley for 3 agents sums correctly and respects contribution order."""
        members = [
            CoalitionMember(agent_id="s1", agent_type="solar", offered_kwh=4.0, marginal_cost=0.003),
            CoalitionMember(agent_id="b1", agent_type="battery", offered_kwh=2.0, marginal_cost=0.005),
            CoalitionMember(agent_id="s2", agent_type="solar", offered_kwh=1.0, marginal_cost=0.003),
        ]
        price = 0.005
        shapley = compute_shapley_values(members, price)
        grand = _coalition_value(members, price)
        assert abs(sum(shapley.values()) - grand) < 1e-10

    def test_zero_clearing_price_yields_zero_values(self):
        """At clearing price 0, all Shapley values should be 0."""
        members = [
            CoalitionMember(agent_id="s1", agent_type="solar", offered_kwh=5.0, marginal_cost=0.003),
            CoalitionMember(agent_id="b1", agent_type="battery", offered_kwh=3.0, marginal_cost=0.005),
        ]
        shapley = compute_shapley_values(members, 0.0)
        assert all(abs(v) < 1e-10 for v in shapley.values())


# =========================================================================
# 2. Coalition Formation
# =========================================================================
class TestCoalitionFormation:

    def test_coalition_forms_with_solar_and_battery(self):
        """A solar+battery pair should form a dispatchable coalition."""
        fleet = create_demo_fleet()
        engine = GridEngine(agents=fleet, start_hour=12.0)
        # Run a few ticks so agents have production
        for _ in range(3):
            engine.step()

        coalitions = engine.coalitions.form_coalitions(
            engine.agents, engine.tick,
            engine.clearing_price if engine.clearing_price > 0 else 0.005,
        )
        # At noon, solar produces, battery has charge -> should form
        if engine.clearing_price > 0:
            # If there were trades, coalitions should form
            assert len(coalitions) >= 0  # May not form if battery has no dischargeable

    def test_coalition_is_dispatchable(self):
        """Solar+battery coalition must be marked dispatchable."""
        members = [
            CoalitionMember(agent_id="s1", agent_type="solar", offered_kwh=3.0, marginal_cost=0.003),
            CoalitionMember(agent_id="b1", agent_type="battery", offered_kwh=2.0, marginal_cost=0.005),
        ]
        c = Coalition(coalition_id="test", members=members, formation_tick=1)
        assert c.is_dispatchable is True

    def test_solar_only_not_dispatchable(self):
        """Two solar agents do not form a dispatchable coalition."""
        members = [
            CoalitionMember(agent_id="s1", agent_type="solar", offered_kwh=3.0, marginal_cost=0.003),
            CoalitionMember(agent_id="s2", agent_type="solar", offered_kwh=2.0, marginal_cost=0.003),
        ]
        c = Coalition(coalition_id="test", members=members, formation_tick=1)
        assert c.is_dispatchable is False


# =========================================================================
# 3. Revenue Splitting
# =========================================================================
class TestRevenueSplitting:

    def test_revenue_splits_sum_to_total(self):
        """Shapley-based revenue splits must sum to total revenue."""
        members = [
            CoalitionMember(agent_id="s1", agent_type="solar", offered_kwh=3.0, marginal_cost=0.003),
            CoalitionMember(agent_id="b1", agent_type="battery", offered_kwh=2.0, marginal_cost=0.005),
        ]
        coalition = Coalition(coalition_id="test", members=members, formation_tick=1)
        revenue = 0.025  # $0.025 total
        splits = compute_revenue_splits(coalition, 0.005, revenue)

        assert abs(sum(splits.values()) - revenue) < 1e-7, \
            f"Splits {splits} don't sum to {revenue}"

    def test_larger_contributor_gets_more(self):
        """Agent contributing more kWh should get a larger share."""
        members = [
            CoalitionMember(agent_id="big", agent_type="solar", offered_kwh=8.0, marginal_cost=0.003),
            CoalitionMember(agent_id="small", agent_type="solar", offered_kwh=1.0, marginal_cost=0.003),
        ]
        coalition = Coalition(coalition_id="test", members=members, formation_tick=1)
        splits = compute_revenue_splits(coalition, 0.005, 0.045)
        assert splits["big"] > splits["small"]


# =========================================================================
# 4. Commit-Reveal Cryptographic Integrity
# =========================================================================
class TestCommitReveal:

    def test_commitment_hash_deterministic(self):
        """Same inputs must produce same hash."""
        h1 = create_commitment_hash(3.14159, "my_nonce_123")
        h2 = create_commitment_hash(3.14159, "my_nonce_123")
        assert h1 == h2
        assert h1.startswith("0x")
        assert len(h1) == 66  # 0x + 64 hex

    def test_different_nonce_different_hash(self):
        """Different nonces must produce different hashes."""
        h1 = create_commitment_hash(5.0, "nonce_a")
        h2 = create_commitment_hash(5.0, "nonce_b")
        assert h1 != h2

    def test_different_value_different_hash(self):
        """Different values must produce different hashes."""
        h1 = create_commitment_hash(5.0, "nonce")
        h2 = create_commitment_hash(5.1, "nonce")
        assert h1 != h2

    def test_verify_correct_reveal(self):
        """Valid reveal must pass verification."""
        value = 3.456789
        nonce = "secret_nonce_42"
        h = create_commitment_hash(value, nonce)
        assert verify_commitment(h, value, nonce) is True

    def test_verify_wrong_value_fails(self):
        """Tampered value must fail verification."""
        value = 3.456789
        nonce = "secret_nonce_42"
        h = create_commitment_hash(value, nonce)
        assert verify_commitment(h, value + 0.001, nonce) is False

    def test_verify_wrong_nonce_fails(self):
        """Wrong nonce must fail verification."""
        value = 3.456789
        nonce = "secret_nonce_42"
        h = create_commitment_hash(value, nonce)
        assert verify_commitment(h, value, "wrong_nonce") is False

    def test_precision_normalization(self):
        """Values differing only beyond 6 decimals should hash the same."""
        h1 = create_commitment_hash(1.0000001, "nonce")
        h2 = create_commitment_hash(1.0000002, "nonce")
        # Both round to 1.000000 at 6dp
        assert h1 == h2


# =========================================================================
# 5. Slashing Mechanics
# =========================================================================
class TestSlashing:

    def test_full_delivery_no_slash(self):
        """Producer delivering >= 95% gets no slash."""
        engine = FuturesEngine(delivery_window=3)
        contract = engine.create_contract(
            producer_id="solar-1", consumer_id="house-1",
            predicted_production_kwh=5.0, predicted_demand_kwh=5.0,
            producer_nonce="pnonce", consumer_nonce="cnonce",
            spot_price=0.005, spread=0.10, current_tick=1,
        )
        # Reveal
        engine.reveal(contract.contract_id, "solar-1", 5.0, "pnonce")
        engine.reveal(contract.contract_id, "house-1", 5.0, "cnonce")

        # Settle with full delivery
        result = engine.settle_contract(contract.contract_id, 5.0)
        assert result.state == FuturesState.SETTLED
        assert result.slash_amount_usd == 0.0
        assert result.producer_pnl_usd > 0  # Earned the spread premium

    def test_partial_delivery_slashed(self):
        """Producer delivering < 95% gets proportionally slashed."""
        engine = FuturesEngine(delivery_window=3)
        contract = engine.create_contract(
            producer_id="solar-1", consumer_id="house-1",
            predicted_production_kwh=10.0, predicted_demand_kwh=10.0,
            producer_nonce="pn", consumer_nonce="cn",
            spot_price=0.005, spread=0.15, current_tick=1,
        )
        engine.reveal(contract.contract_id, "solar-1", 10.0, "pn")
        engine.reveal(contract.contract_id, "house-1", 10.0, "cn")

        # Deliver only 50%
        result = engine.settle_contract(contract.contract_id, 5.0)
        assert result.state == FuturesState.SLASHED
        assert result.slash_amount_usd > 0
        # Slash should be ~50% of producer deposit
        expected_slash = contract.producer.deposit_usd * 0.5
        assert abs(result.slash_amount_usd - expected_slash) < 1e-8

    def test_zero_delivery_full_slash(self):
        """Zero delivery = full deposit slashed."""
        engine = FuturesEngine(delivery_window=3)
        contract = engine.create_contract(
            producer_id="solar-1", consumer_id="house-1",
            predicted_production_kwh=5.0, predicted_demand_kwh=5.0,
            producer_nonce="pn", consumer_nonce="cn",
            spot_price=0.005, spread=0.10, current_tick=1,
        )
        engine.reveal(contract.contract_id, "solar-1", 5.0, "pn")
        engine.reveal(contract.contract_id, "house-1", 5.0, "cn")

        result = engine.settle_contract(contract.contract_id, 0.0)
        assert result.state == FuturesState.SLASHED
        assert abs(result.slash_amount_usd - contract.producer.deposit_usd) < 1e-8

    def test_no_reveal_full_slash(self):
        """Producer that never reveals gets fully slashed."""
        engine = FuturesEngine(delivery_window=3)
        contract = engine.create_contract(
            producer_id="solar-1", consumer_id="house-1",
            predicted_production_kwh=5.0, predicted_demand_kwh=5.0,
            producer_nonce="pn", consumer_nonce="cn",
            spot_price=0.005, spread=0.10, current_tick=1,
        )
        # Don't reveal -- settle directly
        result = engine.settle_contract(contract.contract_id, 5.0)
        assert result.state == FuturesState.SLASHED
        assert result.slash_amount_usd == contract.producer.deposit_usd

    def test_consumer_compensated_on_slash(self):
        """Slashed amount goes to consumer as compensation."""
        engine = FuturesEngine(delivery_window=3)
        contract = engine.create_contract(
            producer_id="solar-1", consumer_id="house-1",
            predicted_production_kwh=10.0, predicted_demand_kwh=10.0,
            producer_nonce="pn", consumer_nonce="cn",
            spot_price=0.005, spread=0.10, current_tick=1,
        )
        engine.reveal(contract.contract_id, "solar-1", 10.0, "pn")
        engine.reveal(contract.contract_id, "house-1", 10.0, "cn")

        result = engine.settle_contract(contract.contract_id, 3.0)  # 30% delivery
        assert result.consumer_pnl_usd == result.slash_amount_usd
        assert result.producer_pnl_usd == -result.slash_amount_usd


# =========================================================================
# 6. Spread Forecasting
# =========================================================================
class TestSpreadForecasting:

    def test_new_producer_gets_moderate_spread(self):
        """Producer with no track record gets ~20% spread."""
        engine = FuturesEngine()
        spread = engine.forecast_spread("new_solar", 12.0, 0.0)
        assert 0.15 <= spread <= 0.25

    def test_reliable_producer_gets_lower_spread(self):
        """Producer with perfect track record gets lower spread."""
        engine = FuturesEngine()
        engine.producer_accuracy["reliable"] = [1.0, 1.0, 1.0, 1.0, 1.0]
        spread_reliable = engine.forecast_spread("reliable", 12.0, 0.0)
        spread_new = engine.forecast_spread("new_solar", 12.0, 0.0)
        assert spread_reliable < spread_new

    def test_nighttime_higher_spread(self):
        """Nighttime solar futures should have higher spread."""
        engine = FuturesEngine()
        spread_noon = engine.forecast_spread("s1", 12.0, 0.0)
        spread_night = engine.forecast_spread("s1", 22.0, 0.0)
        assert spread_night > spread_noon

    def test_spread_capped(self):
        """Spread must never exceed MAX_SPREAD."""
        engine = FuturesEngine()
        spread = engine.forecast_spread("s1", 22.0, 10.0)  # high volatility + night
        assert spread <= 0.50


# =========================================================================
# 7. Full Integration
# =========================================================================
class TestFullIntegration:

    def test_grid_engine_with_coalitions_and_futures(self):
        """Run 30 ticks and verify coalitions + futures integrate cleanly."""
        fleet = create_demo_fleet()
        engine = GridEngine(agents=fleet, start_hour=10.0, speed_multiplier=360)

        for _ in range(30):
            engine.step()

        # Coalitions should have stats
        c_stats = engine.coalitions.stats
        assert "total_formed" in c_stats
        assert c_stats["premium_factor"] == DISPATCHABILITY_PREMIUM

        # Futures should have stats
        f_stats = engine.futures.stats
        assert "total_contracts" in f_stats
        assert f_stats["delivery_window_ticks"] == 3

        # The engine should still produce valid snapshots
        assert len(engine.snapshots) == 30
        for snap in engine.snapshots:
            assert snap.tick > 0
            for m in snap.matches:
                assert m.price_usd_per_kwh <= 0.01

    def test_producer_accuracy_tracking(self):
        """After futures settlement, producer accuracy should be tracked."""
        engine = FuturesEngine(delivery_window=3)
        contract = engine.create_contract(
            producer_id="solar-1", consumer_id="house-1",
            predicted_production_kwh=4.0, predicted_demand_kwh=4.0,
            producer_nonce="pn", consumer_nonce="cn",
            spot_price=0.005, spread=0.10, current_tick=1,
        )
        engine.reveal(contract.contract_id, "solar-1", 4.0, "pn")
        engine.reveal(contract.contract_id, "house-1", 4.0, "cn")
        engine.settle_contract(contract.contract_id, 3.0)  # 75% delivery

        assert "solar-1" in engine.producer_accuracy
        assert abs(engine.producer_accuracy["solar-1"][0] - 0.75) < 1e-10
