"""Wallet Generation & Funding Helper for GridMint agents.

Generates 10 Ethereum-compatible wallets for all GridMint agents,
writes private keys to .env, and prints addresses for Circle faucet funding.

Usage:
    python scripts/setup_wallets.py          # Generate new wallets
    python scripts/setup_wallets.py --check  # Check balances of existing wallets
"""

from __future__ import annotations

import os
import sys

# Add parent dir so we can import from engine/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv, set_key
from eth_account import Account

load_dotenv()

# Agent ID → .env key mapping
AGENT_KEYS = {
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

ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")
FAUCET_URL = "https://faucet.circle.com"


def generate_wallets():
    """Generate wallets for all agents and save to .env."""
    print("=" * 70)
    print("GridMint Wallet Generator")
    print("=" * 70)
    print()

    wallets: dict[str, tuple[str, str]] = {}  # agent_id -> (address, private_key)

    for agent_id, env_key in AGENT_KEYS.items():
        existing = os.getenv(env_key, "").strip()
        if existing:
            acct = Account.from_key(existing)
            wallets[agent_id] = (acct.address, existing)
            print(f"  ✅ {agent_id:15s} → {acct.address}  (existing)")
        else:
            acct = Account.create()
            key_hex = acct.key.hex()
            wallets[agent_id] = (acct.address, key_hex)
            set_key(ENV_PATH, env_key, key_hex)
            print(f"  🆕 {agent_id:15s} → {acct.address}  (generated)")

    print()
    print("=" * 70)
    print("FAUCET FUNDING INSTRUCTIONS")
    print(f"Go to {FAUCET_URL} and fund each address with testnet USDC.")
    print("Select: Network = Arc Testnet, Token = USDC")
    print("=" * 70)
    print()

    for agent_id, (addr, _) in wallets.items():
        print(f"  {addr}   ← {agent_id}")

    print()
    print(f"Total wallets: {len(wallets)}")
    print("Fund each with ~$1.00 testnet USDC (we spend ~$0.25 total in 50 ticks).")
    print()
    return wallets


def check_balances():
    """Check USDC balances of all agent wallets on Arc Testnet."""
    from web3 import Web3

    rpc = os.getenv("ARC_RPC_URL", "https://rpc.testnet.arc.network")
    usdc_addr = os.getenv("USDC_CONTRACT_ADDRESS", "0x3600000000000000000000000000000000000000")
    explorer = os.getenv("ARC_EXPLORER_URL", "https://testnet.arcscan.app")

    w3 = Web3(Web3.HTTPProvider(rpc))
    if not w3.is_connected():
        print("❌ Cannot connect to Arc Testnet RPC!")
        return

    print(f"Connected to Arc Testnet (chain {w3.eth.chain_id})")
    print()

    erc20_abi = [
        {
            "name": "balanceOf",
            "type": "function",
            "inputs": [{"name": "account", "type": "address"}],
            "outputs": [{"name": "", "type": "uint256"}],
        }
    ]
    usdc = w3.eth.contract(address=Web3.to_checksum_address(usdc_addr), abi=erc20_abi)

    total_usdc = 0.0
    funded = 0

    for agent_id, env_key in AGENT_KEYS.items():
        pk = os.getenv(env_key, "").strip()
        if not pk:
            print(f"  ⚠️  {agent_id:15s} → No private key in .env")
            continue
        acct = Account.from_key(pk)
        addr = acct.address
        try:
            raw = usdc.functions.balanceOf(Web3.to_checksum_address(addr)).call()
            balance = raw / 1_000_000
            total_usdc += balance
            status = "✅" if balance > 0.01 else "❌"
            if balance > 0.01:
                funded += 1
            print(f"  {status} {agent_id:15s} → {addr}  ${balance:.6f} USDC")
        except Exception as e:
            print(f"  ❌ {agent_id:15s} → {addr}  Error: {e}")

    print()
    print(f"Total USDC across {len(AGENT_KEYS)} wallets: ${total_usdc:.6f}")
    print(f"Funded wallets: {funded}/{len(AGENT_KEYS)}")
    if funded < len(AGENT_KEYS):
        print(f"\n⚠️  Fund remaining wallets at {FAUCET_URL}")
        print(f"   View on explorer: {explorer}")


if __name__ == "__main__":
    if "--check" in sys.argv:
        check_balances()
    else:
        generate_wallets()
