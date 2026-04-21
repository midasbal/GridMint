"""Default grid fleet configuration for the GridMint demo."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from eth_account import Account

from agents.battery_agent import BatteryAgent
from agents.consumer_agent import ConsumerAgent
from agents.solar_agent import SolarAgent

load_dotenv()

# Map agent_id -> .env key for private keys
_WALLET_ENV_KEYS = {
    "solar-1": "SOLAR_1_PRIVATE_KEY",
    "solar-2": "SOLAR_2_PRIVATE_KEY",
    "solar-3": "SOLAR_3_PRIVATE_KEY",
    "house-1": "CONSUMER_1_PRIVATE_KEY",
    "house-2": "CONSUMER_2_PRIVATE_KEY",
    "house-3": "CONSUMER_3_PRIVATE_KEY",
    "house-4": "CONSUMER_4_PRIVATE_KEY",
    "house-5": "CONSUMER_5_PRIVATE_KEY",
    "battery-1": "BATTERY_1_PRIVATE_KEY",
    "battery-2": "BATTERY_2_PRIVATE_KEY",
}


def _wallet_for(agent_id: str) -> tuple[str | None, str | None]:
    """Load wallet address and private key from .env for an agent."""
    env_key = _WALLET_ENV_KEYS.get(agent_id)
    if not env_key:
        return None, None
    pk = os.getenv(env_key, "").strip()
    if not pk:
        return None, None
    try:
        acct = Account.from_key(pk)
        return acct.address, pk
    except Exception:
        return None, None


def create_demo_fleet() -> list:
    """Create the default 10-device demo fleet.

    3 solar panels (varying capacities)
    5 consumers (varying load profiles)
    2 batteries (different strategies)

    This fleet generates 5-15 matched trades per tick,
    reaching 50+ total transactions within ~5-10 ticks (~15-30 seconds).
    """

    solars = [
        SolarAgent(
            agent_id="solar-1",
            capacity_kw=12.0,
            price_usd_per_kwh=0.002,
            wallet_address=_wallet_for("solar-1")[0],
            private_key=_wallet_for("solar-1")[1],
        ),
        SolarAgent(
            agent_id="solar-2",
            capacity_kw=10.0,
            price_usd_per_kwh=0.003,
            wallet_address=_wallet_for("solar-2")[0],
            private_key=_wallet_for("solar-2")[1],
        ),
        SolarAgent(
            agent_id="solar-3",
            capacity_kw=15.0,
            price_usd_per_kwh=0.004,
            wallet_address=_wallet_for("solar-3")[0],
            private_key=_wallet_for("solar-3")[1],
        ),
    ]

    consumers = [
        ConsumerAgent(
            agent_id="house-1",
            base_load_kw=0.3,
            appliance_load_kw=1.5,
            max_price=0.008,
            wallet_address=_wallet_for("house-1")[0],
            private_key=_wallet_for("house-1")[1],
        ),
        ConsumerAgent(
            agent_id="house-2",
            base_load_kw=0.5,
            appliance_load_kw=2.0,
            max_price=0.007,
            wallet_address=_wallet_for("house-2")[0],
            private_key=_wallet_for("house-2")[1],
        ),
        ConsumerAgent(
            agent_id="house-3",
            base_load_kw=0.4,
            appliance_load_kw=1.8,
            max_price=0.009,
            wallet_address=_wallet_for("house-3")[0],
            private_key=_wallet_for("house-3")[1],
        ),
        ConsumerAgent(
            agent_id="house-4",
            base_load_kw=0.35,
            appliance_load_kw=1.6,
            max_price=0.006,
            wallet_address=_wallet_for("house-4")[0],
            private_key=_wallet_for("house-4")[1],
        ),
        ConsumerAgent(
            agent_id="house-5",
            base_load_kw=0.45,
            appliance_load_kw=2.2,
            max_price=0.008,
            wallet_address=_wallet_for("house-5")[0],
            private_key=_wallet_for("house-5")[1],
        ),
    ]

    batteries = [
        BatteryAgent(
            agent_id="battery-1",
            capacity_kwh=13.5,
            initial_soc=0.3,
            buy_threshold=0.004,
            sell_threshold=0.006,
            wallet_address=_wallet_for("battery-1")[0],
            private_key=_wallet_for("battery-1")[1],
        ),
        BatteryAgent(
            agent_id="battery-2",
            capacity_kwh=10.0,
            initial_soc=0.3,
            buy_threshold=0.005,
            sell_threshold=0.007,
            wallet_address=_wallet_for("battery-2")[0],
            private_key=_wallet_for("battery-2")[1],
        ),
    ]

    return solars + consumers + batteries
