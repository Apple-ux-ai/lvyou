# Repository Guidelines

## Project Structure & Module Organization

This is a local TravelMate app. Static pages are in `pages/`; reusable browser code and styles are in `shared/`; icons and other assets are in `assets/`. The FastAPI service is in `backend/app/`, with Pydantic models in `models/`, API services in `services/`, and RAG, indexing, embedding, and Chroma code in `rag/`. Knowledge sources live in `backend/data/knowledge/`; versioned indexes live in `backend/index_versions/`. Backend tests are grouped under `backend/tests/{unit,integration,contract}`. Frontend unit/contract tests are in `frontend/tests/`, and Playwright flows are in `frontend/e2e/`.

## Build, Test, and Development Commands

Run from the repository root unless noted:

```powershell
npm install                                  # install frontend/test dependencies
npm test                                     # run Vitest tests
npm run test:e2e                             # run Playwright; starts ports 5501 and 8000
cd backend; python -m venv .venv              # create backend environment
python -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pytest -q        # run backend tests
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

For the normal local workflow, use `start-travelmate.cmd`; it launches the frontend and API and writes logs under `.local/logs/`. A static-only preview is `python -m http.server 5500` from the root.

## Coding Style & Naming Conventions

Match nearby code: four-space indentation and `snake_case` in Python; two-space, semicolon-terminated JavaScript with `camelCase` functions and `PascalCase` UI concepts. Use lowercase kebab-case for knowledge filenames, such as `japan-kansai.md`. No formatter or linter is configured, so keep changes focused and avoid unrelated reformatting.

## Testing Guidelines

Pytest uses `backend/pytest.ini` with `tests/` as its root and automatic asyncio support. Name Python tests `test_*.py`; keep new tests beside the unit, integration, or SSE contract they cover. Add regression coverage for behavior changes and update contract tests when API/SSE shapes change. Use local LLM mode for deterministic end-to-end tests.

## Commit & Pull Request Guidelines

Existing commits use concise imperative subjects such as `Add complete travel guide assistant application`. Follow that style, optionally adding a scope (`Fix rag retrieval fallback`). PRs should describe behavior changes, list commands run, call out config or knowledge-index changes, and include screenshots for UI changes. Never commit `backend/.env`, API keys, `.venv/`, or generated local data.

## Security & Configuration Tips

Keep secrets in the gitignored `backend/.env`, based on `backend/.env.example`. Review CORS and external-provider settings before deployment; the local defaults are for development only.
