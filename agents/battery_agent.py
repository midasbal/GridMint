"""Battery agent with autonomous price-reactive arbitrage logic."""

from __future__ import annotations

from typing import Optional

from agents import AgentState, AgentType, EnergyDemand, EnergyOffer
from agents.base_agent import BaseAgent

# Realistic home battery (e.g., Tesla Powerwall)
DEFAULT_CAPACITY_KWH = 13.5
DEFAULT_MAX_CHARGE_RATE_KW = 5.0
DEFAULT_MIN_SOC = 0.1  # Never drain below 10%
DEFAULT_MAX_SOC = 0.95  # Never charge above 95%
DEFAULT_ROUND_TRIP_EFF = 0.90  # 90% round-trip efficiency (Li-ion typical)

# Arbitrage thresholds
DEFAULT_BUY_THRESHOLD_USD = 0.003   # Buy energy when price <= $0.003/kWh
DEFAULT_SELL_THRESHOLD_USD = 0.006  # Sell energy when price >= $0.006/kWh


class BatteryAgent(BaseAgent):
    """Simulates a home battery that autonomously arbitrages energy prices.

    Strategy:
        - BUY when grid clearing price < buy_threshold AND soc < max_soc
        - SELL when grid clearing price > sell_threshold AND soc > min_soc
        - HOLD otherwise

    The battery makes autonomous economic decisions with real USDC.
    """

    def __init__(
        self,
        agent_id: str,
        capacity_kwh: float = DEFAULT_CAPACITY_KWH,
        max_charge_rate_kw: float = DEFAULT_MAX_CHARGE_RATE_KW,
        initial_soc: float = 0.5,
        buy_threshold: float = DEFAULT_BUY_THRESHOLD_USD,
        sell_threshold: float = DEFAULT_SELL_THRESHOLD_USD,
        round_trip_efficiency: float = DEFAULT_ROUND_TRIP_EFF,
        wallet_address: Optional[str] = None,
        private_key: Optional[str] = None,
    ):
        super().__init__(agent_id, AgentType.BATTERY, wallet_address, private_key)
        self.capacity_kwh = capacity_kwh
        self.max_charge_rate_kw = max_charge_rate_kw
        self.soc = initial_soc  # 0.0 to 1.0
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold
        # Split round-trip efficiency equally between charge and discharge:
        # sqrt(0.90) ~ 0.9487 each way, so charge*discharge = 0.90
        self._one_way_eff = round_trip_efficiency ** 0.5

        # Track arbitrage P&L
        self.avg_buy_price: float = 0.0
        self._total_buy_cost: float = 0.0
        self._total_buy_kwh: float = 0.0

    @property
    def stored_kwh(self) -> float:
        return self.soc * self.capacity_kwh

    @property
    def available_capacity_kwh(self) -> float:
        return (DEFAULT_MAX_SOC - self.soc) * self.capacity_kwh

    @property
    def dischargeable_kwh(self) -> float:
        return (self.soc - DEFAULT_MIN_SOC) * self.capacity_kwh

    def update_clearing_price(self, clearing_price: float) -> None:
        """Called by the grid engine each tick with the current clearing price.
        Battery uses this to decide buy/sell/hold for the NEXT tick."""
        self._last_clearing_price = clearing_price

    def charge(self, kwh: float, price_usd_per_kwh: float) -> None:
        """Charge the battery (after a successful purchase).
        Applies one-way efficiency loss: only eff * kwh is actually stored."""
        stored = min(kwh * self._one_way_eff, self.available_capacity_kwh)
        self.soc += stored / self.capacity_kwh
        # Track cost against PURCHASED kwh (buyer paid for full kwh)
        self._total_buy_cost += kwh * price_usd_per_kwh
        self._total_buy_kwh += kwh
        if self._total_buy_kwh > 0:
            self.avg_buy_price = self._total_buy_cost / self._total_buy_kwh

    def discharge(self, kwh: float) -> float:
        """Discharge the battery (after a successful sale).
        Applies one-way efficiency loss: must drain kwh/eff from SOC to deliver kwh.
        Returns actual kWh delivered to buyer."""
        # To deliver `kwh` to the grid, we must drain kwh / eff from storage
        drain = kwh / self._one_way_eff
        actual_drain = min(drain, self.dischargeable_kwh)
        self.soc -= actual_drain / self.capacity_kwh
        return actual_drain * self._one_way_eff  # what buyer actually receives

    def set_oracle(self, oracle) -> None:
        """Attach a SurgePricingOracle for EWMA-based buy/sell decisions."""
        self._oracle = oracle

    def set_gemini(self, gemini) -> None:
        """Attach GeminiBrain for AI-powered trading decisions."""
        self._gemini = gemini
        self._gemini_decision: Optional[str] = None  # last Gemini action
        self._gemini_reasoning: str = ""

    @property
    def gemini_mode(self) -> bool:
        """True if Gemini brain is attached and available."""
        brain = getattr(self, "_gemini", None)
        return brain is not None and brain.available

    async def ask_gemini(self) -> None:
        """Ask Gemini for a trade decision. Called async between ticks."""
        brain = getattr(self, "_gemini", None)
        if not brain or not brain.available:
            return
        decision = await brain.analyze_trade(
            agent_id=self.agent_id,
            soc=self.soc,
            capacity_kwh=self.capacity_kwh,
            avg_buy_price=self.avg_buy_price,
            buy_threshold=self.buy_threshold,
            sell_threshold=self.sell_threshold,
        )
        self._gemini_decision = decision.action
        self._gemini_reasoning = decision.reasoning

    def get_offer(self, tick: int, sim_hour: float) -> Optional[EnergyOffer]:
        """Sell stored energy when clearing price exceeds sell threshold."""
        if self.status.value == "offline":
            return None
        # Gemini override: if Gemini says "hold" or "buy", don't sell
        gemini_action = getattr(self, "_gemini_decision", None)
        if gemini_action is not None:
            if gemini_action != "sell":
                return None
        else:
            # Fallback to oracle/threshold logic
            oracle = getattr(self, "_oracle", None)
            if oracle:
                if not oracle.battery_should_sell(self.sell_threshold):
                    return None
            else:
                price = getattr(self, "_last_clearing_price", 0.0)
                if price < self.sell_threshold:
                    return None
        dischargeable = self.dischargeable_kwh
        # Convert charge rate (kW) to energy per tick (kWh)
        max_energy = self.max_charge_rate_kw * self.tick_duration_hours
        sell_amount = min(dischargeable, max_energy)
        if sell_amount <= 0.0001:
            return None
        return EnergyOffer(
            agent_id=self.agent_id,
            amount_kwh=round(sell_amount, 6),
            price_usd_per_kwh=self.sell_threshold,
            tick=tick,
        )

    def get_demand(self, tick: int, sim_hour: float) -> Optional[EnergyDemand]:
        """Buy energy to charge when clearing price is below buy threshold."""
        if self.status.value == "offline":
            return None
        # Gemini override: if Gemini says "hold" or "sell", don't buy
        gemini_action = getattr(self, "_gemini_decision", None)
        if gemini_action is not None:
            if gemini_action != "buy":
                return None
        else:
            # Fallback to oracle/threshold logic
            oracle = getattr(self, "_oracle", None)
            if oracle:
                if not oracle.battery_should_buy(self.buy_threshold):
                    return None
            else:
                price = getattr(self, "_last_clearing_price", self.buy_threshold)
                if price > self.buy_threshold:
                    return None
        available = self.available_capacity_kwh
        # Convert charge rate (kW) to energy per tick (kWh)
        max_energy = self.max_charge_rate_kw * self.tick_duration_hours
        buy_amount = min(available, max_energy)
        if buy_amount <= 0.0001:
            return None
        return EnergyDemand(
            agent_id=self.agent_id,
            amount_kwh=round(buy_amount, 6),
            max_price_usd_per_kwh=self.buy_threshold,
            tick=tick,
        )

    def get_state(self, tick: int, sim_hour: float) -> AgentState:
        return AgentState(
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            status=self.status,
            wallet_address=self.wallet_address,
            erc8004_token_id=self.erc8004_token_id,
            battery_soc=round(self.soc, 4),
            battery_capacity_kwh=self.capacity_kwh,
            total_earned_usd=self.total_earned_usd,
            total_spent_usd=self.total_spent_usd,
            total_energy_sold_kwh=self.total_energy_sold_kwh,
            total_energy_bought_kwh=self.total_energy_bought_kwh,
            tx_count=self.tx_count,
        )
