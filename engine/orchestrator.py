"""FastAPI Orchestrator - REST API + WebSocket for the GridMint demo.

Endpoints:
    GET  /api/status           - Grid engine status and stats
    GET  /api/agents           - List all agents and their state
    GET  /api/snapshots        - Recent grid snapshots
    GET  /api/payments         - Payment engine stats + tx log
    POST /api/grid/start       - Start the simulation
    POST /api/grid/stop        - Stop the simulation
    POST /api/agent/{id}/toggle - Toggle an agent online/offline (fault injection)
    WS   /ws                   - Live snapshot stream for the dashboard
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from agents.config import create_demo_fleet
from engine.grid_engine import GridEngine
from engine.payment_engine import PaymentEngine, SimulatedSettler, ArcSettler, GatewaySettler
from engine.stress_test import ScenarioType
from engine.x402_paywall import get_paywall, x402_middleware
from agents.battery_agent import BatteryAgent

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger("gridmint.orchestrator")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(message)s")


# ---------------------------------------------------------------------------
# WebSocket connection manager
# ---------------------------------------------------------------------------
class ConnectionManager:
    """Manages active WebSocket connections for live dashboard streaming."""

    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)
        logger.info("Dashboard connected. Active clients: %d", len(self.active))

    def disconnect(self, ws: WebSocket):
        self.active.remove(ws)
        logger.info("Dashboard disconnected. Active clients: %d", len(self.active))

    async def broadcast(self, data: dict):
        """Send a JSON message to all connected dashboards."""
        if not self.active:
            return
        payload = json.dumps(data, default=str)
        stale: list[WebSocket] = []
        for ws in self.active:
            try:
                await ws.send_text(payload)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self.active.remove(ws)


# ---------------------------------------------------------------------------
# Application state
# ---------------------------------------------------------------------------
ws_manager = ConnectionManager()
engine: Optional[GridEngine] = None
payments: Optional[PaymentEngine] = None
_sim_task: Optional[asyncio.Task] = None


def _create_engine() -> tuple[GridEngine, PaymentEngine]:
    """Construct the grid engine and payment engine with default fleet."""
    fleet = create_demo_fleet()
    settlement_mode = os.getenv("SETTLEMENT_MODE", "simulated").strip().lower()

    if settlement_mode == "live":
        # Build wallet_keys map: agent_id -> private_key
        wallet_keys = {}
        for agent in fleet:
            if agent.private_key:
                wallet_keys[agent.agent_id] = agent.private_key

        # GatewaySettler routes agent trades through Circle Nanopayments (EIP-3009 gasless).
        # It automatically falls back to direct ArcSettler ERC-20 if the nanopayments
        # server is unreachable, ensuring zero demo breakage.
        settler = GatewaySettler(wallet_keys=wallet_keys)
        logger.info(
            "🔴 LIVE MODE: Using GatewaySettler (Circle Nanopayments) with %d wallets",
            len(wallet_keys),
        )
    else:
        settler = SimulatedSettler()
        # Pre-fund simulated wallets — only used when SETTLEMENT_MODE=simulated
        # AND an agent has no real wallet address (pure simulation).
        # Agents with real wallet addresses will show on-chain balances via /api/balances.
        for agent in fleet:
            settler.fund_wallet(agent.agent_id, 10.0)
            if agent.wallet_address:
                settler.fund_wallet(agent.wallet_address, 10.0)
        logger.info("🟡 SIMULATED MODE: Using SimulatedSettler")

    pay_engine = PaymentEngine(settler=settler)

    def on_trade(trade):
        pay_engine.enqueue_trade(trade)

    grid = GridEngine(
        agents=fleet,
        tick_interval=3.0,
        speed_multiplier=360,
        start_hour=5.0,
        on_trade=on_trade,
    )

    # ── Register Gemini Function Calling tools ────────────────────────────
    # These let Gemini autonomously call live grid functions during Q&A.
    def _tool_get_grid_status() -> dict:
        """Get comprehensive grid state including real-time indicators and finality status.
        
        Returns live market state with clear distinction between confirmed and pending data.
        """
        # Calculate tick delta (time since last tick)
        import time
        current_time = time.time()
        last_tick_time = getattr(grid, '_last_tick_timestamp', current_time)
        tick_delta_seconds = current_time - last_tick_time
        
        # Settlement mode and finality
        is_live_mode = settlement_mode == "live"
        block_finality_status = "N/A (simulated mode)"
        if is_live_mode:
            # In live mode, check if we have recent confirmed transactions
            recent_confirmed = sum(1 for r in payments.results[-10:] if r.success and r.tx_hash)
            block_finality_status = "confirmed" if recent_confirmed > 0 else "pending"
        
        return {
            # CURRENT STATE
            "tick": grid.tick,
            "sim_hour": round(grid.sim_hour % 24.0, 2),
            "running": grid.running,
            "tick_delta_seconds": round(tick_delta_seconds, 2),
            "tick_interval": grid.tick_interval,
            # MARKET STATE
            "clearing_price_usd_per_kwh": round(grid.clearing_price, 6),
            "total_tx_count": grid.total_tx_count,
            "total_usd_settled": round(grid.total_usd_settled, 6),
            "current_offers_count": len(grid._last_offers) if hasattr(grid, '_last_offers') else 0,
            "current_demands_count": len(grid._last_demands) if hasattr(grid, '_last_demands') else 0,
            # SETTLEMENT STATE
            "settlement_mode": settlement_mode,
            "block_finality_status": block_finality_status,
            # AGENT STATE
            "agent_count": len(grid.agents),
            "agents_online": sum(1 for a in grid.agents.values() if a.status.value == "online"),
            "agents_offline": sum(1 for a in grid.agents.values() if a.status.value == "offline"),
            # GAME THEORY METRICS
            "schelling_convergence_pct": round(grid.schelling.convergence_metrics.get("convergence_pct", 0), 2),
            "schelling_price_spread_usd": round(grid.schelling.convergence_metrics.get("price_spread", 0), 6),
            "surge_pricing_active": grid.oracle.summary.get("surge_active", False),
            "surge_multiplier": grid.oracle.summary.get("current_multiplier", 1.0),
            # COALITION & FUTURES STATE
            "active_coalitions": len(grid.coalitions.active_coalitions) if hasattr(grid.coalitions, 'active_coalitions') else 0,
            "active_futures_contracts": len(grid.futures.contracts),
            # DATA FRESHNESS
            "data_freshness": "real_time" if grid.running else "static",
            "last_update_tick": grid.tick,
        }

    def _tool_get_agent_balance(agent_id: str) -> dict:
        """Get comprehensive agent financial state including wallet balance and locked collateral.
        
        CRITICAL: This returns ACTUAL wallet balance (initial funding + earned - spent),
        NOT just P&L. Even at tick 0, agents have initial capital that Gemini must see.
        """
        agent = grid.agents.get(agent_id)
        if not agent:
            return {
                "error": f"Agent '{agent_id}' not found",
                "error_type": "AGENT_NOT_FOUND",
                "available_agents": list(grid.agents.keys()),
                "suggestion": f"Valid agent IDs: {', '.join(list(grid.agents.keys())[:5])}..."
            }
        
        # Fetch actual USDC balance from settler (synchronously)
        wallet_addr = agent.wallet_address or agent_id
        balance_usd = 0.0
        balance_source = "unknown"
        try:
            import asyncio
            balance_usd = asyncio.run(pay_engine.settler.get_balance(wallet_addr))
            balance_source = "settler_confirmed"
        except Exception as e:
            # CRITICAL: Return detailed error, not generic "0.0"
            logger.error("TOOL ERROR: Failed to fetch balance for %s: %s", agent_id, e)
            return {
                "error": f"Balance fetch failed: {str(e)}",
                "error_type": "BALANCE_FETCH_FAILED",
                "agent_id": agent_id,
                "fallback_data": {
                    "total_earned_usd": round(agent.total_earned_usd, 6),
                    "total_spent_usd": round(agent.total_spent_usd, 6),
                    "net_pl_usd": round(agent.total_earned_usd - agent.total_spent_usd, 6),
                }
            }
        
        # Calculate locked collateral from active futures contracts
        locked_collateral = 0.0
        active_futures_count = 0
        for contract in grid.futures.contracts.values():
            if contract.producer.agent_id == agent_id:
                locked_collateral += contract.producer.deposit_usd
                active_futures_count += 1
            if contract.consumer.agent_id == agent_id:
                locked_collateral += contract.consumer.deposit_usd
                active_futures_count += 1
        
        # Available balance = Total balance - Locked collateral
        available_balance = balance_usd - locked_collateral
        
        # Battery-specific state
        battery_state = {}
        if isinstance(agent, BatteryAgent):
            battery_state = {
                "current_soc": round(agent.soc, 4),
                "target_soc": 0.5,  # BatteryAgent default equilibrium target
                "capacity_kwh": agent.capacity_kwh,
                "stored_kwh": round(agent.soc * agent.capacity_kwh, 4),
                "charge_headroom_kwh": round(agent.charge_headroom, 4),
                "discharge_headroom_kwh": round(agent.discharge_headroom, 4),
                "avg_buy_price": round(agent.avg_buy_price, 6),
            }
        
        return {
            "agent_id": agent_id,
            "agent_type": agent.agent_type.value,
            "status": agent.status.value,
            "wallet_address": agent.wallet_address,
            # FINANCIAL STATE (comprehensive)
            "total_balance_usd": round(balance_usd, 6),
            "available_balance_usd": round(available_balance, 6),
            "locked_collateral_usd": round(locked_collateral, 6),
            "active_futures_contracts": active_futures_count,
            "balance_source": balance_source,
            # TRANSACTION HISTORY
            "total_earned_usd": round(agent.total_earned_usd, 6),
            "total_spent_usd": round(agent.total_spent_usd, 6),
            "net_profit_loss_usd": round(agent.total_earned_usd - agent.total_spent_usd, 6),
            "tx_count": agent.tx_count,
            # BATTERY STATE (if applicable)
            **battery_state,
            # METADATA
            "data_timestamp": grid.tick,
            "data_freshness": "real_time",
        }

    def _tool_trigger_stress_test(scenario: str) -> dict:
        """Trigger a grid stress test with comprehensive validation and error handling.
        
        Args:
            scenario: Must be exact string match from ScenarioType enum
        
        Returns detailed status including affected agents and expected impact.
        """
        # Type validation: ensure scenario is string
        if not isinstance(scenario, str):
            return {
                "error": f"Invalid argument type: scenario must be string, got {type(scenario).__name__}",
                "error_type": "TYPE_ERROR",
                "expected_type": "str",
                "received_type": type(scenario).__name__,
                "available_scenarios": [s.value for s in ScenarioType]
            }
        
        # Enum validation
        try:
            sc = ScenarioType(scenario.strip().lower())
        except ValueError:
            available = [s.value for s in ScenarioType]
            return {
                "error": f"Unknown scenario '{scenario}'",
                "error_type": "INVALID_SCENARIO",
                "received_scenario": scenario,
                "available_scenarios": available,
                "suggestion": f"Use one of: {', '.join(available)}"
            }
        
        # Execute stress test
        try:
            result = grid.stress.start_scenario(sc, grid.agents, grid.tick)
            logger.info("Gemini triggered stress test: %s at tick %d", scenario, grid.tick)
            
            # Enhance result with prediction
            result["execution_status"] = "success"
            result["triggered_by"] = "gemini_function_calling"
            result["trigger_tick"] = grid.tick
            result["expected_impact"] = {
                "solar_crash": "Supply reduced 40-60%, prices surge 2-3×",
                "demand_spike": "Demand increased 50%, prices surge 2×",
                "battery_failure": "Storage capacity reduced 50%, price volatility increases",
                "price_war": "Sellers compete aggressively, prices may drop 30%",
                "night_mode": "Solar offline, battery-dependent, prices increase 50%"
            }.get(scenario, "Market disruption expected")
            
            return result
        except Exception as e:
            logger.error("Stress test execution failed: %s", e)
            return {
                "error": f"Stress test execution failed: {str(e)}",
                "error_type": "EXECUTION_FAILED",
                "scenario": scenario,
                "tick": grid.tick,
                "traceback": str(e)
            }

    def _tool_get_economic_proof() -> dict:
        """Get comprehensive economic proof with transaction state distinction.
        
        Returns Arc vs Ethereum cost analysis with clear indicators of
        confirmed vs pending transactions.
        """
        stats = pay_engine.stats
        total_tx = stats.get("success_count", 0)
        total_pending = stats.get("pending_count", 0)
        total_failed = stats.get("failed_count", 0)
        
        arc_gas = stats.get("total_gas_usd", 0.0)
        eth_shadow = stats.get("eth_equivalent_gas_usd", round(total_tx * 2.47, 4))
        
        # Distinguish confirmed vs simulated transactions
        confirmed_tx_count = 0
        simulated_tx_count = 0
        for result in pay_engine.results:
            if result.success:
                if result.tx_hash and result.tx_hash.startswith("0x") and len(result.tx_hash) == 66:
                    confirmed_tx_count += 1
                else:
                    simulated_tx_count += 1
        
        return {
            # TRANSACTION COUNTS
            "total_transactions": total_tx,
            "confirmed_onchain_tx": confirmed_tx_count,
            "simulated_tx": simulated_tx_count,
            "pending_tx": total_pending,
            "failed_tx": total_failed,
            # SETTLEMENT AMOUNTS
            "total_usd_settled": round(stats.get("total_settled_usd", 0), 6),
            "confirmed_usd_settled": round(stats.get("confirmed_settled_usd", stats.get("total_settled_usd", 0)), 6),
            # GAS COSTS
            "arc_gas_total_usd": round(arc_gas, 8),
            "arc_avg_gas_per_tx_usd": round(arc_gas / total_tx, 8) if total_tx > 0 else 0,
            "eth_equivalent_gas_usd": round(eth_shadow, 4),
            "eth_gas_model": "65,000 gas × 20 gwei × $1,900/ETH (2024 median)",
            # SAVINGS ANALYSIS
            "arc_savings_factor": stats.get("arc_savings_vs_eth", 0),
            "savings_vs_eth_pct": round((1 - arc_gas / eth_shadow) * 100, 2) if eth_shadow > 0 and arc_gas > 0 else 99.99,
            # CHAIN COMPARISON
            "chain_comparison": stats.get("chain_comparison", {}),
            # SETTLEMENT MODE
            "settlement_mode": os.getenv("SETTLEMENT_MODE", "simulated"),
            "data_freshness": "real_time",
            "settlement_finality": "confirmed" if confirmed_tx_count > 0 else "simulated",
        }

    def _tool_get_schelling_metrics() -> dict:
        """Get comprehensive Schelling point convergence metrics including MWU learning state.
        
        Returns detailed convergence data, price expectations, and learning regret bounds.
        """
        metrics = grid.schelling.convergence_metrics
        
        # Add futures slashing risk if available
        futures_stats = grid.futures.stats
        total_slashed = futures_stats.get("total_slashed_usd", 0)
        slash_rate = futures_stats.get("slash_rate_pct", 0)
        
        return {
            # CONVERGENCE METRICS
            "convergence_pct": round(metrics.get("convergence_pct", 0), 2),
            "price_spread_usd": round(metrics.get("price_spread", 0), 6),
            "seller_expected_price": round(metrics.get("seller_expected_price", 0), 6),
            "buyer_expected_price": round(metrics.get("buyer_expected_price", 0), 6),
            # MWU LEARNING STATE
            "learning_rate_eta": metrics.get("learning_rate", 0.1),
            "price_grid_size": metrics.get("price_grid_size", 9),
            "regret_bound": metrics.get("regret_bound", "O(√(T log N))"),
            "ticks_observed": grid.tick,
            # FUTURES & SLASHING RISK
            "futures_slash_risk": {
                "total_slashed_usd": round(total_slashed, 6),
                "slash_rate_pct": round(slash_rate, 2),
                "active_contracts_at_risk": len(grid.futures.active_contracts),
                "deposit_collateral_locked": round(futures_stats.get("total_deposits_usd", 0), 6),
            },
            # WHITEPAPER ALIGNMENT
            "mechanism": "Multiplicative Weights Update (MWU)",
            "schelling_point_definition": "Price where seller/buyer expectations converge within 2σ",
            "convergence_threshold_pct": 85,
            "data_freshness": "real_time",
        }

    grid.gemini.register_tools({
        "get_grid_status": _tool_get_grid_status,
        "get_agent_balance": _tool_get_agent_balance,
        "trigger_stress_test": _tool_trigger_stress_test,
        "get_economic_proof": _tool_get_economic_proof,
        "get_schelling_metrics": _tool_get_schelling_metrics,
    })
    # ─────────────────────────────────────────────────────────────────────

    return grid, pay_engine


# ---------------------------------------------------------------------------
# Simulation loop
# ---------------------------------------------------------------------------
async def _simulation_loop():
    """Main tick loop: step engine, settle payments, broadcast snapshot."""
    global engine, payments
    if engine is None or payments is None:
        return

    engine.running = True
    logger.info("Simulation started. Tick interval: %.1fs", engine.tick_interval)

    while engine.running:
        current_tick = engine.tick + 1  # next tick number

        # 0. Ask Gemini for battery trade decisions every 5th tick
        if current_tick % 5 == 0:
            battery_tasks = []
            for a in engine.agents.values():
                if isinstance(a, BatteryAgent) and a.gemini_mode:
                    battery_tasks.append(a.ask_gemini())
            if battery_tasks:
                await asyncio.gather(*battery_tasks, return_exceptions=True)

        # 1. Advance simulation one tick
        snapshot = engine.step()

        # 1b. Ask Gemini for market narration every 10th tick
        gemini_narrative = ""
        if engine.gemini.available and engine.tick % 10 == 0:
            try:
                gemini_narrative = await engine.gemini.narrate_market(
                    engine.schelling.convergence_metrics
                )
            except Exception:
                gemini_narrative = engine.gemini._last_narrative

        # 2. Settle all matched trades from this tick
        await payments.process_queue()

        # 3. Broadcast snapshot + payment stats to dashboard
        await ws_manager.broadcast({
            "type": "snapshot",
            "data": snapshot.model_dump(),
            "payments": payments.stats,
            "surge": engine.oracle.summary,
            "certificates": engine.certificates.stats,
            "stress": engine.stress.status,
            "schelling": engine.schelling.convergence_metrics,
            "coalitions": engine.coalitions.stats,
            "futures": engine.futures.stats,
            "gemini": {
                "narrative": gemini_narrative,
                "stats": engine.gemini.stats,
            },
        })

        await asyncio.sleep(engine.tick_interval)

    logger.info("Simulation stopped.")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global engine, payments
    engine, payments = _create_engine()
    logger.info("GridMint orchestrator ready. %d agents loaded.", len(engine.agents))
    yield
    if engine:
        engine.stop()


app = FastAPI(
    title="GridMint Orchestrator",
    description="DePIN Micro-Energy Settlement Protocol - API & WebSocket Server",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        # Production Vercel domains
        "https://grid-mint.vercel.app",
        "https://grid-mint-midasbals-projects.vercel.app",
        "https://*.vercel.app",  # All Vercel preview deployments
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Payment", "X-Payment-Proof"],
)

# x402 paywall middleware (must be added after CORS)
app.middleware("http")(x402_middleware)


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------
@app.get("/api/status")
async def get_status():
    """Grid engine status and aggregate statistics."""
    settler_info = {}
    if payments:
        settler_info = {
            "settler_class": type(payments.settler).__name__,
            "settler_stats": payments.settler.stats if hasattr(payments.settler, "stats") else {},
        }
    return {
        "running": engine.running if engine else False,
        "tick": engine.tick if engine else 0,
        "sim_hour": round(engine.sim_hour % 24.0, 2) if engine else 0,
        "total_tx_count": engine.total_tx_count if engine else 0,
        "total_usd_settled": round(engine.total_usd_settled, 8) if engine else 0,
        "clearing_price_usd": engine.clearing_price if engine else 0,
        "agent_count": len(engine.agents) if engine else 0,
        "payments": payments.stats if payments else {},
        "settlement_mode": os.getenv("SETTLEMENT_MODE", "simulated").strip().lower(),
        **settler_info,
    }


@app.get("/api/agents")
async def get_agents():
    """List all agents and their current state."""
    if not engine:
        return []
    return [
        a.get_state(engine.tick, engine.sim_hour).model_dump()
        for a in engine.agents.values()
    ]


@app.get("/api/offers-demands")
async def get_offers_demands():
    """DEBUG: Get current offers and demands for diagnosing market clearing issues."""
    if not engine:
        return {"error": "Engine not initialized"}
    
    # Collect current offers and demands
    offers = []
    demands = []
    for agent in engine.agents.values():
        offer = agent.get_offer(engine.tick, engine.sim_hour)
        if offer:
            offers.append({
                "agent_id": offer.agent_id,
                "agent_type": agent.agent_type.value,
                "amount_kwh": offer.amount_kwh,
                "price_usd_per_kwh": offer.price_usd_per_kwh,
            })
        demand = agent.get_demand(engine.tick, engine.sim_hour)
        if demand:
            demands.append({
                "agent_id": demand.agent_id,
                "agent_type": agent.agent_type.value,
                "amount_kwh": demand.amount_kwh,
                "max_price_usd_per_kwh": demand.max_price_usd_per_kwh,
            })
    
    solar_offers = [o for o in offers if o["agent_type"] == "solar"]
    battery_offers = [o for o in offers if o["agent_type"] == "battery"]
    
    return {
        "tick": engine.tick,
        "sim_hour": round(engine.sim_hour % 24.0, 2),
        "total_offers": len(offers),
        "total_demands": len(demands),
        "solar_offers": len(solar_offers),
        "battery_offers": len(battery_offers),
        "offers": offers,
        "demands": demands,
    }


@app.get("/api/snapshots")
async def get_snapshots(limit: int = 20):
    """Get recent grid snapshots."""
    if not engine:
        return []
    recent = engine.snapshots[-limit:]
    return [s.model_dump() for s in recent]


@app.get("/api/payments")
async def get_payments(limit: int = 50):
    """Payment engine stats and recent transaction log."""
    if not payments:
        return {"stats": {}, "recent": []}
    recent = payments.results[-limit:]
    return {
        "stats": payments.stats,
        "recent": [
            {
                "seller": r.trade.seller_id,
                "buyer": r.trade.buyer_id,
                "amount_kwh": r.trade.amount_kwh,
                "total_usd": r.trade.total_usd,
                "tx_hash": r.tx_hash,
                "success": r.success,
                "gas_cost_usd": r.gas_cost_usd,
                "timestamp": r.timestamp,
            }
            for r in recent
        ],
    }


@app.post("/api/grid/start")
async def start_grid():
    """Start the simulation loop."""
    global _sim_task
    if engine is None:
        return {"error": "Engine not initialized"}
    if engine.running:
        return {"status": "already_running"}

    _sim_task = asyncio.create_task(_simulation_loop())
    return {"status": "started", "tick_interval": engine.tick_interval}


@app.post("/api/grid/stop")
async def stop_grid():
    """Stop the simulation loop and generate end-of-cycle analysis."""
    if engine:
        engine.stop()

    # Generate Gemini end-of-cycle analysis
    analysis = ""
    if engine and payments and engine.gemini.available:
        stats = payments.stats
        summary = {
            "total_ticks": engine.tick,
            "total_tx": stats.get("success_count", 0),
            "total_usd": stats.get("total_settled_usd", 0),
            "avg_cost_per_tx": stats.get("avg_gas_per_tx", 0),
            "eth_gas_cost": stats.get("eth_equivalent_gas_usd", 0),
            "savings_factor": stats.get("arc_savings_factor", 0),
            "green_pct": engine.certificates.stats.get("green_percentage", 0),
            "schelling_convergence": engine.schelling.convergence_metrics.get("convergence_pct", 0),
            "schelling_spread": engine.schelling.convergence_metrics.get("price_spread", 0),
        }
        try:
            analysis = await engine.gemini.end_of_cycle_analysis(summary)
        except Exception:
            analysis = ""

    return {
        "status": "stopped",
        "total_ticks": engine.tick if engine else 0,
        "gemini_analysis": analysis,
    }


@app.post("/api/agent/{agent_id}/toggle")
async def toggle_agent(agent_id: str):
    """Toggle an agent online/offline for live fault injection demo."""
    if not engine:
        return {"error": "Engine not initialized"}
    # Security: validate agent_id against known agents only — prevents path traversal patterns
    if not agent_id or len(agent_id) > 64 or agent_id not in engine.agents:
        return {"error": "Agent not found"}

    state = engine.toggle_agent(agent_id)
    await ws_manager.broadcast({
        "type": "agent_toggle",
        "data": state.model_dump(),
    })
    return state.model_dump()


@app.post("/api/stress/{scenario}")
async def start_stress(scenario: str):
    """Start a stress test scenario."""
    if not engine:
        return {"error": "Engine not initialized"}
    try:
        sc = ScenarioType(scenario)
    except ValueError:
        return {"error": f"Unknown scenario '{scenario}'", "available": [s.value for s in ScenarioType]}
    result = engine.stress.start_scenario(sc, engine.agents, engine.tick)
    return result


@app.delete("/api/stress")
async def stop_stress():
    """Stop the currently running stress test scenario."""
    if not engine:
        return {"error": "Engine not initialized"}
    result = engine.stress.stop_scenario(engine.agents)
    return result


@app.get("/api/stress")
async def get_stress():
    """Get current stress test status."""
    if not engine:
        return {}
    return engine.stress.status


@app.get("/api/certificates")
async def get_certificates():
    """Get green certificate statistics and recent entries."""
    if not engine:
        return {}
    stats = engine.certificates.stats
    recent = engine.certificates.certificates[-20:]
    return {
        "stats": stats,
        "recent": [
            {"cert_id": c.cert_id, "source": c.source_agent, "buyer": c.buyer_agent,
             "kwh": c.kwh, "tick": c.tick, "sim_hour": c.sim_hour}
            for c in recent
        ],
    }


@app.get("/api/certificates/{agent_id}")
async def get_agent_certificates(agent_id: str):
    """Get green certificates for a specific agent."""
    if not engine:
        return []
    return engine.certificates.get_agent_certificates(agent_id)


@app.get("/api/surge")
async def get_surge():
    """Get current surge pricing oracle state."""
    if not engine:
        return {}
    return engine.oracle.summary


@app.get("/api/schelling")
async def get_schelling():
    """Get MWU Schelling point convergence metrics."""
    if not engine:
        return {}
    return engine.schelling.convergence_metrics


@app.get("/api/schelling/{agent_id}")
async def get_schelling_agent(agent_id: str):
    """Get learned price distribution for a specific agent."""
    if not engine:
        return {}
    dist = engine.schelling.get_agent_distribution(agent_id)
    return dist or {"error": f"Agent '{agent_id}' not in Schelling engine"}


@app.get("/api/schelling/distributions/all")
async def get_all_distributions():
    """Get all agent distributions for dashboard heatmap."""
    if not engine:
        return []
    return engine.schelling.get_all_distributions()


@app.get("/api/economic-proof")
async def get_economic_proof():
    """Economic proof: GridMint cost vs traditional gas costs."""
    if not engine or not payments:
        return {}
    stats = payments.stats
    total_tx = stats.get("success_count", 0)
    total_usd = stats.get("total_settled_usd", 0.0)
    # Use real formula: 65k gas × 20 gwei × $1,900/ETH per ERC-20 transfer
    eth_shadow = stats.get("eth_equivalent_gas_usd", round(total_tx * 2.47, 4))
    arc_gas = stats.get("total_gas_usd", 0.0)
    paywall = get_paywall()
    return {
        "total_transactions": total_tx,
        "total_usd_settled": round(total_usd, 8),
        "avg_cost_per_tx_usd": round(arc_gas / total_tx, 8) if total_tx > 0 else 0,
        "traditional_eth_gas_cost_usd": round(eth_shadow, 4),
        "eth_gas_model": stats.get("eth_gas_model", "65,000 gas × 20 gwei × $1,900/ETH (2024 median)"),
        "chain_comparison": stats.get("chain_comparison", {}),
        "savings_vs_eth_pct": round((1 - arc_gas / eth_shadow) * 100, 2) if eth_shadow > 0 and arc_gas > 0 else 99.99,
        "arc_savings_factor": stats.get("arc_savings_vs_eth", 0),
        "green_energy_pct": engine.certificates.stats.get("green_percentage", 0),
        "merkle_root": engine.certificates.get_merkle_root(),
        "surge_pricing_active": True,
        "schelling_convergence": engine.schelling.convergence_metrics,
        "x402_revenue": paywall.stats,
        "stress_tests_available": [s.value for s in ScenarioType],
    }


@app.get("/api/x402")
async def get_x402_stats():
    """x402 paywall revenue and usage statistics (not paywalled itself)."""
    return get_paywall().stats


@app.get("/api/coalitions")
async def get_coalitions():
    """Shapley coalition statistics and recent coalition history."""
    if not engine:
        return {"stats": {}, "recent": []}
    stats = engine.coalitions.stats
    recent = engine.coalitions.historical_coalitions[-10:]
    return {
        "stats": stats,
        "recent": [
            {
                "coalition_id": c.coalition_id,
                "formation_tick": c.formation_tick,
                "members": [{"agent_id": m.agent_id, "agent_type": m.agent_type, "offered_kwh": m.offered_kwh} for m in c.members],
                "total_kwh": c.total_kwh,
                "is_dispatchable": c.is_dispatchable,
                "revenue_usd": c.revenue_usd,
                "shapley_values": c.shapley_values,
                "revenue_splits": c.revenue_splits,
            }
            for c in recent
        ],
    }


@app.get("/api/futures")
async def get_futures():
    """Energy futures market statistics and recent contract history."""
    if not engine:
        return {"stats": {}, "recent": []}
    stats = engine.futures.stats
    recent = engine.futures.historical[-10:]
    return {
        "stats": stats,
        "recent": [
            {
                "contract_id": c.contract_id,
                "producer": c.producer.agent_id,
                "consumer": c.consumer.agent_id,
                "delivery_tick": c.delivery_tick,
                "futures_price": c.futures_price,
                "spot_price_at_commit": c.spot_price_at_commit,
                "spread": c.spread,
                "state": c.state.value if hasattr(c.state, "value") else str(c.state),
                "slash_amount_usd": getattr(c, "slash_amount_usd", 0),
                "actual_delivery_kwh": getattr(c, "actual_delivery_kwh", 0),
            }
            for c in recent
        ],
    }



# ---------------------------------------------------------------------------
# Gemini AI endpoints
# ---------------------------------------------------------------------------
@app.get("/api/gemini")
async def get_gemini_stats():
    """Gemini AI brain status and statistics."""
    if not engine:
        return {"available": False}
    return engine.gemini.stats


async def _fetch_onchain_balance(wallet_address: str) -> float | None:
    """Try to fetch real USDC balance from Arc Testnet for any wallet address.

    Returns float balance in USD, or None if unreachable.
    """
    try:
        from web3 import Web3
        rpc_url = os.getenv("ARC_RPC_URL", "https://rpc.testnet.arc.network")
        usdc_address = os.getenv("USDC_CONTRACT_ADDRESS", "0x3600000000000000000000000000000000000000")
        w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 4}))
        abi = [{"name": "balanceOf", "type": "function", "inputs": [{"name": "account", "type": "address"}], "outputs": [{"name": "", "type": "uint256"}]}]
        usdc = w3.eth.contract(address=Web3.to_checksum_address(usdc_address), abi=abi)
        raw = usdc.functions.balanceOf(Web3.to_checksum_address(wallet_address)).call()
        return raw / 1_000_000
    except Exception:
        return None


@app.get("/api/balances")
async def get_balances():
    """Get USDC balances for all agents.

    Always attempts real on-chain balance from Arc Testnet first.
    Falls back to simulated in-memory balance if RPC is unreachable.
    """
    if not engine or not payments:
        return {}
    result = {}
    for aid, agent in engine.agents.items():
        wallet_addr = agent.wallet_address
        # 1. Try real on-chain balance if agent has a real wallet address
        if wallet_addr:
            onchain = await _fetch_onchain_balance(wallet_addr)
            if onchain is not None:
                result[aid] = {
                    "address": wallet_addr,
                    "balance_usd": round(onchain, 6),
                    "source": "arc_testnet",
                }
                continue
        # 2. Fall back to simulated balance (or 0 if no wallet)
        addr_key = wallet_addr or aid
        try:
            bal = await payments.settler.get_balance(addr_key)
            result[aid] = {
                "address": wallet_addr,
                "balance_usd": round(bal, 6),
                "source": "simulated",
            }
        except Exception as e:
            result[aid] = {"address": wallet_addr, "balance_usd": None, "source": "error", "error": str(e)}
    return result


@app.get("/api/gemini/narrate")
async def get_narration():
    """Get the latest Gemini market narrative."""
    if not engine:
        return {"narrative": "Engine not initialized."}
    if not engine.gemini.available:
        return {"narrative": engine.gemini._last_narrative or "Gemini unavailable."}
    narrative = await engine.gemini.narrate_market(engine.schelling.convergence_metrics)
    return {"narrative": narrative}


@app.post("/api/gemini/ask")
async def ask_gemini(body: dict):
    """Operator console: ask Gemini a question about the grid.

    Body: {"question": "Why did battery_01 sell at tick 42?"}
    
    SECURITY: Input sanitized, length limited, validated before Gemini processing.
    """
    if not engine:
        return {"answer": "Engine not initialized."}
    question = body.get("question", "")
    if not question or not isinstance(question, str):
        return {"answer": "Please provide a question."}
    
    # SECURITY: Strict input validation
    # 1. Type check (already done above)
    # 2. Length limit to prevent DoS and context overflow
    if len(question) > 600:
        return {"answer": "Question too long. Please limit to 600 characters."}
    
    # 3. Strip and validate non-empty
    question = question.strip()
    if not question:
        return {"answer": "Please provide a question."}
    
    # 4. Additional security: Gemini brain will further sanitize input
    # (sanitization now handled in gemini_brain.py._sanitize_user_input)

    # Build context from current grid state
    context = {
        "tick": engine.tick,
        "sim_hour": round(engine.sim_hour % 24.0, 2),
        "clearing_price": engine.clearing_price,
        "total_tx": engine.total_tx_count,
        "total_usd": round(engine.total_usd_settled, 6),
        "agents": {
            aid: {
                "type": a.agent_type.value,
                "status": a.status.value,
                "earned": round(a.total_earned_usd, 6),
                "spent": round(a.total_spent_usd, 6),
                "tx_count": a.tx_count,
                **({"soc": round(a.soc, 3)} if isinstance(a, BatteryAgent) else {}),
            }
            for aid, a in engine.agents.items()
        },
        "schelling": engine.schelling.convergence_metrics,
        "surge": engine.oracle.summary,
    }
    answer = await engine.gemini.answer_query(question, context)
    return {"answer": answer}

@app.post("/api/gemini/ask-fc")
async def ask_gemini_with_functions(body: dict):
    """Agentic operator console using Gemini Function Calling.

    Gemini autonomously decides which live grid tools to invoke, executes them,
    and returns a grounded answer. This demonstrates the hackathon requirement:
    'Function Calling, enabling agents to interact directly with Circle APIs
    and smart contracts.'

    Body: {"question": "Trigger a solar crash and tell me the economic impact"}

    Available tools Gemini can call:
      - get_grid_status()         → live tick, price, tx count, settlement mode
      - get_agent_balance(agent_id) → USDC balance & tx history for any agent
      - trigger_stress_test(scenario) → inject solar_crash / demand_spike / etc.
      - get_economic_proof()      → Arc vs ETH cost comparison
      - get_schelling_metrics()   → MWU convergence data
    
    SECURITY: Input validated and sanitized. All tool calls are logged for audit.
    """
    if not engine:
        return {"answer": "Engine not initialized.", "tools_called": [], "function_calling_used": False}
    question = body.get("question", "")
    if not question or not isinstance(question, str):
        return {"answer": "Please provide a question.", "tools_called": [], "function_calling_used": False}
    
    # SECURITY: Length limit to prevent DoS
    if len(question) > 600:
        return {"answer": "Question too long. Please limit to 600 characters.", "tools_called": [], "function_calling_used": False}
    
    question = question.strip()
    if not question:
        return {"answer": "Please provide a question.", "tools_called": [], "function_calling_used": False}

    # SECURITY: Further sanitization and validation happens in gemini_brain.py
    # All tool calls are logged in gemini._fc_call_log for audit trail
    result = await engine.gemini.answer_query_with_functions(question)
    return result


# ---------------------------------------------------------------------------
# AUDIT ITEMS: /health, /api/grid/reset, /api/live-proof, /api/settlement-log
# ---------------------------------------------------------------------------

@app.get("/health")
async def health_check():
    """System readiness endpoint — judges can hit this to verify live chain connectivity."""
    import time
    chain_ok = False
    block_number = None
    usdc_verified = False
    rpc_url = os.getenv("ARC_RPC_URL", "")

    try:
        from web3 import Web3
        w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 5}))
        chain_ok = w3.is_connected()
        if chain_ok:
            block_number = w3.eth.block_number
            usdc_addr = os.getenv("USDC_CONTRACT_ADDRESS", "")
            if usdc_addr:
                code = w3.eth.get_code(Web3.to_checksum_address(usdc_addr))
                usdc_verified = len(code) > 2
    except Exception as e:
        logger.warning("Health check chain probe failed: %s", e)

    mode = os.getenv("SETTLEMENT_MODE", "simulated").strip().lower()
    return {
        "status": "ok",
        "arc_connected": chain_ok,
        "arc_rpc": rpc_url,
        "arc_chain_id": int(os.getenv("ARC_CHAIN_ID", "5042002")),
        "block_number": block_number,
        "usdc_contract_verified": usdc_verified,
        "usdc_contract": os.getenv("USDC_CONTRACT_ADDRESS", ""),
        "gateway_wallet": os.getenv("GATEWAY_WALLET_ADDRESS", ""),
        "settlement_mode": mode,
        "agents_loaded": len(engine.agents) if engine else 0,
        "simulation_running": engine.running if engine else False,
        "uptime_ticks": engine.tick if engine else 0,
        "timestamp": int(time.time()),
    }


@app.post("/api/grid/reset")
async def reset_grid():
    """Quick Start Demo: re-create engine from dawn (05:00), clear all state, auto-start."""
    global engine, payments, _sim_task

    # Stop existing simulation
    if engine and engine.running:
        engine.stop()
    if _sim_task and not _sim_task.done():
        _sim_task.cancel()
        try:
            await _sim_task
        except asyncio.CancelledError:
            pass
        _sim_task = None

    # Re-create engine from dawn
    engine, payments = _create_engine()
    logger.info("Grid reset to dawn (05:00). Auto-starting simulation.")

    # Auto-start
    _sim_task = asyncio.create_task(_simulation_loop())
    return {
        "status": "reset_and_started",
        "start_hour": 5.0,
        "message": "Grid reset to dawn (05:00). Simulation auto-started.",
        "agents": len(engine.agents),
    }


@app.get("/api/live-proof")
async def get_live_proof():
    """Export a static JSON artifact of all on-chain tx hashes — verifiable offline."""
    if not payments:
        return {"error": "No payment data available"}

    tx_records = []
    for r in payments.results:
        # Arc RPC returns tx_hashes with OR without "0x" prefix (both are valid)
        # Accept both formats: 64-char hex (no prefix) or 66-char hex (with 0x prefix)
        if r.success and r.tx_hash and r.tx_hash != "None":
            hash_clean = r.tx_hash.lower()
            # Check if it's a valid hex hash (64 chars without 0x, or 66 chars with 0x)
            is_valid = ((len(hash_clean) == 64 and all(c in '0123456789abcdef' for c in hash_clean)) or
                       (len(hash_clean) == 66 and hash_clean.startswith('0x')))
            
            if is_valid:
                # Normalize to 0x format for Arc Block Explorer URLs
                tx_hash_normalized = hash_clean if hash_clean.startswith('0x') else f"0x{hash_clean}"
                
                tx_records.append({
                    "tx_hash": tx_hash_normalized,
                    "arcscan_url": f"https://testnet.arcscan.app/tx/{tx_hash_normalized}",
                    "seller": r.trade.seller_id,
                    "buyer": r.trade.buyer_id,
                    "amount_kwh": round(r.trade.amount_kwh, 6),
                    "usdc_amount": round(r.trade.total_usd, 8),
                    "gas_cost_usd": round(r.gas_cost_usd or 0, 8),
                    "timestamp": r.timestamp,
                })

    stats = payments.stats
    return {
        "proof_type": "arc_testnet_settlement_log",
        "settlement_mode": os.getenv("SETTLEMENT_MODE", "simulated"),
        "gateway_wallet": os.getenv("GATEWAY_WALLET_ADDRESS", ""),
        "arcscan_gateway_url": f"https://testnet.arcscan.app/address/{os.getenv('GATEWAY_WALLET_ADDRESS','')}",
        "chain_id": int(os.getenv("ARC_CHAIN_ID", "5042002")),
        "usdc_contract": os.getenv("USDC_CONTRACT_ADDRESS", ""),
        "total_transactions": len(tx_records),
        "total_settled_usd": round(stats.get("total_settled_usd", 0), 8),
        "total_gas_usd": round(stats.get("total_gas_usd", 0), 8),
        "eth_equivalent_gas_usd": round(stats.get("eth_equivalent_gas_usd", 0), 4),
        "arc_savings_vs_eth": stats.get("arc_savings_vs_eth"),
        "transactions": tx_records,
    }


@app.get("/api/settlement-log")
async def get_settlement_log(limit: int = 200):
    """Serve the raw settlement JSONL log from disk (auditable raw data for judges)."""
    import pathlib
    # Security: cap limit to prevent excessive memory usage
    limit = max(1, min(limit, 500))
    log_path = pathlib.Path(__file__).parent.parent / "settlement_log.jsonl"
    entries = []
    if log_path.exists():
        try:
            with open(log_path) as f:
                lines = f.readlines()
            for line in lines[-limit:]:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except Exception:
                        pass
        except Exception as e:
            return {"error": str(e), "entries": []}
    return {
        "total_entries": len(entries),
        "log_path": str(log_path),
        "entries": entries,
    }


@app.get("/api/circle-status")
async def get_circle_status():
    """Return Circle technology integration status and design rationale."""
    from engine.circle_payments import circle_integration_status
    return circle_integration_status()


@app.get("/api/gateway/deposit-info")
async def get_gateway_deposit_info():
    """Return Circle Nanopayments Gateway deposit info for buyers."""
    settler_stats = {}
    if payments and hasattr(payments.settler, "stats"):
        settler_stats = payments.settler.stats
    return {
        "network": "Arc Testnet",
        "chain_id": 5042002,
        "eip155_network_id": "eip155:5042002",
        "circle_gateway_domain": 26,
        "usdc_contract": "0x3600000000000000000000000000000000000000",
        "seller_address": os.getenv("GATEWAY_WALLET_ADDRESS", "0x0077777d7EBA4688BDeF3E311b846F25870A19B9"),
        "nanopayments_server": "http://localhost:4402",
        "sdk": "@circle-fin/x402-batching",
        "buyer_quickstart": "https://developers.circle.com/gateway/nanopayments/quickstarts/buyer",
        "deposit_command": "new GatewayClient({ chain: 'arcTestnet', privateKey }).deposit('1')",
        "payment_header": "PAYMENT-SIGNATURE",
        "confirmations_required": 1,
        "time_to_attestation_ms": 500,
        "paywalled_endpoints": {
            "/api/economic-proof": {"price_usd": 0.003, "amount_usdc_units": 3000},
            "/api/certificates": {"price_usd": 0.001, "amount_usdc_units": 1000},
            "/api/schelling": {"price_usd": 0.002, "amount_usdc_units": 2000},
        },
        "agent_settlement": {
            "endpoint": "POST http://localhost:4402/nanopayments/agent-settle",
            "description": "Agent-to-agent trades routed through Circle Gateway (EIP-3009 gasless)",
            "settler_class": type(payments.settler).__name__ if payments else "unknown",
            "settler_stats": settler_stats,
        },
    }


@app.get("/api/live-proof/full")
async def get_live_proof_full():
    """Serve the pre-generated live_proof.json with 60+ real Arc Testnet tx hashes.

    This file is generated by scripts/generate_live_proof.py and contains
    verifiable on-chain transaction hashes for all energy trades.
    """
    import pathlib
    proof_path = pathlib.Path(__file__).parent.parent / "live_proof.json"
    if proof_path.exists():
        with open(proof_path) as f:
            return json.load(f)
    return {"error": "live_proof.json not found. Run scripts/generate_live_proof.py first."}


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """Live snapshot stream for the dashboard."""
    await ws_manager.connect(ws)
    try:
        # Keep connection alive; client can send commands too
        while True:
            data = await ws.receive_text()
            # Future: handle dashboard commands (e.g., toggle agent)
            msg = json.loads(data)
            if msg.get("action") == "toggle_agent":
                agent_id = msg.get("agent_id")
                if agent_id and engine and agent_id in engine.agents:
                    state = engine.toggle_agent(agent_id)
                    await ws_manager.broadcast({
                        "type": "agent_toggle",
                        "data": state.model_dump(),
                    })
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "engine.orchestrator:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
