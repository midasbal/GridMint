#!/usr/bin/env python3
"""
Circle Developer Console Infrastructure Demo

This script demonstrates a USDC transaction using Circle's Arc Testnet infrastructure.
It executes a real on-chain transaction that can be verified on Arc Block Explorer.

Circle Infrastructure Components:
- Arc Testnet blockchain (Circle-managed L1)
- Circle USDC contract (0x3600...)
- Circle Faucet for testnet funding

Requirements:
- Python 3.10+
- web3.py
- DEMO_PRIVATE_KEY in .env (funded wallet from Circle Faucet)
"""

import os
import sys
import time
from pathlib import Path

# Add parent directory to path to import engine modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from web3 import Web3
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ============================================================================
# CIRCLE ARC TESTNET CONFIGURATION
# ============================================================================

# Circle's Arc Testnet infrastructure
ARC_RPC_URL = "https://rpc.testnet.arc.network"
ARC_CHAIN_ID = 5042002
ARC_EXPLORER = "https://testnet.arcscan.app"

# Circle USDC contract on Arc Testnet
CIRCLE_USDC_CONTRACT = "0x3600000000000000000000000000000000000000"

# Recipient: GridMint Gateway wallet
RECIPIENT_ADDRESS = "0x0077777d7EBA4688BDeF3E311b846F25870A19B9"

# Demo transaction amount (1 USDC)
DEMO_AMOUNT_USDC = 1.0

