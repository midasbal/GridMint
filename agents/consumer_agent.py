"""Consumer (house) agent with occupancy-driven demand model."""

from __future__ import annotations

import math
import random
from typing import Optional

from agents import AgentState, AgentType, EnergyDemand, EnergyOffer
from agents.base_agent import BaseAgent

# Realistic residential load profile
DEFAULT_BASE_LOAD_KW = 0.4  # Always-on (fridge, standby, etc.)
DEFAULT_APPLIANCE_LOAD_KW = 1.8  # Active appliances
DEFAULT_MAX_PRICE_USD_PER_KWH = 0.008  # Willing to pay up to $0.008/kWh
NOISE_FACTOR = 0.05  # +/- 5% random variation


class ConsumerAgent(BaseAgent):
    """Simulates a household with time-varying electricity demand.

    Demand formula (dimensionally correct):
        occupancy(t) = 0.3 + 0.7 * max(gaussian_peak(7h), gaussian_peak(19h))
        power_kw(t) = base_load + occupancy(t) * appliance_load * (1 + noise)
        demand_kwh(t) = power_kw(t) * tick_duration_hours

    Morning peak at 7:00, evening peak at 19:00. Low during work hours.
    Uses max() not addition to prevent occupancy exceeding 1.0.
    """

    def __init__(
        self,
        agent_id: str,
        base_load_kw: float = DEFAULT_BASE_LOAD_KW,
        appliance_load_kw: float = DEFAULT_APPLIANCE_LOAD_KW,
        max_price: float = DEFAULT_MAX_PRICE_USD_PER_KWH,
        wallet_address: Optional[str] = None,
        private_key: Optional[str] = None,
    ):
        super().__init__(agent_id, AgentType.CONSUMER, wallet_address, private_key)
        self.base_load_kw = base_load_kw
        self.appliance_load_kw = appliance_load_kw
        self.max_price = max_price

    def set_oracle(self, oracle) -> None:
        """Attach a SurgePricingOracle for dynamic willingness-to-pay."""
        self._oracle = oracle

    def set_schelling(self, schelling) -> None:
        """Attach SchellingEngine for game-theoretic price discovery."""
        self._schelling = schelling

    def _occupancy_factor(self, sim_hour: float) -> float:
        """Dual-peak occupancy: morning (7h) and evening (19h)."""
        morning = math.exp(-0.5 * ((sim_hour - 7.0) / 1.5) ** 2)
        evening = math.exp(-0.5 * ((sim_hour - 19.0) / 2.0) ** 2)
        return 0.3 + 0.7 * max(morning, evening)

    def _demand_kwh(self, sim_hour: float) -> float:
        """Energy demanded this tick in kWh (dimensionally correct).

        power_kw = base_load + occupancy * appliance_load * noise
        energy_kwh = power_kw * tick_duration_hours
        """
        occupancy = self._occupancy_factor(sim_hour)
        noise = 1.0 + random.uniform(-NOISE_FACTOR, NOISE_FACTOR)
        power_kw = self.base_load_kw + occupancy * self.appliance_load_kw * noise
        return power_kw * self.tick_duration_hours

    def get_offer(self, tick: int, sim_hour: float) -> Optional[EnergyOffer]:
        return None  # Consumers only buy

    def get_demand(self, tick: int, sim_hour: float) -> Optional[EnergyDemand]:
        if self.status.value == "offline":
            return None
        demand = self._demand_kwh(sim_hour)
        if demand <= 0.0001:
            return None
        # Price priority: Schelling > Oracle > max_price
        schelling = getattr(self, "_schelling", None)
        oracle = getattr(self, "_oracle", None)
        if schelling:
            price = schelling.choose_price(self.agent_id)
        elif oracle:
            price = oracle.consumer_max_price(self.max_price, sim_hour)
        else:
            price = self.max_price
        return EnergyDemand(
            agent_id=self.agent_id,
            amount_kwh=round(demand, 6),
            max_price_usd_per_kwh=price,
            tick=tick,
        )

    def get_state(self, tick: int, sim_hour: float) -> AgentState:
        return AgentState(
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            status=self.status,
            wallet_address=self.wallet_address,
            erc8004_token_id=self.erc8004_token_id,
            current_consumption_kwh=self._demand_kwh(sim_hour),
            total_spent_usd=self.total_spent_usd,
            total_energy_bought_kwh=self.total_energy_bought_kwh,
            tx_count=self.tx_count,
        )
