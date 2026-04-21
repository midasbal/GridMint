"""Gemini AI Brain — powers intelligent agent decisions and operator console.

Three capabilities:
1. Battery trade analysis: Gemini analyzes price/SoC history → buy/sell/hold
2. Market narration: Explains Schelling convergence in natural language
3. Operator Q&A: Judges can ask questions about the grid in plain English

All calls are async with timeout fallback so the 3-second tick loop is never blocked.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("gridmint.gemini")

# ---------------------------------------------------------------------------
# Gemini SDK import (graceful degradation if not installed or no key)
# ---------------------------------------------------------------------------
_GEMINI_AVAILABLE = False
_client = None

try:
    from google import genai
    from google.genai import types as genai_types

    _api_key = os.getenv("GEMINI_API_KEY", "")
    if _api_key:
        _client = genai.Client(api_key=_api_key)
        _GEMINI_AVAILABLE = True
        logger.info("Gemini AI brain initialized (model: gemini-2.5-flash - latest transactional agent model).")
    else:
        logger.warning("GEMINI_API_KEY not set — Gemini brain disabled, using fallback logic.")
except ImportError:
    logger.warning("google-genai not installed — Gemini brain disabled.")
    genai_types = None  # type: ignore


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class TradeDecision:
    """Output of Gemini trade analysis."""
    action: str  # "buy", "sell", "hold"
    confidence: float  # 0.0 - 1.0
    reasoning: str  # natural language explanation
    suggested_price: Optional[float] = None


@dataclass
class PriceSnapshot:
    """Compact price/state snapshot for Gemini context window."""
    tick: int
    sim_hour: float
    clearing_price: float
    supply_kwh: float
    demand_kwh: float
    battery_soc: float = 0.0
    avg_buy_price: float = 0.0


# ---------------------------------------------------------------------------
# Rate limiter (Gemini free tier: 15 RPM)
# ---------------------------------------------------------------------------
class _RateLimiter:
    """Simple token-bucket rate limiter."""

    def __init__(self, max_per_minute: int = 12):
        self._max = max_per_minute
        self._timestamps: list[float] = []

    def can_call(self) -> bool:
        now = time.time()
        self._timestamps = [t for t in self._timestamps if now - t < 60.0]
        return len(self._timestamps) < self._max

    def record(self) -> None:
        self._timestamps.append(time.time())


# ---------------------------------------------------------------------------
# Gemini Brain
# ---------------------------------------------------------------------------
class GeminiBrain:
    """Async Gemini integration for GridMint agents.

    All methods return fallback values if Gemini is unavailable or times out.
    """

    TIMEOUT_SECONDS = 2.5  # Must complete before next 3s tick
    MODEL_NAME = "gemini-2.5-flash"  # Latest Flash model - optimized for transactional agents

    def __init__(self):
        self._rate_limiter = _RateLimiter(max_per_minute=12)
        self._model = None
        self._client = _client
        if _GEMINI_AVAILABLE and _client:
            self._model = True  # Flag; we use _client.models.generate_content()
        self._last_narrative: str = ""
        self._price_history: list[PriceSnapshot] = []
        self._call_count: int = 0
        self._fallback_count: int = 0
        # Function-calling tool registry: name -> callable
        self._tools: dict[str, object] = {}
        self._fc_call_log: list[dict] = []  # audit log of all function calls

    def register_tools(self, tools: dict[str, object]) -> None:
        """Register callable functions that Gemini can invoke via Function Calling.

        Call this after instantiation, passing a dict of name -> Python callable.
        Example:
            brain.register_tools({
                "get_grid_status": lambda: {...},
                "trigger_stress_test": lambda scenario: engine.stress.start_scenario(...),
                "get_agent_balance": lambda agent_id: payments.settler.get_balance(...),
            })
        """
        self._tools.update(tools)
        logger.info("Gemini Function Calling: %d tools registered: %s", len(self._tools), list(self._tools))

    def _build_tool_declarations(self) -> list:
        """Build Gemini FunctionDeclaration objects for all registered tools."""
        if not _GEMINI_AVAILABLE or genai_types is None or not self._tools:
            return []
        declarations = []
        # Tool schemas — each registered tool gets a typed FunctionDeclaration
        schemas = {
            "get_grid_status": genai_types.FunctionDeclaration(
                name="get_grid_status",
                description="Returns comprehensive real-time grid state including: tick number, clearing price, settlement mode (live/simulated), block finality status (confirmed/pending), active agents, Schelling convergence %, surge pricing multiplier, active coalitions, and futures contracts. Distinguishes between real-time and static data.",
                parameters=genai_types.Schema(type=genai_types.Type.OBJECT, properties={}),
            ),
            "get_agent_balance": genai_types.FunctionDeclaration(
                name="get_agent_balance",
                description="Returns detailed financial state for an agent including: total_balance_usd (initial funding + earned - spent), available_balance_usd (total - locked collateral), locked_collateral_usd (futures deposits), transaction history (earned/spent/net P&L), battery state (SoC, target SoC, charge/discharge headroom if battery), and data freshness indicators. CRITICAL: Shows initial capital even at tick 0.",
                parameters=genai_types.Schema(
                    type=genai_types.Type.OBJECT,
                    properties={
                        "agent_id": genai_types.Schema(
                            type=genai_types.Type.STRING,
                            description="Agent identifier (e.g. 'solar-1', 'battery-2', 'house-3'). Must be exact string match.",
                        )
                    },
                    required=["agent_id"],
                ),
            ),
            "trigger_stress_test": genai_types.FunctionDeclaration(
                name="trigger_stress_test",
                description="Injects a grid stress scenario with validation and detailed error handling. Returns execution status, affected agents, and expected market impact. Available scenarios: 'solar_crash' (supply -40%), 'demand_spike' (demand +50%), 'battery_failure' (storage -50%), 'price_war' (competitive pricing), 'night_mode' (solar offline). Returns error with suggestions if invalid scenario.",
                parameters=genai_types.Schema(
                    type=genai_types.Type.OBJECT,
                    properties={
                        "scenario": genai_types.Schema(
                            type=genai_types.Type.STRING,
                            description="Exact scenario name (lowercase): solar_crash | demand_spike | battery_failure | price_war | night_mode",
                        )
                    },
                    required=["scenario"],
                ),
            ),
            "get_economic_proof": genai_types.FunctionDeclaration(
                name="get_economic_proof",
                description="Returns comprehensive economic proof with transaction state distinction: total transactions (confirmed onchain vs simulated), settlement amounts (confirmed vs pending), Arc gas costs, Ethereum equivalent costs, savings factor, chain comparison (Arbitrum/Base/Polygon/Solana), and settlement finality status. Distinguishes between confirmed blockchain transactions and local simulation actions.",
                parameters=genai_types.Schema(type=genai_types.Type.OBJECT, properties={}),
            ),
            "get_schelling_metrics": genai_types.FunctionDeclaration(
                name="get_schelling_metrics",
                description="Returns MWU Schelling point convergence metrics including: convergence % (how well agents agree on price), price spread (seller vs buyer expectations), MWU learning rate (eta), regret bound (O(√(T log N))), futures slashing risk (total slashed USD, slash rate %, locked collateral), and mechanism description per whitepaper. Shows game-theoretic coordination quality.",
                parameters=genai_types.Schema(type=genai_types.Type.OBJECT, properties={}),
            ),
        }
        for name in self._tools:
            if name in schemas:
                declarations.append(schemas[name])
        return declarations

    def _dispatch_tool_call(self, name: str, args: dict) -> str:
        """Execute a registered tool with strict type validation and detailed error handling.
        
        SECURITY: Validates all arguments against strict schemas to prevent malicious payloads.
        
        Returns JSON-serializable result string with error types for Gemini to understand.
        """
        fn = self._tools.get(name)
        if fn is None:
            error_payload = {
                "error": f"Tool '{name}' not registered",
                "error_type": "TOOL_NOT_FOUND",
                "available_tools": list(self._tools.keys()),
                "suggestion": "Use one of the registered tools listed above"
            }
            return json.dumps(error_payload)
        
        # SECURITY: Validate tool arguments against expected schemas
        is_valid, validation_error = self._validate_tool_arguments(name, args)
        if not is_valid:
            logger.warning("SECURITY: Tool argument validation failed for %s: %s", name, validation_error)
            error_payload = {
                "error": f"Tool argument validation failed: {validation_error}",
                "error_type": "VALIDATION_ERROR",
                "tool": name,
                "args": {k: str(v)[:50] for k, v in args.items()},  # Truncate in error response
                "security_note": "Arguments must match expected schema"
            }
            return json.dumps(error_payload)
        
        # Type validation and sanitization for common arguments
        validated_args = {}
        for key, value in args.items():
            # String arguments: ensure they're strings and sanitize
            if key in ("agent_id", "scenario"):
                if not isinstance(value, str):
                    error_payload = {
                        "error": f"Argument '{key}' must be string, got {type(value).__name__}",
                        "error_type": "TYPE_ERROR",
                        "expected_type": "str",
                        "received_type": type(value).__name__,
                        "received_value": str(value),
                    }
                    return json.dumps(error_payload)
                # SECURITY: Sanitize string arguments
                sanitized = self._sanitize_user_input(str(value))
                if not sanitized:
                    error_payload = {
                        "error": f"Argument '{key}' contains invalid or malicious content",
                        "error_type": "SECURITY_ERROR",
                        "received_value": str(value)[:50],
                        "security_note": "Input failed sanitization check (possible injection attempt)"
                    }
                    logger.warning("SECURITY: Tool argument sanitization failed for %s.%s: %s", name, key, value)
                    return json.dumps(error_payload)
                validated_args[key] = sanitized
            else:
                validated_args[key] = value
        
        try:
            result = fn(**validated_args)
            
            # Check if result is an error dict
            if isinstance(result, dict) and "error" in result:
                # Tool returned an error - log it but pass through to Gemini
                logger.warning("Tool %s returned error: %s", name, result.get("error"))
                entry = {
                    "tool": name,
                    "args": validated_args,
                    "success": False,
                    "error": result.get("error"),
                    "error_type": result.get("error_type", "TOOL_ERROR"),
                    "ts": time.time()
                }
                self._fc_call_log.append(entry)
                return json.dumps(result, default=str)
            
            # Success
            entry = {"tool": name, "args": validated_args, "success": True, "ts": time.time()}
            self._fc_call_log.append(entry)
            logger.info("Gemini Function Call: %s(%s) → success", name, validated_args)
            return json.dumps(result, default=str)
            
        except TypeError as e:
            # Function signature mismatch
            logger.error("Tool %s type error: %s", name, e)
            error_payload = {
                "error": f"Tool execution failed: {str(e)}",
                "error_type": "TYPE_ERROR",
                "tool": name,
                "args": validated_args,
                "traceback": str(e),
            }
            entry = {"tool": name, "args": validated_args, "success": False, "error": str(e), "ts": time.time()}
            self._fc_call_log.append(entry)
            return json.dumps(error_payload)
            
        except Exception as e:
            # Unexpected error
            logger.error("Tool %s execution failed: %s", name, e)
            error_payload = {
                "error": f"Tool execution failed: {str(e)}",
                "error_type": "EXECUTION_ERROR",
                "tool": name,
                "args": validated_args,
                "traceback": str(e),
            }
            entry = {"tool": name, "args": validated_args, "success": False, "error": str(e), "ts": time.time()}
            self._fc_call_log.append(entry)
            return json.dumps(error_payload)

    @property
    def available(self) -> bool:
        return self._model is not None and self._client is not None

    def _generate(self, prompt: str) -> str:
        """Synchronous Gemini call via new SDK. Returns response text."""
        response = self._client.models.generate_content(
            model=self.MODEL_NAME,
            contents=prompt,
        )
        return response.text

    @property
    def stats(self) -> dict:
        return {
            "available": self.available,
            "model": self.MODEL_NAME,
            "calls": self._call_count,
            "fallbacks": self._fallback_count,
            "last_narrative": self._last_narrative,
            "function_calling": {
                "registered_tools": list(self._tools.keys()),
                "total_fc_calls": len(self._fc_call_log),
                "recent_fc_calls": self._fc_call_log[-5:],
            },
        }

    def record_tick(self, snap: PriceSnapshot) -> None:
        """Record a price snapshot for context. Keeps last 10 ticks."""
        self._price_history.append(snap)
        if len(self._price_history) > 10:
            self._price_history = self._price_history[-10:]

    # ------------------------------------------------------------------
    # 1. Battery trade analysis
    # ------------------------------------------------------------------
    async def analyze_trade(
        self,
        agent_id: str,
        soc: float,
        capacity_kwh: float,
        avg_buy_price: float,
        buy_threshold: float,
        sell_threshold: float,
    ) -> TradeDecision:
        """Ask Gemini whether a battery should buy, sell, or hold.

        Falls back to simple threshold logic if Gemini is unavailable/slow.
        """
        if not self.available or not self._rate_limiter.can_call():
            self._fallback_count += 1
            return self._fallback_trade(soc, avg_buy_price, buy_threshold, sell_threshold)

        history_text = self._format_history()
        prompt = f"""You are an energy trading AI managing battery "{agent_id}".

