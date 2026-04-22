"""Autonomous Agent Coalitions (DACs) with Shapley Value Revenue Splitting.

Agents can form temporary coalitions (virtual power plants) that bid as a
single entity in the merit-order auction. Revenue is split according to each
member's Shapley value -- the marginal contribution they bring to every
possible sub-coalition.

Mathematical foundation:
    phi_i(v) = SUM over S subset of N\\{i}:
        |S|! * (|N|-|S|-1)! / |N|! * [v(S union {i}) - v(S)]

For a 2-member coalition {A, B}:
    phi_A = (v({A}) + v({A,B}) - v({B})) / 2
    phi_B = (v({B}) + v({A,B}) - v({A})) / 2

The coalition value v(S) is defined as the total revenue the subset would
earn at the current clearing price, accounting for dispatchability bonuses:
- Solar alone: intermittent, lower value
- Battery alone: stored but limited
- Solar + Battery together: dispatchable (guaranteed delivery), earns a
  premium because the grid values firm power over intermittent supply.

This models real wholesale electricity markets where generator portfolios
(e.g., wind + gas peaker) bid jointly for higher capacity payments.
"""

from __future__ import annotations

import itertools
import logging
import math
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("gridmint.coalitions")

# Dispatchability premium: firm power is worth more than intermittent
# Real-world analogy: capacity payments in PJM are ~$50/MW-day for firm vs $0 for intermittent
DISPATCHABILITY_PREMIUM = 1.25  # 25% price premium for dispatchable (solar+battery) bundles


@dataclass
class CoalitionMember:
    """A single agent's contribution to a coalition."""
    agent_id: str
    agent_type: str  # "solar", "battery", "consumer"
    offered_kwh: float  # energy this member contributes
    marginal_cost: float  # $/kWh cost floor for this member
    wallet_address: Optional[str] = None


@dataclass
class Coalition:
    """A temporary coalition of agents bidding as one entity."""
    coalition_id: str
    members: list[CoalitionMember]
    formation_tick: int
    # Computed fields
    total_kwh: float = 0.0
    joint_price: float = 0.0
    is_dispatchable: bool = False
    shapley_values: dict[str, float] = field(default_factory=dict)
    revenue_usd: float = 0.0
    revenue_splits: dict[str, float] = field(default_factory=dict)

    def __post_init__(self):
        self.total_kwh = sum(m.offered_kwh for m in self.members)
        member_types = {m.agent_type for m in self.members}
        # Dispatchable = has both generation AND storage
        self.is_dispatchable = ("solar" in member_types and "battery" in member_types)


def _coalition_value(
    members: list[CoalitionMember],
    clearing_price: float,
) -> float:
    """Compute the economic value of a coalition subset.

    Value = total_kwh * effective_price, where effective_price includes
    a dispatchability premium if the coalition has both solar and battery.
    """
    if not members:
        return 0.0

    total_kwh = sum(m.offered_kwh for m in members)
    if total_kwh <= 0:
        return 0.0

    types = {m.agent_type for m in members}
    is_dispatchable = "solar" in types and "battery" in types

    effective_price = clearing_price
    if is_dispatchable:
        effective_price *= DISPATCHABILITY_PREMIUM

    return total_kwh * effective_price


def compute_shapley_values(
    members: list[CoalitionMember],
    clearing_price: float,
) -> dict[str, float]:
    """Compute exact Shapley values for each coalition member.

    Uses the combinatorial definition:
        phi_i = SUM_{S subset N\\{i}} |S|!(n-|S|-1)!/n! * [v(S+i) - v(S)]

    Complexity: O(2^n * n) where n = coalition size.
    For n <= 10 (our fleet), this is at most 10240 evaluations -- trivial.

    Returns:
        Dict mapping agent_id -> Shapley value (fraction of total value).
        Values sum to v(N) (the grand coalition value).
    """
    n = len(members)
    if n == 0:
        return {}
    if n == 1:
        return {members[0].agent_id: _coalition_value(members, clearing_price)}

    member_map = {m.agent_id: m for m in members}
    agent_ids = list(member_map.keys())
    factorial_cache = {k: math.factorial(k) for k in range(n + 1)}
    n_fact = factorial_cache[n]

    shapley = {aid: 0.0 for aid in agent_ids}

    for aid in agent_ids:
        others = [oid for oid in agent_ids if oid != aid]

        # Iterate over all subsets of others
        for r in range(len(others) + 1):
            for subset_ids in itertools.combinations(others, r):
                s_size = len(subset_ids)
                # Combinatorial weight
                weight = (factorial_cache[s_size] * factorial_cache[n - s_size - 1]) / n_fact

                # v(S)
                subset_members = [member_map[sid] for sid in subset_ids]
                v_without = _coalition_value(subset_members, clearing_price)

                # v(S union {i})
                subset_with = subset_members + [member_map[aid]]
                v_with = _coalition_value(subset_with, clearing_price)

                shapley[aid] += weight * (v_with - v_without)

    return shapley


