"""Schelling Point Discovery via Multiplicative Weights Update (MWU).

Each agent maintains a probability distribution over a discretized price grid.
After each tick, agents observe whether they were matched at their chosen price
and shift weight toward prices that yielded successful trades.

This implements online convex optimization with logarithmic regret:
    w_i(t+1) = w_i(t) * exp(eta * reward_i(t))
    p_i(t+1) = w_i(t+1) / sum(w_j(t+1))

Over ~50 ticks, agents converge to a Nash equilibrium price that emerges
from pure game-theoretic dynamics — no oracle, no hardcoded thresholds.

The regret bound is O(sqrt(T * ln(N))) where T = ticks, N = price slots.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Optional


# Discretized price grid: 9 price slots from $0.001 to $0.009
PRICE_GRID = [round(0.001 * (i + 1), 4) for i in range(9)]
NUM_SLOTS = len(PRICE_GRID)


@dataclass
class MWUState:
    """Per-agent MWU learning state."""

    agent_id: str
    role: str  # "seller" or "buyer"
    # Log-weights (stored in log-space for numerical stability)
    log_weights: list[float] = field(default_factory=lambda: [0.0] * NUM_SLOTS)
    # Cumulative reward for regret tracking
    cumulative_reward: float = 0.0
    best_fixed_reward: float = 0.0
    ticks_played: int = 0
    last_chosen_slot: int = 4  # middle of grid
    last_matched: bool = False
    last_reward: float = 0.0

    @property
    def probabilities(self) -> list[float]:
        """Convert log-weights to probability distribution via softmax."""
        max_lw = max(self.log_weights)
        exps = [math.exp(lw - max_lw) for lw in self.log_weights]
        total = sum(exps)
        return [e / total for e in exps]

    @property
    def expected_price(self) -> float:
        """Expected price under current distribution."""
        probs = self.probabilities
        return sum(p * PRICE_GRID[i] for i, p in enumerate(probs))

    @property
    def entropy(self) -> float:
        """Shannon entropy of distribution (higher = more uncertain)."""
        probs = self.probabilities
        return -sum(p * math.log(p + 1e-12) for p in probs)

    @property
    def regret(self) -> float:
        """External regret: best fixed action - cumulative reward."""
        return max(0.0, self.best_fixed_reward - self.cumulative_reward)


class SchellingEngine:
    """Manages MWU learning for all agents in the grid.

    Usage:
        1. At init, register each agent with register_agent()
        2. Each tick, call choose_price(agent_id) to sample a price
        3. After matching, call update(agent_id, matched, clearing_price)

    The engine tracks convergence and exposes distribution data for the dashboard.
    """

    def __init__(self, learning_rate: float = 0.5):
        """
        Args:
            learning_rate: eta parameter for MWU. Higher = faster convergence
                but more oscillation. Theory optimal: sqrt(ln(N)/T).
                0.5 is good for T~50, N=9: sqrt(ln(9)/50) ~ 0.21, we use
                slightly higher for faster visual convergence in demo.
        """
        self.eta = learning_rate
        self.agents: dict[str, MWUState] = {}
        self._per_slot_rewards: dict[str, list[float]] = {}  # for best-fixed tracking

    def register_agent(self, agent_id: str, role: str) -> None:
        """Register an agent for MWU learning.

        Args:
            agent_id: Unique agent identifier.
            role: "seller" (solar/battery) or "buyer" (consumer/battery-charging).
        """
        self.agents[agent_id] = MWUState(agent_id=agent_id, role=role)
        self._per_slot_rewards[agent_id] = [0.0] * NUM_SLOTS

    def choose_price(self, agent_id: str) -> float:
        """Sample a price from the agent's learned distribution.

        Returns a price from the discretized grid, chosen proportionally
        to the agent's MWU weight distribution.
        """
        state = self.agents.get(agent_id)
        if state is None:
            return PRICE_GRID[NUM_SLOTS // 2]  # default middle

        probs = state.probabilities
        # Roulette wheel selection
        r = random.random()
        cumsum = 0.0
        chosen = NUM_SLOTS - 1
        for i, p in enumerate(probs):
            cumsum += p
            if r <= cumsum:
                chosen = i
                break

        state.last_chosen_slot = chosen
        return PRICE_GRID[chosen]

    def update(
        self,
        agent_id: str,
        was_matched: bool,
        clearing_price: float,
        trade_kwh: float = 0.0,
    ) -> None:
        """Update MWU weights after observing this tick's outcome.

        Reward function design (critical for convergence quality):
        - Sellers: reward = kwh_sold * (clearing_price - grid_price[slot]) if matched
          Incentivizes bidding close to but below clearing price.
        - Buyers: reward = kwh_bought * (grid_price[slot] - clearing_price) if matched
          Incentivizes bidding close to but above clearing price.
        - Unmatched: reward = -small_penalty to discourage extreme bids.

        This is a zero-sum-like structure that drives both sides toward
        the competitive equilibrium.
        """
        state = self.agents.get(agent_id)
        if state is None:
            return

        state.ticks_played += 1
        state.last_matched = was_matched

        # Compute reward for each slot (counterfactual: what if we'd chosen slot i?)
        rewards = [0.0] * NUM_SLOTS
        for i in range(NUM_SLOTS):
            slot_price = PRICE_GRID[i]
            if state.role == "seller":
                if clearing_price >= slot_price:
                    # Would have been matched (bid below clearing)
                    # Reward: profit margin = clearing - cost, scaled by volume
                    rewards[i] = max(0.0, clearing_price - slot_price) * max(trade_kwh, 0.1)
                else:
                    # Too expensive, would not match
                    rewards[i] = -0.001
            else:  # buyer
                if clearing_price <= slot_price:
                    # Would have been matched (bid above clearing)
                    # Reward: consumer surplus = willingness - clearing
                    rewards[i] = max(0.0, slot_price - clearing_price) * max(trade_kwh, 0.1)
                else:
                    # Bid too low, would not match
                    rewards[i] = -0.001

        # MWU update: log_w(t+1) = log_w(t) + eta * reward
        for i in range(NUM_SLOTS):
            state.log_weights[i] += self.eta * rewards[i]
            # Track per-slot cumulative for best-fixed-action regret
            self._per_slot_rewards[agent_id][i] += rewards[i]

        # Track cumulative reward for chosen slot
        actual_reward = rewards[state.last_chosen_slot]
        state.last_reward = actual_reward
        state.cumulative_reward += actual_reward

        # Best fixed action reward (for regret calculation)
        state.best_fixed_reward = max(self._per_slot_rewards[agent_id])

    @property
    def convergence_metrics(self) -> dict:
        """Dashboard-ready convergence summary."""
        if not self.agents:
            return {}

        seller_states = [s for s in self.agents.values() if s.role == "seller"]
        buyer_states = [s for s in self.agents.values() if s.role == "buyer"]

        def avg_expected(states: list[MWUState]) -> float:
            if not states:
                return 0.0
            return sum(s.expected_price for s in states) / len(states)

        def avg_entropy(states: list[MWUState]) -> float:
            if not states:
                return 0.0
            return sum(s.entropy for s in states) / len(states)

        def avg_regret(states: list[MWUState]) -> float:
            if not states:
                return 0.0
            return sum(s.regret for s in states) / len(states)

        seller_exp = avg_expected(seller_states)
        buyer_exp = avg_expected(buyer_states)

        return {
            "seller_expected_price": round(seller_exp, 6),
            "buyer_expected_price": round(buyer_exp, 6),
            "price_spread": round(abs(buyer_exp - seller_exp), 6),
            "seller_avg_entropy": round(avg_entropy(seller_states), 4),
            "buyer_avg_entropy": round(avg_entropy(buyer_states), 4),
            "seller_avg_regret": round(avg_regret(seller_states), 6),
            "buyer_avg_regret": round(avg_regret(buyer_states), 6),
            "convergence_pct": round(
                max(0.0, 1.0 - avg_entropy(seller_states + buyer_states) / math.log(NUM_SLOTS)) * 100, 1
            ),
            "price_grid": PRICE_GRID,
            "ticks_played": max((s.ticks_played for s in self.agents.values()), default=0),
        }

    def get_agent_distribution(self, agent_id: str) -> Optional[dict]:
        """Get a single agent's learned price distribution for dashboard."""
        state = self.agents.get(agent_id)
        if state is None:
            return None
        return {
            "agent_id": agent_id,
            "role": state.role,
            "probabilities": [round(p, 4) for p in state.probabilities],
            "expected_price": round(state.expected_price, 6),
            "entropy": round(state.entropy, 4),
            "regret": round(state.regret, 6),
            "ticks_played": state.ticks_played,
            "last_matched": state.last_matched,
            "price_grid": PRICE_GRID,
        }

    def get_all_distributions(self) -> list[dict]:
        """All agent distributions for dashboard heatmap."""
        return [self.get_agent_distribution(aid) for aid in self.agents]
