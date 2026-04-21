#!/usr/bin/env python
"""Entry point to start the GridMint orchestrator server."""
import sys
import os

# Ensure gridmint package root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.orchestrator import app
import uvicorn

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