BATTERY STATE:
- SoC: {soc:.1%} of {capacity_kwh} kWh
- Average buy price: ${avg_buy_price:.4f}/kWh
- Buy threshold: ${buy_threshold:.4f}/kWh
- Sell threshold: ${sell_threshold:.4f}/kWh

RECENT MARKET (last {len(self._price_history)} ticks):
{history_text}

Decide: BUY, SELL, or HOLD. Consider:
1. Price trend (rising/falling)
2. SoC level (don't drain below 10%, don't charge above 95%)
3. Arbitrage opportunity (sell above avg_buy_price for profit)
4. Time of day (solar production peaks midday, demand peaks evening)

Respond in EXACTLY this JSON format, nothing else:
{{"action": "buy|sell|hold", "confidence": 0.0-1.0, "reasoning": "one sentence"}}"""

        try:
            self._rate_limiter.record()
            self._call_count += 1
            result_text = await asyncio.wait_for(
                asyncio.to_thread(self._generate, prompt),
                timeout=self.TIMEOUT_SECONDS,
            )
            return self._parse_trade_response(result_text, soc, avg_buy_price, buy_threshold, sell_threshold)
        except Exception as e:
            logger.debug("Gemini trade analysis failed (%s), using fallback.", e)
            self._fallback_count += 1
            return self._fallback_trade(soc, avg_buy_price, buy_threshold, sell_threshold)

    def _fallback_trade(self, soc, avg_buy, buy_th, sell_th) -> TradeDecision:
        """Simple threshold-based fallback."""
        if not self._price_history:
            return TradeDecision(action="hold", confidence=0.5, reasoning="No price history yet")
        price = self._price_history[-1].clearing_price
        if price <= buy_th and soc < 0.9:
            return TradeDecision(action="buy", confidence=0.6, reasoning=f"Price ${price:.4f} below buy threshold")
        if price >= sell_th and soc > 0.15:
            return TradeDecision(action="sell", confidence=0.6, reasoning=f"Price ${price:.4f} above sell threshold")
        return TradeDecision(action="hold", confidence=0.5, reasoning="Price in neutral zone")

    def _parse_trade_response(self, text: str, soc, avg_buy, buy_th, sell_th) -> TradeDecision:
        """Parse Gemini JSON response, fall back on parse failure."""
        try:
            # Strip markdown code fences if present
            clean = text.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            data = json.loads(clean)
            action = data.get("action", "hold").lower()
            if action not in ("buy", "sell", "hold"):
                action = "hold"
            return TradeDecision(
                action=action,
                confidence=float(data.get("confidence", 0.5)),
                reasoning=data.get("reasoning", "Gemini decision"),
            )
        except (json.JSONDecodeError, KeyError, ValueError):
            logger.debug("Failed to parse Gemini response: %s", text[:200])
            self._fallback_count += 1
            return self._fallback_trade(soc, avg_buy, buy_th, sell_th)

    # ------------------------------------------------------------------
    # 2. Market narration (Schelling + grid state)
    # ------------------------------------------------------------------
    async def narrate_market(self, schelling_metrics: dict) -> str:
        """Generate natural language market commentary from grid state.

        Returns a 1-2 sentence narrative for the dashboard.
        """
        if not self.available or not self._rate_limiter.can_call():
            self._fallback_count += 1
            return self._fallback_narration(schelling_metrics)

        history_text = self._format_history()
        prompt = f"""You are a live energy market commentator for a DePIN micro-grid.

