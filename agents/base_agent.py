"""Base agent class with ERC-8004 identity and wallet integration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from agents import AgentState, AgentStatus, AgentType, EnergyDemand, EnergyOffer


class BaseAgent(ABC):
    """Abstract base for all GridMint device agents.

    Every agent has:
    - A deterministic energy model (production or consumption)
    - A wallet address for USDC settlement on Arc
    - An ERC-8004 on-chain identity (registered in IdentityRegistry)
    """

    def __init__(
        self,
        agent_id: str,
        agent_type: AgentType,
        wallet_address: Optional[str] = None,
        private_key: Optional[str] = None,
    ):
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.wallet_address = wallet_address
        self.private_key = private_key
        self.status = AgentStatus.ONLINE

        # Tick duration in hours — set by GridEngine at init.
        # Default 0.3h = 18 simulated minutes (3s tick * 360x speed).
        self.tick_duration_hours: float = 0.3

        # Cumulative economics
        self.total_earned_usd: float = 0.0
        self.total_spent_usd: float = 0.0
        self.total_energy_sold_kwh: float = 0.0
        self.total_energy_bought_kwh: float = 0.0
        self.tx_count: int = 0

        # ERC-8004 identity
        self.erc8004_token_id: Optional[int] = None

    @abstractmethod
    def get_offer(self, tick: int, sim_hour: float) -> Optional[EnergyOffer]:
        """Return an energy sell offer for this tick, or None."""
        ...

    @abstractmethod
    def get_demand(self, tick: int, sim_hour: float) -> Optional[EnergyDemand]:
        """Return an energy buy demand for this tick, or None."""
        ...

    @abstractmethod
    def get_state(self, tick: int, sim_hour: float) -> AgentState:
        """Return the full state snapshot."""
        ...

    def record_sale(self, amount_kwh: float, total_usd: float) -> None:
        self.total_earned_usd += total_usd
        self.total_energy_sold_kwh += amount_kwh
        self.tx_count += 1

    def record_purchase(self, amount_kwh: float, total_usd: float) -> None:
        self.total_spent_usd += total_usd
        self.total_energy_bought_kwh += amount_kwh
        self.tx_count += 1

    def set_offline(self) -> None:
        self.status = AgentStatus.OFFLINE

    def set_online(self) -> None:
        self.status = AgentStatus.ONLINE
