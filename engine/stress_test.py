"""Grid Stress Test Mode - Chaos engineering scenarios for the microgrid.

Provides scripted stress scenarios that can be triggered during the demo
to show grid resilience and autonomous agent adaptation.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

from agents.base_agent import BaseAgent
from agents.battery_agent import BatteryAgent

logger = logging.getLogger("gridmint.stress")


class ScenarioType(str, Enum):
    SOLAR_ECLIPSE = "solar_eclipse"
    DEMAND_SURGE = "demand_surge"
    CASCADING_FAILURE = "cascading_failure"
    PRICE_ATTACK = "price_attack"


@dataclass
class StressResult:
    """Outcome metrics for a stress test scenario."""

    scenario: ScenarioType
    started_at_tick: int
    ended_at_tick: int
    uptime_ratio: float = 1.0
    avg_price_stability: float = 0.0
    unmet_demand_kwh: float = 0.0
    battery_response_ticks: int = 0
    trades_during_stress: int = 0
    recovery_ticks: int = 0


class StressTestRunner:
    """Applies chaos engineering scenarios to the grid engine.

    Each scenario is a sequence of timed actions applied via
    tick-level interceptors on the grid engine.
    """

    def __init__(self):
        self.active_scenario: Optional[ScenarioType] = None
        self._actions: list[Callable] = []
        self._tick_counter: int = 0
        self._start_tick: int = 0
        self._pre_stress_states: dict[str, str] = {}  # agent_id -> original status
        self._results: list[StressResult] = []

    @property
    def is_active(self) -> bool:
        return self.active_scenario is not None

    def stop_scenario(self, agents: dict[str, BaseAgent]) -> dict:
        """Manually stop the currently running stress test scenario."""
        if not self.is_active:
            return {"message": "No active scenario to stop"}
        
        scenario_name = self.active_scenario.value
        
        # Restore agents to original states
        for aid, original_status in self._pre_stress_states.items():
            if aid in agents:
                if original_status == "online":
                    agents[aid].set_online()
                elif original_status == "offline":
                    agents[aid].set_offline()
        
        self._finish_scenario()
        return {"message": f"Stopped scenario '{scenario_name}'", "success": True}

    def start_scenario(
        self,
        scenario: ScenarioType,
        agents: dict[str, BaseAgent],
        current_tick: int,
    ) -> dict:
        """Begin a stress test scenario."""
        if self.is_active:
            return {"error": f"Scenario '{self.active_scenario}' already running"}

        self.active_scenario = scenario
        self._tick_counter = 0
        self._start_tick = current_tick

        # Save original states for recovery
        self._pre_stress_states = {
            aid: a.status.value for aid, a in agents.items()
        }

        logger.info("Stress scenario '%s' started at tick %d", scenario.value, current_tick)
        return {"status": "started", "scenario": scenario.value, "tick": current_tick}

    def apply_tick(
        self,
        agents: dict[str, BaseAgent],
        current_tick: int,
    ) -> Optional[dict]:
        """Called each tick to apply scenario effects. Returns event if action taken."""
        if not self.is_active:
            return None

        self._tick_counter += 1
        event = None

        if self.active_scenario == ScenarioType.SOLAR_ECLIPSE:
            event = self._apply_solar_eclipse(agents)
        elif self.active_scenario == ScenarioType.DEMAND_SURGE:
            event = self._apply_demand_surge(agents)
        elif self.active_scenario == ScenarioType.CASCADING_FAILURE:
            event = self._apply_cascading_failure(agents)
        elif self.active_scenario == ScenarioType.PRICE_ATTACK:
            event = self._apply_price_attack(agents)

        return event

    def _apply_solar_eclipse(self, agents: dict[str, BaseAgent]) -> Optional[dict]:
        """Gradually shut down all solar agents, then recover."""
        solar_ids = sorted(aid for aid, a in agents.items() if aid.startswith("solar"))
        # Ticks 1-3: kill solar panels one by one
        # Ticks 8-10: bring them back one by one
        # Total duration: 10 ticks
        if self._tick_counter <= len(solar_ids):
            target = solar_ids[self._tick_counter - 1]
            agents[target].set_offline()
            return {"action": "eclipse_darken", "agent": target, "tick": self._tick_counter}
        elif self._tick_counter >= 8 and (self._tick_counter - 8) < len(solar_ids):
            target = solar_ids[self._tick_counter - 8]
            agents[target].set_online()
            return {"action": "eclipse_recover", "agent": target, "tick": self._tick_counter}
        elif self._tick_counter >= 11:
            self._finish_scenario()
            return {"action": "eclipse_complete"}
        return None

    def _apply_demand_surge(self, agents: dict[str, BaseAgent]) -> Optional[dict]:
        """Double all consumer loads for 6 ticks."""
        from agents.consumer_agent import ConsumerAgent
        consumers = {aid: a for aid, a in agents.items() if isinstance(a, ConsumerAgent)}

        if self._tick_counter == 1:
            for c in consumers.values():
                c.appliance_load_kw *= 2.0
            return {"action": "demand_doubled", "affected": len(consumers)}
        elif self._tick_counter >= 7:
            for c in consumers.values():
                c.appliance_load_kw /= 2.0
            self._finish_scenario()
            return {"action": "demand_normalized", "affected": len(consumers)}
        return None

    def _apply_cascading_failure(self, agents: dict[str, BaseAgent]) -> Optional[dict]:
        """Kill producers one at a time with 2-tick intervals."""
        producer_ids = sorted(
            aid for aid, a in agents.items()
            if aid.startswith("solar") or aid.startswith("battery")
        )
        idx = (self._tick_counter - 1) // 2
        if self._tick_counter % 2 == 1 and idx < len(producer_ids):
            target = producer_ids[idx]
            agents[target].set_offline()
            return {"action": "cascade_kill", "agent": target, "remaining": len(producer_ids) - idx - 1}
        elif idx >= len(producer_ids):
            # Recover all
            for aid in producer_ids:
                agents[aid].set_online()
            self._finish_scenario()
            return {"action": "cascade_recovered", "restored": len(producer_ids)}
        return None

    def _apply_price_attack(self, agents: dict[str, BaseAgent]) -> Optional[dict]:
        """A battery dumps energy at near-zero price, then withdraws."""
        battery_ids = [aid for aid in agents if aid.startswith("battery")]
        if not battery_ids:
            self._finish_scenario()
            return {"action": "no_batteries"}

        rogue = battery_ids[0]
        bat = agents[rogue]

        if self._tick_counter == 1 and isinstance(bat, BatteryAgent):
            self._original_sell = bat.sell_threshold
            bat.sell_threshold = 0.0001  # Dump at near-zero
            bat.soc = 0.9  # Give it energy to dump
            return {"action": "price_dump_start", "agent": rogue, "dump_price": 0.0001}
        elif self._tick_counter == 4 and isinstance(bat, BatteryAgent):
            bat.set_offline()
            return {"action": "rogue_withdrawal", "agent": rogue}
        elif self._tick_counter >= 7 and isinstance(bat, BatteryAgent):
            bat.sell_threshold = getattr(self, "_original_sell", 0.006)
            bat.set_online()
            self._finish_scenario()
            return {"action": "price_attack_resolved", "agent": rogue}
        return None

    def _finish_scenario(self) -> None:
        """Mark the current scenario as complete."""
        logger.info("Stress scenario '%s' completed after %d ticks",
                     self.active_scenario, self._tick_counter)
        self.active_scenario = None
        self._tick_counter = 0

    @property
    def status(self) -> dict:
        return {
            "active": self.is_active,
            "scenario": self.active_scenario.value if self.active_scenario else None,
            "ticks_elapsed": self._tick_counter,
            "available_scenarios": [s.value for s in ScenarioType],
        }
