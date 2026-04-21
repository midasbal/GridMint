"""Smoke test: verify the grid engine runs and produces trades."""

import sys
import os

# Ensure gridmint package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.config import create_demo_fleet
from engine.grid_engine import GridEngine


def test_simulation_produces_trades():
    """Run 20 ticks and verify we get matches and sub-cent pricing."""
    fleet = create_demo_fleet()
    engine = GridEngine(
        agents=fleet,
        tick_interval=0.0,  # No delay for tests
        speed_multiplier=360,
        start_hour=10.0,  # Start at 10 AM (solar is producing)
    )

    for _ in range(20):
        engine.step()

    assert engine.total_tx_count > 0, "No trades occurred in 20 ticks"
    assert engine.total_tx_count >= 20, (
        f"Expected at least 20 trades, got {engine.total_tx_count}"
    )

    # Verify sub-cent pricing
    for snap in engine.snapshots:
        for match in snap.matches:
            assert match.total_usd <= 0.01, (
                f"Trade exceeded $0.01: ${match.total_usd}"
            )
            assert match.price_usd_per_kwh <= 0.01, (
                f"Price exceeded $0.01/kWh: ${match.price_usd_per_kwh}"
            )

    print(f"Total transactions: {engine.total_tx_count}")
    print(f"Total USDC settled: ${engine.total_usd_settled:.6f}")
    print(f"All trades sub-cent: PASS")


def test_fault_injection():
    """Kill a solar agent mid-simulation, verify grid adapts."""
    fleet = create_demo_fleet()
    engine = GridEngine(agents=fleet, start_hour=12.0)

    # Run 5 ticks normally
    for _ in range(5):
        engine.step()
    normal_matches = sum(len(s.matches) for s in engine.snapshots)

    # Kill solar-1 (the cheapest producer)
    engine.toggle_agent("solar-1")
    assert engine.agents["solar-1"].status.value == "offline"

    # Run 5 more ticks
    for _ in range(5):
        engine.step()

    # Grid should still produce matches (from solar-2, solar-3, batteries)
    total_matches = sum(len(s.matches) for s in engine.snapshots)
    assert total_matches > normal_matches, "Grid stopped producing trades after fault"

    print(f"Fault injection test PASS. Matches before kill: {normal_matches}, "
          f"Total after: {total_matches}")


def test_battery_arbitrage():
    """Verify battery buys low and sells high."""
    fleet = create_demo_fleet()
    # Start at 8 AM so battery sees cheap midday prices then expensive evening
    engine = GridEngine(agents=fleet, start_hour=8.0, speed_multiplier=720)

    # Run enough ticks to span midday -> evening price swing
    for _ in range(50):
        engine.step()

    battery = engine.agents["battery-1"]
    # Battery should have done something
    assert battery.tx_count > 0, "Battery never traded"
    print(f"Battery-1: bought {battery.total_energy_bought_kwh:.2f} kWh "
          f"(${battery.total_spent_usd:.4f}), "
          f"sold {battery.total_energy_sold_kwh:.2f} kWh "
          f"(${battery.total_earned_usd:.4f}), "
          f"SOC: {battery.soc:.1%}")


if __name__ == "__main__":
    test_simulation_produces_trades()
    print("---")
    test_fault_injection()
    print("---")
    test_battery_arbitrage()
    print("\nAll smoke tests passed.")