MARKET DATA (last {len(self._price_history)} ticks):
{history_text}

SCHELLING CONSENSUS:
- Seller expected price: ${schelling_metrics.get('seller_expected_price', 0):.6f}
- Buyer expected price: ${schelling_metrics.get('buyer_expected_price', 0):.6f}
- Price spread: ${schelling_metrics.get('price_spread', 0):.6f}
- Convergence: {schelling_metrics.get('convergence_pct', 0):.1f}%

Write exactly 1-2 sentences of market commentary. Be specific about prices and trends.
Sound like a Bloomberg terminal analyst. No markdown, no bullet points."""

        try:
            self._rate_limiter.record()
            self._call_count += 1
            result_text = await asyncio.wait_for(
                asyncio.to_thread(self._generate, prompt),
                timeout=self.TIMEOUT_SECONDS,
            )
            narrative = result_text.strip()
            self._last_narrative = narrative
            return narrative
        except Exception as e:
            logger.debug("Gemini narration failed (%s), using fallback.", e)
            self._fallback_count += 1
            return self._fallback_narration(schelling_metrics)

    def _fallback_narration(self, metrics: dict) -> str:
        """Generate basic narrative without Gemini."""
        spread = metrics.get("price_spread", 0)
        conv = metrics.get("convergence_pct", 0)
        if not self._price_history:
            return "Market initializing. Awaiting first trades."
        price = self._price_history[-1].clearing_price
        narrative = f"Clearing at ${price:.4f}/kWh. Schelling convergence {conv:.0f}%, spread ${spread:.6f}."
        self._last_narrative = narrative
        return narrative

    # ------------------------------------------------------------------
    # 3. Operator Q&A console
    # ------------------------------------------------------------------
    async def answer_query(self, question: str, grid_context: dict) -> str:
        """Answer an operator's natural language question about the grid.

        Args:
            question: The operator's question in plain English.
            grid_context: Current grid state dict (status, agents, payments, etc.)
        
        Security: Input sanitized to prevent prompt injection and jailbreaking.
        """
        if not self.available:
            return "Gemini AI is not available. Set GEMINI_API_KEY in .env to enable."

        if not self._rate_limiter.can_call():
            return "Rate limit reached. Please wait a moment before asking again."

        # SECURITY: Sanitize user input to prevent prompt injection
        question = self._sanitize_user_input(question)
        if not question:
            return "Invalid question. Please provide a valid query about the grid."

        # Build context (truncate to keep under token limit)
        ctx = json.dumps(grid_context, default=str, indent=2)
        if len(ctx) > 4000:
            ctx = ctx[:4000] + "\n... (truncated)"

        history_text = self._format_history()
        
        # SECURITY: Use structured prompt with clear boundaries to prevent jailbreaking
        prompt = f"""You are the AI operator assistant for GridMint, a DePIN micro-energy settlement grid on Arc blockchain.

