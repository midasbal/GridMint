Contribution guidelines

This repository now uses a React (Vite) frontend served separately from the Python FastAPI backend.

To run locally:
1. Backend: cd gridmint && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && uvicorn engine.orchestrator:app --reload
2. Frontend: cd frontend && npm install && npm run dev

Cleanup policy: legacy Streamlit files were deprecated and may be removed. If you need them for reference, check the .cleanup_remove_list.txt file.