def compute_revenue_splits(
    coalition: Coalition,
    clearing_price: float,
    revenue_usd: float,
) -> dict[str, float]:
    """Split actual settlement revenue according to Shapley values.

    The Shapley values give each agent's fair share of the coalition value.
    We normalize them to sum to 1.0, then multiply by actual revenue.

    Returns:
        Dict mapping agent_id -> USD amount to receive.
    """
    shapley = compute_shapley_values(coalition.members, clearing_price)
    coalition.shapley_values = shapley

    total_shapley = sum(shapley.values())
    if total_shapley <= 0:
        # Equal split fallback (should never happen with positive clearing price)
        n = len(coalition.members)
        return {m.agent_id: revenue_usd / max(n, 1) for m in coalition.members}

    splits = {}
    for aid, sv in shapley.items():
        splits[aid] = round(revenue_usd * (sv / total_shapley), 8)

    coalition.revenue_usd = revenue_usd
    coalition.revenue_splits = splits
    return splits


class CoalitionEngine:
    """Manages coalition formation, joint bidding, and revenue splitting.

    Lifecycle per tick:
        1. form_coalitions() - identify profitable coalitions from current offers
        2. get_joint_offers() - return merged offers for the matching engine
        3. split_revenue() - after settlement, distribute USDC via Shapley

    Coalition formation rule:
        A coalition forms if its Shapley-value-weighted revenue for EVERY
        member exceeds what they'd earn bidding solo. This ensures individual
        rationality (no agent is worse off joining).
    """

    def __init__(self):
        self.active_coalitions: dict[str, Coalition] = {}
        self.historical_coalitions: list[Coalition] = []
        self._coalition_counter = 0

    @property
    def stats(self) -> dict:
        """Coalition statistics for the dashboard."""
        total_formed = len(self.historical_coalitions)
        total_dispatchable = sum(1 for c in self.historical_coalitions if c.is_dispatchable)
        total_revenue = sum(c.revenue_usd for c in self.historical_coalitions)
        avg_members = (
            sum(len(c.members) for c in self.historical_coalitions) / max(total_formed, 1)
        )
        return {
            "total_formed": total_formed,
            "total_dispatchable": total_dispatchable,
            "total_revenue_usd": round(total_revenue, 8),
            "avg_members": round(avg_members, 1),
            "active": len(self.active_coalitions),
            "premium_factor": DISPATCHABILITY_PREMIUM,
        }

    def form_coalitions(
        self,
        agents: dict,
        tick: int,
        sim_hour: float,
        clearing_price: float,
    ) -> list[Coalition]:
        """Identify and form profitable coalitions from current agent set.

        Strategy: pair each solar agent with an available battery to create
        dispatchable virtual power plants. Only form if individually rational.
        """
        self.active_coalitions.clear()
        formed = []

        # Find available solar and battery agents
        solar_agents = []
        battery_agents = []
        for aid, agent in agents.items():
            if agent.status.value == "offline":
                continue
            if agent.agent_type.value == "solar":
                solar_agents.append(agent)
            elif agent.agent_type.value == "battery":
                # Battery joins coalition only if it has stored energy to sell
                if hasattr(agent, "dischargeable_kwh") and agent.dischargeable_kwh > 0.1:
                    battery_agents.append(agent)

        if not solar_agents or not battery_agents or clearing_price <= 0:
            return formed

        # Greedy pairing: match solar with closest-capacity battery
        used_batteries = set()

        for solar in solar_agents:
            # BUGFIX: Get solar's current production by calling _production_kwh() method
            # Previously used getattr(solar, "_last_production_kwh", 0.0) which doesn't exist
            solar_kwh = solar._production_kwh(sim_hour) if hasattr(solar, "_production_kwh") else 0.0
            if solar_kwh <= 0.001:
                continue

            best_battery = None
            best_gain = 0.0

            for batt in battery_agents:
                if batt.agent_id in used_batteries:
                    continue

                batt_kwh = min(batt.dischargeable_kwh, batt.max_charge_rate_kw * batt.tick_duration_hours)
                if batt_kwh <= 0.001:
                    continue

                # Check individual rationality: each member must gain
                solar_member = CoalitionMember(
                    agent_id=solar.agent_id,
                    agent_type="solar",
                    offered_kwh=solar_kwh,
                    marginal_cost=getattr(solar, "price_usd_per_kwh", 0.003),
                    wallet_address=solar.wallet_address,
                )
                batt_member = CoalitionMember(
                    agent_id=batt.agent_id,
                    agent_type="battery",
                    offered_kwh=batt_kwh,
                    marginal_cost=batt.sell_threshold,
                    wallet_address=batt.wallet_address,
                )

                members = [solar_member, batt_member]
                shapley = compute_shapley_values(members, clearing_price)

                # Solo values
                solo_solar = _coalition_value([solar_member], clearing_price)
                solo_batt = _coalition_value([batt_member], clearing_price)

                # Individual rationality check: Shapley value >= solo value
                if (shapley[solar.agent_id] >= solo_solar and
                        shapley[batt.agent_id] >= solo_batt):
                    gain = sum(shapley.values()) - solo_solar - solo_batt
                    if gain > best_gain:
                        best_gain = gain
                        best_battery = (batt, batt_member, solar_member)

            if best_battery:
                batt, batt_member, solar_member = best_battery
                used_batteries.add(batt.agent_id)

                self._coalition_counter += 1
                cid = f"dac-{self._coalition_counter}"

                coalition = Coalition(
                    coalition_id=cid,
                    members=[solar_member, batt_member],
                    formation_tick=tick,
                )
                # Compute joint price: weighted average of marginal costs
                total_kwh = coalition.total_kwh
                if total_kwh > 0:
                    weighted_cost = sum(m.marginal_cost * m.offered_kwh for m in coalition.members)
                    coalition.joint_price = round(weighted_cost / total_kwh, 6)

                # Compute and store Shapley values
                coalition.shapley_values = compute_shapley_values(
                    coalition.members, clearing_price
                )

                self.active_coalitions[cid] = coalition
                formed.append(coalition)

                logger.info(
                    "Coalition %s formed: %s (%.3f kWh) + %s (%.3f kWh) = "
                    "%.3f kWh dispatchable | premium: %.0f%%",
                    cid,
                    solar_member.agent_id, solar_member.offered_kwh,
                    batt_member.agent_id, batt_member.offered_kwh,
                    total_kwh,
                    (DISPATCHABILITY_PREMIUM - 1) * 100,
                )

        return formed

    def split_revenue(
        self,
        coalition_id: str,
        revenue_usd: float,
        clearing_price: float,
    ) -> dict[str, float]:
        """Split settlement revenue for a completed coalition trade.

        Returns dict of agent_id -> USD amount. The coalition is then
        moved to historical records.
        """
        coalition = self.active_coalitions.get(coalition_id)
        if not coalition:
            return {}

        splits = compute_revenue_splits(coalition, clearing_price, revenue_usd)

        # Archive
        self.historical_coalitions.append(coalition)
        del self.active_coalitions[coalition_id]

        logger.info(
            "Coalition %s revenue split: $%.8f -> %s",
            coalition_id,
            revenue_usd,
            {aid: f"${v:.8f}" for aid, v in splits.items()},
        )

        return splits

    def get_coalition_for_agent(self, agent_id: str) -> Optional[Coalition]:
        """Check if an agent is currently in an active coalition."""
        for coalition in self.active_coalitions.values():
            for member in coalition.members:
                if member.agent_id == agent_id:
                    return coalition
        return None