# ERC-20 ABI (minimal - transfer function only)
ERC20_ABI = [
    {
        "name": "transfer",
        "type": "function",
        "inputs": [
            {"name": "to", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "name": "balanceOf",
        "type": "function",
        "inputs": [{"name": "account", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
]


def print_banner():
    """Display Circle branding banner"""
    print("\n" + "━" * 70)
    print("🔵 CIRCLE DEVELOPER CONSOLE INFRASTRUCTURE DEMONSTRATION")
    print("━" * 70)
    print("Purpose:      Hackathon requirement - Circle infrastructure demo")
    print("Network:      Arc Testnet (Circle-managed blockchain)")
    print("RPC:          https://rpc.testnet.arc.network")
    print("USDC:         Circle USDC on Arc (0x3600...)")
    print("Explorer:     https://testnet.arcscan.app")
    print("━" * 70 + "\n")


def print_step(step_num: int, title: str):
    """Print step header"""
    print(f"\n{'═' * 70}")
    print(f"STEP {step_num}: {title}")
    print("═" * 70)


def main():
    print_banner()

    # Validate environment
    private_key = os.getenv("DEMO_PRIVATE_KEY")
    if not private_key:
        print("❌ ERROR: DEMO_PRIVATE_KEY not found in .env")
        print("\nPlease add a funded wallet private key to .env:")
        print("1. Generate a wallet (or use existing)")
        print("2. Fund it at https://faucet.circle.com (Arc Testnet, 10 USDC)")
        print("3. Add to .env: DEMO_PRIVATE_KEY=0x...")
        sys.exit(1)

    # Initialize Web3 connection to Circle's Arc Testnet
    print_step(1, "Connect to Circle's Arc Testnet RPC")
    print(f"Connecting to {ARC_RPC_URL}...")
    
    w3 = Web3(Web3.HTTPProvider(ARC_RPC_URL, request_kwargs={"timeout": 10}))
    
    if not w3.is_connected():
        print("❌ Failed to connect to Arc Testnet RPC")
        sys.exit(1)
    
    block_number = w3.eth.block_number
    print(f"✅ Connected to Circle Arc Testnet")
    print(f"   Chain ID: {ARC_CHAIN_ID}")
    print(f"   Current Block: {block_number:,}")
    print(f"   RPC URL: {ARC_RPC_URL}")

    # Load wallet
    print_step(2, "Load Wallet & Check Circle USDC Balance")
    
    account = w3.eth.account.from_key(private_key)
    sender_address = account.address
    print(f"Wallet Address: {sender_address}")
    
    # Initialize Circle USDC contract
    usdc_contract = w3.eth.contract(
        address=Web3.to_checksum_address(CIRCLE_USDC_CONTRACT),
        abi=ERC20_ABI
    )
    
    # Check USDC balance
    balance_raw = usdc_contract.functions.balanceOf(sender_address).call()
    balance_usdc = balance_raw / 1_000_000  # USDC has 6 decimals
    
    print(f"Circle USDC Balance: {balance_usdc:.6f} USDC")
    print(f"Circle USDC Contract: {CIRCLE_USDC_CONTRACT}")
    
    if balance_usdc < DEMO_AMOUNT_USDC:
        print(f"\n❌ Insufficient USDC balance")
        print(f"   Required: {DEMO_AMOUNT_USDC} USDC")
        print(f"   Available: {balance_usdc:.6f} USDC")
        print(f"\n🚰 Fund your wallet at: https://faucet.circle.com")
        print(f"   Network: Arc Testnet")
        print(f"   Address: {sender_address}")
        sys.exit(1)

    # Build Circle USDC transaction
    print_step(3, "Build Circle USDC Transaction")
    
    amount_units = int(DEMO_AMOUNT_USDC * 1_000_000)  # Convert to 6-decimal units
    
    print(f"Sender:       {sender_address}")
    print(f"Recipient:    {RECIPIENT_ADDRESS}")
    print(f"Amount:       {DEMO_AMOUNT_USDC} USDC")
    print(f"Token:        Circle USDC ({CIRCLE_USDC_CONTRACT})")
    print(f"Blockchain:   Arc Testnet (Circle infrastructure)")
    
    nonce = w3.eth.get_transaction_count(sender_address)
    gas_price = w3.eth.gas_price
    
    # Build transaction
    tx = usdc_contract.functions.transfer(
        Web3.to_checksum_address(RECIPIENT_ADDRESS),
        amount_units
    ).build_transaction({
        "chainId": ARC_CHAIN_ID,
        "from": sender_address,
        "nonce": nonce,
        "gas": 65_000,
        "gasPrice": gas_price,
    })
    
    print(f"\nTransaction Parameters:")
    print(f"   Nonce: {nonce}")
    print(f"   Gas Limit: {tx['gas']:,}")
    print(f"   Gas Price: {gas_price / 10**9:.4f} gwei")

    # Sign and broadcast via Circle's Arc RPC
    print_step(4, "Sign & Broadcast via Circle Arc Testnet")
    
    print("Signing transaction...")
    signed_tx = account.sign_transaction(tx)
    
    print("Broadcasting to Circle Arc Testnet RPC...")
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    tx_hash_hex = tx_hash.hex()
    
    print(f"\n✅ Transaction broadcast successfully!")
    print(f"   Tx Hash: {tx_hash_hex}")
    print(f"   Arc Explorer: {ARC_EXPLORER}/tx/{tx_hash_hex}")

    # Wait for confirmation
    print_step(5, "Wait for On-Chain Confirmation")
    
    print("⏳ Waiting for transaction confirmation...")
    print("   (Arc Testnet has sub-second finality)\n")
    
    start_time = time.time()
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=15)
    confirmation_time = time.time() - start_time
    
    # Calculate gas cost
    gas_used = receipt["gasUsed"]
    gas_cost_wei = gas_used * gas_price
    gas_cost_usd = gas_cost_wei / 10**18  # On Arc, gas is paid in USDC (18 decimals)
    
    # Ethereum comparison
    eth_gas_price_gwei = 20  # Typical Ethereum gas price
    eth_price_usd = 1900  # Approximate ETH price
    eth_gas_cost = (gas_used * eth_gas_price_gwei * eth_price_usd) / 10**9
    savings_factor = eth_gas_cost / gas_cost_usd if gas_cost_usd > 0 else 0
    
    print(f"✅ TRANSACTION CONFIRMED ON CIRCLE ARC TESTNET")
    print(f"{'─' * 70}")
    print(f"Tx Hash:           {tx_hash_hex}")
    print(f"Block Number:      {receipt['blockNumber']:,}")
    print(f"Status:            {'✅ SUCCESS' if receipt['status'] == 1 else '❌ FAILED'}")
    print(f"Gas Used:          {gas_used:,}")
    print(f"Confirmation Time: {confirmation_time:.2f} seconds")
    print(f"\n💰 COST ANALYSIS (Circle Arc vs Ethereum)")
    print(f"{'─' * 70}")
    print(f"Arc Gas Cost:      ${gas_cost_usd:.6f}")
    print(f"Ethereum Cost:     ${eth_gas_cost:.2f}")
    print(f"Savings:           {savings_factor:.0f}× cheaper on Circle Arc")
    print(f"\n🔍 VERIFY ON ARC BLOCK EXPLORER:")
    print(f"{'─' * 70}")
    print(f"{ARC_EXPLORER}/tx/{tx_hash_hex}")
    print(f"\n✅ Circle infrastructure demonstration complete!")
    print(f"{'═' * 70}\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Demo cancelled by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        print("\nTroubleshooting:")
        print("1. Check DEMO_PRIVATE_KEY in .env")
        print("2. Ensure wallet is funded via https://faucet.circle.com")
        print("3. Verify Arc Testnet RPC is accessible")
        sys.exit(1)
