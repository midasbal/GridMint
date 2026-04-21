"""GridMint Agent Models - Core data structures for all grid devices."""

from __future__ import annotations

import math
import time
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AgentType(str, Enum):
    SOLAR = "solar"
    CONSUMER = "consumer"
    BATTERY = "battery"


class AgentStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"


class EnergyOffer(BaseModel):
    """An offer to sell energy on the grid."""

    agent_id: str
    amount_kwh: float = Field(ge=0, description="Energy available in kWh")
    price_usd_per_kwh: float = Field(ge=0, description="Asking price in USD/kWh")
    tick: int


class EnergyDemand(BaseModel):
    """A request to buy energy from the grid."""

    agent_id: str
    amount_kwh: float = Field(ge=0, description="Energy needed in kWh")
    max_price_usd_per_kwh: float = Field(ge=0, description="Max willingness to pay")
    tick: int


class TradeMatch(BaseModel):
    """A matched trade between a producer and consumer."""

    seller_id: str
    buyer_id: str
    amount_kwh: float
    price_usd_per_kwh: float
    total_usd: float
    tick: int
    tx_hash: Optional[str] = None
    settled: bool = False


class AgentState(BaseModel):
    """Snapshot of an agent's current state."""

    agent_id: str
    agent_type: AgentType
    status: AgentStatus = AgentStatus.ONLINE
    wallet_address: Optional[str] = None
    erc8004_token_id: Optional[int] = None

    # Energy state
    current_production_kwh: float = 0.0
    current_consumption_kwh: float = 0.0
    battery_soc: float = 0.0  # state of charge 0.0-1.0 (batteries only)
    battery_capacity_kwh: float = 0.0

    # Economics
    total_earned_usd: float = 0.0
    total_spent_usd: float = 0.0
    total_energy_sold_kwh: float = 0.0
    total_energy_bought_kwh: float = 0.0
    tx_count: int = 0


class GridSnapshot(BaseModel):
    """Full grid state at a single tick."""

    tick: int
    sim_hour: float
    timestamp: float = Field(default_factory=time.time)
    agents: list[AgentState]
    offers: list[EnergyOffer]
    demands: list[EnergyDemand]
    matches: list[TradeMatch]
    clearing_price_usd: float = 0.0
    total_tx_count: int = 0
    total_usd_settled: float = 0.0
