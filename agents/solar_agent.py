"""Solar panel agent with realistic irradiance-based production model."""

from __future__ import annotations

import math
from typing import Optional

from agents import AgentState, AgentType, EnergyDemand, EnergyOffer
from agents.base_agent import BaseAgent

# Realistic defaults for a residential solar installation
DEFAULT_CAPACITY_KW = 5.0       # Nameplate DC rating (accounts for cell efficiency at STC)
DEFAULT_TEMP_COEFF = -0.004     # Power derating per degree C above 25C (typical Si cell)
DEFAULT_INVERTER_CLIP = 0.95    # Inverter clips at 95% of nameplate to prevent overload
DEFAULT_PEAK_IRRADIANCE = 1.0   # kW/m^2 (STC reference irradiance)
SUNRISE_HOUR = 6.0
SUNSET_HOUR = 20.0
DAYLIGHT_HOURS = SUNSET_HOUR - SUNRISE_HOUR

# Pricing: competitive residential solar LCOE
BASE_PRICE_USD_PER_KWH = 0.003  # $0.003/kWh -> sub-cent


class SolarAgent(BaseAgent):
    """Simulates a solar panel that produces energy following a bell curve
    based on time-of-day irradiance and sells surplus at sub-cent prices.

    Production formula (physically correct):
        irradiance(t) = max(0, sin(pi * (t - sunrise) / daylight)) * peak_irradiance
        power_kw(t) = min(capacity_kw * irradiance / STC, inverter_clip * capacity_kw)
        temp_derate(t) = 1 + temp_coeff * (cell_temp(t) - 25)
        energy_kwh(t) = power_kw * temp_derate * tick_duration_hours

    capacity_kw is the nameplate DC rating at STC (1.0 kW/m^2, 25C),
    so we do NOT multiply by cell efficiency (that's already baked into nameplate).
    """

    def __init__(
        self,
        agent_id: str,
        capacity_kw: float = DEFAULT_CAPACITY_KW,
        temp_coeff: float = DEFAULT_TEMP_COEFF,
        inverter_clip: float = DEFAULT_INVERTER_CLIP,
        price_usd_per_kwh: float = BASE_PRICE_USD_PER_KWH,
        wallet_address: Optional[str] = None,
        private_key: Optional[str] = None,
    ):
        super().__init__(agent_id, AgentType.SOLAR, wallet_address, private_key)
        self.capacity_kw = capacity_kw
        self.temp_coeff = temp_coeff
        self.inverter_clip = inverter_clip
        self.base_price = price_usd_per_kwh
        self.price_usd_per_kwh = price_usd_per_kwh  # dynamic, updated each tick

    def _irradiance(self, sim_hour: float) -> float:
        """Solar irradiance as a sine curve between sunrise and sunset (kW/m^2)."""
        if sim_hour < SUNRISE_HOUR or sim_hour > SUNSET_HOUR:
            return 0.0
        progress = (sim_hour - SUNRISE_HOUR) / DAYLIGHT_HOURS
        return max(0.0, math.sin(math.pi * progress)) * DEFAULT_PEAK_IRRADIANCE

    def _cell_temperature(self, sim_hour: float) -> float:
        """Approximate cell temperature using NOCT model (simplified).
        Ambient follows a sine curve peaking at 14:00, cell temp ~30C above ambient."""
        ambient = 15.0 + 15.0 * max(0.0, math.sin(math.pi * (sim_hour - 6.0) / 16.0))
        irr = self._irradiance(sim_hour)
        # NOCT approximation: cell_temp = ambient + irradiance * 30
        return ambient + irr * 30.0

    def _production_kwh(self, sim_hour: float) -> float:
        """Energy produced this tick in kWh (dimensionally correct).

        power = capacity_kw * (irradiance / STC_irradiance)  [no double-counting efficiency]
        power = min(power, inverter_clip * capacity_kw)       [inverter clipping]
        power *= (1 + temp_coeff * (cell_temp - 25))          [temperature derating]
        energy = power * tick_duration_hours                   [kW * h = kWh]
        """
        irr = self._irradiance(sim_hour)
        if irr <= 0.0:
            return 0.0
        # DC power proportional to irradiance ratio vs STC
        power = self.capacity_kw * (irr / DEFAULT_PEAK_IRRADIANCE)
        # Inverter clipping
        power = min(power, self.inverter_clip * self.capacity_kw)
        # Temperature derating
        cell_temp = self._cell_temperature(sim_hour)
        temp_factor = 1.0 + self.temp_coeff * (cell_temp - 25.0)
        power *= max(temp_factor, 0.0)
        # Convert power (kW) to energy (kWh) using tick duration
        return power * self.tick_duration_hours

    def set_oracle(self, oracle) -> None:
        """Attach a SurgePricingOracle for dynamic pricing."""
        self._oracle = oracle

    def set_schelling(self, schelling) -> None:
        """Attach SchellingEngine for game-theoretic price discovery."""
        self._schelling = schelling

    def get_offer(self, tick: int, sim_hour: float) -> Optional[EnergyOffer]:
        if self.status.value == "offline":
            return None
        output = self._production_kwh(sim_hour)
        if output <= 0.0001:
            return None
        # Price priority: Schelling > Oracle > base_price
        schelling = getattr(self, "_schelling", None)
        oracle = getattr(self, "_oracle", None)
        if schelling:
            price = schelling.choose_price(self.agent_id)
        elif oracle:
            price = oracle.solar_price(self.base_price, sim_hour)
        else:
            price = self.price_usd_per_kwh
        self.price_usd_per_kwh = price  # update for state reporting
        return EnergyOffer(
            agent_id=self.agent_id,
            amount_kwh=round(output, 6),
            price_usd_per_kwh=price,
            tick=tick,
        )

    def get_demand(self, tick: int, sim_hour: float) -> Optional[EnergyDemand]:
        return None  # Solar panels only produce

    def get_state(self, tick: int, sim_hour: float) -> AgentState:
        return AgentState(
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            status=self.status,
            wallet_address=self.wallet_address,
            erc8004_token_id=self.erc8004_token_id,
            current_production_kwh=self._production_kwh(sim_hour),
            total_earned_usd=self.total_earned_usd,
            total_energy_sold_kwh=self.total_energy_sold_kwh,
            tx_count=self.tx_count,
        )