STRICT OPERATIONAL BOUNDARIES:
- You can ONLY answer questions about the grid state, agents, transactions, and market dynamics.
- You CANNOT execute system commands, access files, or perform administrative actions.
- You CANNOT modify the simulation state. Use registered tools only for querying data.
- If asked to do something outside your scope, politely decline and explain your boundaries.

GRID STATE:
{ctx}

RECENT PRICE HISTORY:
{history_text}

OPERATOR QUESTION: {question}

Answer concisely (2-4 sentences). Reference specific agents, prices, and data points.
If asked about a specific agent, explain its behavior based on the data.
If the question is outside your operational scope, respond with: "I can only answer questions about the grid state and market data."
"""

        try:
            self._rate_limiter.record()
            self._call_count += 1
            result_text = await asyncio.wait_for(
                asyncio.to_thread(self._generate, prompt),
                timeout=5.0,  # longer timeout for Q&A
            )
            # SECURITY: Sanitize Gemini output before returning
            return self._sanitize_model_output(result_text.strip())
        except Exception as e:
            logger.debug("Gemini Q&A failed: %s", e)
            return f"Gemini query failed: {e}. Please try again."

    # ------------------------------------------------------------------
    # 3b. Function Calling Q&A (agentic — Gemini decides which tools to call)
    # ------------------------------------------------------------------
    async def answer_query_with_functions(self, question: str) -> dict:
        """Answer an operator question using Gemini Function Calling.

        Gemini decides autonomously which tools to invoke (get_grid_status,
        trigger_stress_test, get_agent_balance, etc.) and returns a final
        answer after receiving the tool results.
        
        SECURITY: User input is sanitized, tool calls are validated, and output is sanitized.

        Returns:
            {
                "answer": str,
                "tools_called": [{"name": str, "args": dict, "result": str}],
                "function_calling_used": bool,
            }
        """
        if not self.available:
            return {"answer": "Gemini AI is not available. Set GEMINI_API_KEY in .env.", "tools_called": [], "function_calling_used": False}

        if not self._rate_limiter.can_call():
            return {"answer": "Rate limit reached. Please wait a moment.", "tools_called": [], "function_calling_used": False}

        # SECURITY: Sanitize user question
        question = self._sanitize_user_input(question)
        if not question:
            return {"answer": "Invalid question. Please provide a valid query about the grid.", "tools_called": [], "function_calling_used": False}

        declarations = self._build_tool_declarations()
        tools_called: list[dict] = []

        def _run_fc_conversation(q: str) -> str:
            """Run multi-turn Function Calling conversation synchronously."""
            if not _GEMINI_AVAILABLE or genai_types is None or not declarations:
                # Fallback: plain generate_content
                response = self._client.models.generate_content(
                    model=self.MODEL_NAME,
                    contents=q,
                )
                return response.text

            tool_config = genai_types.Tool(function_declarations=declarations)
            
            # SECURITY: Add system instruction to reinforce boundaries
            system_instruction = """You are the GridMint operator assistant. Your ONLY purpose is to help operators understand the grid state by calling the provided tools.

