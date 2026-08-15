# Repository Guidelines

## Project Structure & Module Organization

`pages/` contains the static HTML views, `shared/` holds reusable browser utilities, shared components, and API/SSE client code, and `assets/` contains icons and other frontend resources. The Python service lives in `backend/`: `app/main.py` defines the FastAPI entry point, `app/models/` contains Pydantic schemas, and `app/rag/` contains retrieval, indexing, Chroma, and response-pipeline code. Knowledge files are under `backend/data/knowledge/`; tests are grouped in `backend/tests/unit`, `integration`, and `contract`. Frontend tests live in `frontend/tests/`.

## Build, Test, and Development Commands

Run backend commands from `travel-guide-assistant/backend`:

```text
python -m venv .venv
python -m pip install -r requirements.txt
python -m pytest                  # run the complete test suite
uvicorn app.main:app --reload    # serve the API on localhost:8000
```

To preview the static frontend, run `python -m http.server 5500` from `travel-guide-assistant/`, then open `pages/home.html`. The frontend expects the API at `http://localhost:8000` unless `window.TravelMateConfig.API_BASE` overrides it.

From `travel-guide-assistant/`, run `npm install` once, then `npm test` to run the Vitest and React Testing Library suite.

## Coding Style & Naming Conventions

Use four spaces and `snake_case` for Python functions, modules, and variables; use `PascalCase` for Pydantic models. Keep JavaScript in the existing two-space, semicolon-terminated IIFE style, with `camelCase` functions and `PascalCase` UI concepts. Use lowercase kebab-case for knowledge filenames (for example, `japan-kansai.md`). No formatter or linter is configured, so keep diffs focused and match nearby code.

## Testing Guidelines

Pytest is configured by `backend/pytest.ini` with `tests/` as the root and automatic asyncio support. Name test files `test_*.py` and keep unit, integration, and SSE contract coverage in their corresponding directories. Run `python -m pytest` before submitting backend changes and `npm test` before frontend changes; add a regression test for behavior changes and update contract tests when SSE event shapes change.

## Commit & Pull Request Guidelines

This checkout has no Git history available, so no existing commit convention can be verified. Use concise imperative messages, preferably Conventional Commit style such as `feat(rag): add citation metadata` or `fix(frontend): handle SSE errors`. PRs should explain the behavior change, list tests run, note configuration or knowledge-data changes, and include screenshots for visible page changes. Never commit API keys, local vector-store artifacts, or `.venv` contents.

## Security & Configuration Tips

Keep secrets and environment-specific API URLs out of tracked HTML and Python files. Review CORS and external API settings before deployment; the current permissive CORS setup is intended for development only.
