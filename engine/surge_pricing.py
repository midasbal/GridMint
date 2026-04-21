"""Surge Pricing Oracle - Algorithmic dynamic pricing based on supply/demand.

Replaces static agent prices with a market-responsive pricing algorithm.
Solar agents adjust prices based on grid surplus/deficit ratio.
Consumers adjust willingness-to-pay based on urgency and scarcity.
Battery agents use EWMA price tracking with standard deviation bands.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field


@dataclass
class GridConditions:
    """Summary of grid supply/demand balance for pricing decisions."""

    total_supply_kwh: float = 0.0
    total_demand_kwh: float = 0.0
    clearing_price: float = 0.0
    sim_hour: float = 12.0

    @property
    def surplus_ratio(self) -> float:
        """Positive = surplus, negative = deficit. Range roughly -1 to +1."""
        total = self.total_supply_kwh + self.total_demand_kwh
        if total < 0.0001:
            return 0.0
        return (self.total_supply_kwh - self.total_demand_kwh) / total

    @property
    def scarcity_factor(self) -> float:
        """0.0 = abundant supply, 1.0 = extreme scarcity."""
        return max(0.0, min(1.0, -self.surplus_ratio))


class SurgePricingOracle:
    """Computes dynamic prices for solar and consumer agents.

    Solar pricing:
        price = base_price * (1 + alpha * scarcity_factor) * time_multiplier
        - Prices rise when demand exceeds supply
        - Evening premium when solar output drops

    Consumer willingness-to-pay:
        max_price = base_max * (1 + beta * scarcity_factor) * urgency
        - Consumers pay more during scarcity
        - Urgency factor models critical loads

    This creates a self-regulating market where prices signal real conditions.
    """

    # Tuning parameters
    SOLAR_ALPHA = 2.0       # Price sensitivity to scarcity (0=static, 3=aggressive)
    CONSUMER_BETA = 1.5     # Willingness-to-pay sensitivity to scarcity
    EVENING_PREMIUM = 1.8   # Price multiplier during evening peak (17-22h)
    NIGHT_PREMIUM = 2.5     # Price multiplier during night (22-6h, battery-only supply)
    EWMA_ALPHA = 0.3        # Smoothing factor for EWMA (higher = more responsive)

    def __init__(self):
        self.conditions = GridConditions()
        self.price_history: deque[float] = deque(maxlen=50)
        # O(1) incremental EWMA and exponentially-weighted variance
        self._ewma: float = 0.004       # Initial estimate
        self._ew_var: float = 0.000001   # Initial variance estimate
        self._ewma_initialized: bool = False

    def update_conditions(
        self,
        total_supply: float,
        total_demand: float,
        clearing_price: float,
        sim_hour: float,
    ) -> GridConditions:
        """Update grid conditions after each tick. Called by GridEngine."""
        self.conditions = GridConditions(
            total_supply_kwh=total_supply,
            total_demand_kwh=total_demand,
            clearing_price=clearing_price,
            sim_hour=sim_hour,
        )
        if clearing_price > 0:
            self.price_history.append(clearing_price)
            # O(1) incremental EWMA update: ewma = alpha * new + (1-alpha) * old
            a = self.EWMA_ALPHA
            if not self._ewma_initialized:
                self._ewma = clearing_price
                self._ew_var = 0.000001
                self._ewma_initialized = True
            else:
                delta = clearing_price - self._ewma
                self._ewma = a * clearing_price + (1 - a) * self._ewma
                # Exponentially-weighted variance: var = (1-a) * (old_var + a * delta^2)
                self._ew_var = (1 - a) * (self._ew_var + a * delta * delta)
        return self.conditions

    def _time_of_day_multiplier(self, sim_hour: float) -> float:
        """Smooth price multiplier based on time of day.
        Uses Gaussian blending instead of hard step boundaries."""
        # Night premium: broad Gaussian centered at 2:00 (wrapping around midnight)
        night_hour = sim_hour if sim_hour <= 12 else sim_hour - 24.0
        night_weight = math.exp(-0.5 * ((night_hour - 2.0) / 4.0) ** 2)
        # Evening premium: Gaussian centered at 19:30
        evening_weight = math.exp(-0.5 * ((sim_hour - 19.5) / 2.0) ** 2)
        # Midday discount: Gaussian centered at 12:30
        midday_weight = math.exp(-0.5 * ((sim_hour - 12.5) / 2.5) ** 2)

        # Blend: start at 1.0, add weighted premiums/discounts
        mult = 1.0
        mult += (self.NIGHT_PREMIUM - 1.0) * night_weight
        mult += (self.EVENING_PREMIUM - 1.0) * evening_weight
        mult += (0.8 - 1.0) * midday_weight  # -0.2 discount at peak solar
        return max(mult, 0.5)  # floor at 0.5x

    def solar_price(self, base_price: float, sim_hour: float) -> float:
        """Dynamic price for a solar producer."""
        scarcity = self.conditions.scarcity_factor
        time_mult = self._time_of_day_multiplier(sim_hour)
        price = base_price * (1.0 + self.SOLAR_ALPHA * scarcity) * time_mult
        # Clamp to sub-cent (hackathon requirement)
        return round(min(price, 0.0099), 6)

    def consumer_max_price(self, base_max: float, sim_hour: float) -> float:
        """Dynamic willingness-to-pay for a consumer."""
        scarcity = self.conditions.scarcity_factor
        time_mult = self._time_of_day_multiplier(sim_hour)
        price = base_max * (1.0 + self.CONSUMER_BETA * scarcity) * time_mult
        return round(min(price, 0.0099), 6)

    @property
    def price_ewma(self) -> float:
        """O(1) exponentially weighted moving average of clearing prices.
        Updated incrementally in update_conditions(), not recomputed."""
        return self._ewma

    @property
    def price_stddev(self) -> float:
        """O(1) exponentially weighted standard deviation of clearing prices.
        Derived from incrementally updated EW variance."""
        return math.sqrt(max(self._ew_var, 1e-12))

    def battery_should_buy(self, buy_threshold: float) -> bool:
        """Battery buys when price is below EWMA - 1 stddev."""
        return self.conditions.clearing_price < (self.price_ewma - self.price_stddev)

    def battery_should_sell(self, sell_threshold: float) -> bool:
        """Battery sells when price is above EWMA + 1 stddev."""
        return self.conditions.clearing_price > (self.price_ewma + self.price_stddev)

    @property
    def summary(self) -> dict:
        """Summary for dashboard display."""
        time_mult = self._time_of_day_multiplier(self.conditions.sim_hour)
        scarcity = self.conditions.scarcity_factor
        
        # Determine zone based on scarcity
        if scarcity > 0.6:
            zone = "Critical"
        elif scarcity > 0.3:
            zone = "High"
        elif scarcity > 0.1:
            zone = "Moderate"
        else:
            zone = "Normal"
        
        return {
            "current_multiplier": round(time_mult, 2),
            "zone": zone,
            "stress_index": round(scarcity, 2),
            "surge_active": scarcity > 0.1,
            "surplus_ratio": round(self.conditions.surplus_ratio, 4),
            "scarcity_factor": round(self.conditions.scarcity_factor, 4),
            "time_multiplier": round(time_mult, 4),
            "price_ewma": round(self.price_ewma, 6),
            "price_stddev": round(self.price_stddev, 6),
            "total_supply_kwh": round(self.conditions.total_supply_kwh, 4),
            "total_demand_kwh": round(self.conditions.total_demand_kwh, 4),
        }