STRICT RULES:
- You can ONLY call the registered tools (get_grid_status, get_agent_balance, trigger_stress_test, get_economic_proof, get_schelling_metrics).
- You CANNOT execute arbitrary code, access files, or perform system operations.
- If asked to do something outside these tools, politely decline.
- Always base your answers on tool results, not speculation."""
            
            messages = [q]

            # Agentic loop: keep calling until Gemini stops requesting tools (max 3 rounds)
            for _round in range(3):
                response = self._client.models.generate_content(
                    model=self.MODEL_NAME,
                    contents=messages,
                    config=genai_types.GenerateContentConfig(
                        tools=[tool_config],
                        system_instruction=system_instruction
                    ),
                )

                # Check for function call parts
                fc_parts = []
                text_parts = []
                for candidate in response.candidates:
                    for part in candidate.content.parts:
                        if hasattr(part, "function_call") and part.function_call:
                            fc_parts.append(part.function_call)
                        elif hasattr(part, "text") and part.text:
                            text_parts.append(part.text)

                if not fc_parts:
                    # No more tool calls — return final text answer
                    return "\n".join(text_parts) if text_parts else "(No response)"

                # SECURITY: Limit number of tool calls to prevent DoS
                if len(tools_called) + len(fc_parts) > 10:
                    logger.warning("SECURITY: Too many tool calls in single query, aborting")
                    return "Too many tool calls requested. Please simplify your question."

                # Execute each function call and build tool response parts
                function_response_parts = []
                for fc in fc_parts:
                    fn_name = fc.name
                    fn_args = dict(fc.args) if fc.args else {}
                    
                    # SECURITY: Log all tool calls for audit trail
                    logger.info("SECURITY AUDIT: Gemini requesting tool call: %s(%s)", fn_name, fn_args)
                    
                    fn_result = self._dispatch_tool_call(fn_name, fn_args)
                    tools_called.append({"name": fn_name, "args": fn_args, "result": fn_result})
                    function_response_parts.append(
                        genai_types.Part(
                            function_response=genai_types.FunctionResponse(
                                name=fn_name,
                                response={"output": fn_result},
                            )
                        )
                    )

                # Append model's tool call message + our results to conversation
                messages.append(response.candidates[0].content)
                messages.append(genai_types.Content(role="user", parts=function_response_parts))

            # Exhausted rounds — do one final generation without tools
            final = self._client.models.generate_content(
                model=self.MODEL_NAME,
                contents=messages,
            )
            return final.text

        try:
            self._rate_limiter.record()
            self._call_count += 1
            answer = await asyncio.wait_for(
                asyncio.to_thread(_run_fc_conversation, question),
                timeout=10.0,
            )
            # SECURITY: Sanitize final answer before returning to user
            sanitized_answer = self._sanitize_model_output(answer.strip())
            
            return {
                "answer": sanitized_answer,
                "tools_called": tools_called,
                "function_calling_used": len(tools_called) > 0,
            }
        except Exception as e:
            logger.warning("Gemini Function Calling Q&A failed: %s", e)
            self._fallback_count += 1
            return {
                "answer": f"Gemini function calling failed: {e}. Try /api/gemini/ask for plain Q&A.",
                "tools_called": tools_called,
                "function_calling_used": False,
            }
    async def end_of_cycle_analysis(self, summary: dict) -> str:
        """Generate a comprehensive end-of-simulation executive summary.

        Called once when the simulation stops. Uses all available data
        to produce a detailed analysis for judges.
        """
        if not self.available:
            return self._fallback_analysis(summary)

        if not self._rate_limiter.can_call():
            return self._fallback_analysis(summary)

        prompt = f"""You are an energy market analyst writing an executive summary for a DePIN micro-energy grid simulation on Arc blockchain.

