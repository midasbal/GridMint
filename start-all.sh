#!/usr/bin/env bash
# ============================================================
# GridMint — One-Click Demo Startup
# Launches:
#   - FastAPI backend        → http://localhost:8000
#   - Circle Nanopayments    → http://localhost:4402
#   - React frontend (opt)   → http://localhost:5173
#
# Usage:
#   ./start-all.sh          # Start backend + nanopayments
#   ./start-all.sh --ui     # Also start the React frontend
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Colors ─────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

# ── Cleanup on exit ────────────────────────────────────────
PIDS=()
cleanup() {
  echo -e "\n${YELLOW}Shutting down GridMint services...${RESET}"
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
  echo -e "${GREEN}All services stopped.${RESET}"
}
trap cleanup EXIT INT TERM

echo -e "${BOLD}${CYAN}"
echo "╔══════════════════════════════════════════════════════════╗"
echo "║            GridMint — Agentic Energy Market              ║"
echo "║        Circle Nanopayments + Arc Testnet + Gemini        ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo -e "${RESET}"

# ── Verify .env ────────────────────────────────────────────
if [ ! -f ".env" ]; then
  echo -e "${RED}✗ .env file not found. Copy .env.example → .env and fill in keys.${RESET}"
  exit 1
fi
echo -e "${GREEN}✓ .env found${RESET}"

# ── Verify Python venv ─────────────────────────────────────
PYTHON_CMD=""
if [ -f ".venv/bin/python" ]; then
  PYTHON_CMD=".venv/bin/python"
elif command -v python3 &>/dev/null; then
  PYTHON_CMD="python3"
else
  echo -e "${RED}✗ Python not found. Please install Python 3.10+ and run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt${RESET}"
  exit 1
fi
echo -e "${GREEN}✓ Python: $($PYTHON_CMD --version)${RESET}"

# ── Verify Node.js ──────────────────────────────────────────
if ! command -v node &>/dev/null; then
  echo -e "${RED}✗ Node.js not found. Install from https://nodejs.org${RESET}"
  exit 1
fi
echo -e "${GREEN}✓ Node.js: $(node --version)${RESET}"

# ── Install nanopayments deps if needed ─────────────────────
if [ ! -d "nanopayments/node_modules" ]; then
  echo -e "${YELLOW}Installing nanopayments Node.js dependencies...${RESET}"
  (cd nanopayments && npm install --silent)
fi
echo -e "${GREEN}✓ nanopayments/node_modules ready${RESET}"

echo ""
echo -e "${BOLD}Starting services...${RESET}"
echo ""

# ── Service 1: FastAPI backend (port 8000) ──────────────────
echo -e "${CYAN}[1/2] Starting FastAPI backend on http://localhost:8000 ...${RESET}"
(
  cd "$SCRIPT_DIR"
  if [ -f ".venv/bin/uvicorn" ]; then
    UVICORN=".venv/bin/uvicorn"
  elif command -v uvicorn &>/dev/null; then
    UVICORN="uvicorn"
  else
    echo -e "${RED}✗ uvicorn not found. Run: pip install -r requirements.txt${RESET}"
    exit 1
  fi
  "$UVICORN" engine.orchestrator:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload \
    --log-level info \
    2>&1 | sed "s/^/${GREEN}[FastAPI]${RESET} /"
) &
FASTAPI_PID=$!
PIDS+=("$FASTAPI_PID")

# ── Service 2: Circle Nanopayments server (port 4402) ───────
echo -e "${CYAN}[2/2] Starting Circle Nanopayments Gateway on http://localhost:4402 ...${RESET}"
(
  cd "$SCRIPT_DIR/nanopayments"
  npm start 2>&1 | sed "s/^/${YELLOW}[Nanopayments]${RESET} /"
) &
NANO_PID=$!
PIDS+=("$NANO_PID")

# ── Optional: React frontend (port 5173) ────────────────────
if [[ "${1:-}" == "--ui" ]]; then
  if [ ! -d "frontend/node_modules" ]; then
    echo -e "${YELLOW}Installing frontend dependencies...${RESET}"
    (cd frontend && npm install --silent)
  fi
  echo -e "${CYAN}[3/3] Starting React frontend on http://localhost:5173 ...${RESET}"
  (
    cd "$SCRIPT_DIR/frontend"
    npm run dev 2>&1 | sed "s/^/${RED}[Frontend]${RESET} /"
  ) &
  UI_PID=$!
  PIDS+=("$UI_PID")
fi

# ── Wait for FastAPI to be ready ────────────────────────────
echo ""
echo -e "${YELLOW}Waiting for services to initialize...${RESET}"
READY=0
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    READY=1; break
  fi
  sleep 1
done

echo ""
if [ "$READY" -eq 1 ]; then
  echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════════════╗${RESET}"
  echo -e "${GREEN}${BOLD}║  ✅  GridMint is LIVE                                     ║${RESET}"
  echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════════════════╝${RESET}"
  echo ""
  echo -e "  ${BOLD}FastAPI Backend:${RESET}        http://localhost:8000"
  echo -e "  ${BOLD}API Docs (Swagger):${RESET}     http://localhost:8000/docs"
  echo -e "  ${BOLD}Circle Nanopayments:${RESET}    http://localhost:4402"
  echo -e "  ${BOLD}Nanopayments Health:${RESET}    http://localhost:4402/nanopayments/health"
  echo -e "  ${BOLD}Live Proof:${RESET}             http://localhost:8000/api/live-proof/full"
  echo -e "  ${BOLD}Economic Proof (free):${RESET}  http://localhost:8000/api/economic-proof"
  echo -e "  ${BOLD}Economic Proof (paid):${RESET}  http://localhost:4402/api/economic-proof  ← \$0.003 USDC"
  if [[ "${1:-}" == "--ui" ]]; then
    echo -e "  ${BOLD}React Dashboard:${RESET}        http://localhost:5173"
  fi
  echo ""
  echo -e "  ${BOLD}Agent Settlement Mode:${RESET}  $(grep CIRCLE_SETTLEMENT_BACKEND .env 2>/dev/null | cut -d= -f2 || echo 'erc20')"
  echo -e "  ${BOLD}Nanopayments Demo:${RESET}       cd nanopayments && npm run buyer"
  echo ""
  echo -e "${YELLOW}Press Ctrl+C to stop all services.${RESET}"
else
  echo -e "${RED}⚠  FastAPI backend did not respond within 30s. Check logs above.${RESET}"
fi

# ── Wait for all background processes ───────────────────────
wait