SIMULATION RESULTS:
- Total ticks: {summary.get('total_ticks', 0)}
- Total transactions: {summary.get('total_tx', 0)}
- Total USDC settled: ${summary.get('total_usd', 0):.6f}
- Average cost per transaction: ${summary.get('avg_cost_per_tx', 0):.8f}
- Equivalent Ethereum gas cost: ${summary.get('eth_gas_cost', 0):.2f}
- Arc savings factor: {summary.get('savings_factor', 0):.1f}x cheaper
- Green energy percentage: {summary.get('green_pct', 0):.1f}%
- Schelling convergence: {summary.get('schelling_convergence', 0):.1f}%
- Schelling price spread: ${summary.get('schelling_spread', 0):.6f}

PRICE HISTORY:
{self._format_history()}

Write a 4-5 sentence executive summary covering:
1. Market efficiency (did agents converge to fair pricing?)
2. Economic viability (Arc vs traditional blockchain costs)
3. Grid health (supply/demand balance, green energy mix)
4. Key insight or anomaly observed
Sound authoritative. Use specific numbers."""

        try:
            self._rate_limiter.record()
            self._call_count += 1
            result_text = await asyncio.wait_for(
                asyncio.to_thread(self._generate, prompt),
                timeout=10.0,
            )
            return result_text.strip()
        except Exception as e:
            logger.debug("Gemini analysis failed: %s", e)
            return self._fallback_analysis(summary)

    def _fallback_analysis(self, summary: dict) -> str:
        total_tx = summary.get('total_tx', 0)
        total_usd = summary.get('total_usd', 0)
        savings = summary.get('savings_factor', 0)
        green = summary.get('green_pct', 0)
        return (
            f"GridMint completed {total_tx} transactions settling ${total_usd:.6f} USDC. "
            f"Arc settlement was {savings:.0f}x cheaper than Ethereum equivalent. "
            f"{green:.0f}% of energy traded was from renewable solar sources."
        )

    # ------------------------------------------------------------------
    # SECURITY LAYER: Input/Output Sanitization
    # ------------------------------------------------------------------
    
    def _sanitize_user_input(self, user_input: str) -> str:
        """Sanitize user input to prevent prompt injection and jailbreaking.
        
        Security measures:
        1. Strip all control characters and excessive whitespace
        2. Remove potential injection patterns (system prompts, role instructions)
        3. Limit length to prevent context overflow attacks
        4. Block common jailbreak patterns
        5. Escape special characters that could break prompt boundaries
        
        Returns sanitized string or empty string if input is invalid.
        """
        import re
        
        if not isinstance(user_input, str):
            logger.warning("SECURITY: Non-string input rejected: %s", type(user_input))
            return ""
        
        # Strip control characters and excessive whitespace
        sanitized = user_input.strip()
        sanitized = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', sanitized)  # Remove control chars
        sanitized = re.sub(r'\s+', ' ', sanitized)  # Normalize whitespace
        
        # Length limit (prevent context overflow DoS)
        if len(sanitized) > 600:
            logger.warning("SECURITY: Input truncated from %d to 600 chars", len(sanitized))
            sanitized = sanitized[:600]
        
        # Block common prompt injection patterns (case-insensitive)
        injection_patterns = [
            r'ignore\s+(previous|all|above|prior)\s+(instructions?|prompts?|rules?)',
            r'you\s+are\s+now\s+a',
            r'forget\s+(everything|all|your)',
            r'system\s*:\s*',
            r'assistant\s*:\s*',
            r'<\s*system\s*>',
            r'\[system\]',
            r'new\s+instructions?',
            r'override\s+(instructions?|mode|rules?)',
            r'jailbreak',
            r'pretend\s+you\s+are',
            r'act\s+as\s+if',
            r'sudo\s+',
            r'exec\(.*\)',
            r'eval\(.*\)',
            r'__import__',
            r'subprocess\.',
            r'os\.(system|popen|exec)',
        ]
        
        for pattern in injection_patterns:
            if re.search(pattern, sanitized, re.IGNORECASE):
                logger.warning("SECURITY: Injection pattern detected and blocked: %s", pattern)
                return ""  # Reject entire input if injection attempt detected
        
        # Escape characters that could break prompt boundaries
        # Replace triple backticks (markdown code blocks) with single backticks
        sanitized = sanitized.replace('```', '`')
        
        # Remove any attempt to close/reopen JSON blocks
        sanitized = sanitized.replace('"""', '"')
        sanitized = sanitized.replace("'''", "'")
        
        return sanitized
    
    def _sanitize_model_output(self, model_output: str) -> str:
        """Sanitize Gemini output to prevent code injection in frontend.
        
        Security measures:
        1. Validate output is safe plain text
        2. Strip any embedded script tags or HTML
        3. Remove potential XSS vectors
        4. Limit output length
        
        Returns sanitized model output.
        """
        import re
        
        if not isinstance(model_output, str):
            return "(Invalid model output)"
        
        sanitized = model_output.strip()
        
        # Length limit (prevent response overflow)
        if len(sanitized) > 5000:
            logger.warning("SECURITY: Model output truncated from %d to 5000 chars", len(sanitized))
            sanitized = sanitized[:5000] + "... (truncated for safety)"
        
        # Remove HTML/script tags (XSS prevention)
        sanitized = re.sub(r'<script[^>]*>.*?</script>', '', sanitized, flags=re.DOTALL | re.IGNORECASE)
        sanitized = re.sub(r'<iframe[^>]*>.*?</iframe>', '', sanitized, flags=re.DOTALL | re.IGNORECASE)
        sanitized = re.sub(r'<object[^>]*>.*?</object>', '', sanitized, flags=re.DOTALL | re.IGNORECASE)
        sanitized = re.sub(r'<embed[^>]*>', '', sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r'on\w+\s*=\s*["\'][^"\']*["\']', '', sanitized, flags=re.IGNORECASE)  # Remove event handlers
        
        # Remove javascript: and data: URLs
        sanitized = re.sub(r'javascript\s*:', '', sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r'data\s*:\s*text/html', '', sanitized, flags=re.IGNORECASE)
        
        return sanitized
    
    def _validate_tool_arguments(self, tool_name: str, args: dict) -> tuple[bool, str]:
        """Validate tool arguments against expected schemas to prevent malicious payloads.
        
        Returns (is_valid, error_message)
        """
        # Tool-specific validation rules
        validation_rules = {
            "get_agent_balance": {
                "agent_id": lambda v: isinstance(v, str) and len(v) <= 64 and v.replace('-', '').replace('_', '').isalnum()
            },
            "trigger_stress_test": {
                "scenario": lambda v: isinstance(v, str) and v in ["solar_crash", "demand_spike", "battery_failure", "price_war", "night_mode"]
            },
        }
        
        if tool_name not in validation_rules:
            return (True, "")  # No specific rules, allow
        
        rules = validation_rules[tool_name]
        for arg_name, validator in rules.items():
            if arg_name in args:
                if not validator(args[arg_name]):
                    return (False, f"Invalid argument '{arg_name}': validation failed")
        
        return (True, "")

    # ------------------------------------------------------------------
    # Utility methods
    # ------------------------------------------------------------------
    def _format_history(self) -> str:
        if not self._price_history:
            return "(no data yet)"
        lines = []
        for s in self._price_history:
            lines.append(
                f"  Tick {s.tick} | Hour {s.sim_hour:.1f} | "
                f"Price ${s.clearing_price:.4f} | "
                f"Supply {s.supply_kwh:.2f} kWh | "
                f"Demand {s.demand_kwh:.2f} kWh"
            )
        return "\n".join(lines)
