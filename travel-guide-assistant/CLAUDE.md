# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TravelMate is a single-user, locally run travel-guide assistant. It pairs a Chinese-language AI chat/planner frontend with a FastAPI backend that answers travel questions (RAG over a local knowledge base) and generates editable day-by-day itineraries. It is maintained for local, single-user use: SQLite, Chroma, and a DeepSeek-compatible LLM all run on the same machine (see `LOCAL_USE.md`). PostgreSQL/Qdrant/Docker/cloud deployment are explicitly out of scope.

## Layout

- `pages/*.html` — static HTML pages (assistant, planner, destination, etc.), served directly over `http.server` (no build step).
- `shared/*.js` — browser utilities exposed on `window.TravelMate`: `api.js` (SSE chat + trip REST client), `assistant-response.js` (stream rendering/markdown cleanup), `components.js` (shared UI components), `site-nav.js`, `utils.js`. All in the two-space, semicolon-terminated IIFE style — there is no bundler or module system; pages load these via `<script src="../shared/...">`.
- `assets/` — icons and frontend resources. `colors_and_type.css` / `theme.css` hold design tokens.
- `backend/app/main.py` — FastAPI entry point and the only route module. `app/core/config.py` loads env-based settings. `app/models/schemas.py` holds all Pydantic models. `app/services/` has `rag_chat.py` (chat orchestration) and `trips.py` (SQLite persistence). `app/rag/` is the retrieval pipeline.
- `backend/data/knowledge/` — markdown/JSON knowledge files organized under `destinations/`, `guides/`, `itineraries/`, `pois/`, `tools/`. Filenames are lowercase kebab-case (e.g. `japan-kansai.md`).
- `backend/scripts/` — `ingest.py` (knowledge → vector store) and `local_data.py` (backup/restore).
- `backend/tests/{unit,integration,contract}` — pytest suite. `frontend/tests/` — Vitest; `frontend/e2e/` — Playwright.

## Commands

Backend commands run from `travel-guide-assistant/backend` (the venv lives in `backend/.venv`):

```text
python -m pip install -r requirements.txt     # first-time setup
python -m pytest                              # full backend suite
python -m pytest tests/unit/test_rag_pipeline.py   # single test file
python -m pytest tests/unit/test_rag_pipeline.py::test_name -k pattern
uvicorn app.main:app --reload                 # serve API on localhost:8000
python scripts/ingest.py --dry-run            # preview knowledge ingestion
python scripts/ingest.py --reset              # wipe + re-ingest knowledge base
python scripts/evaluate_retrieval.py          # run retrieval quality metrics
python scripts/verify_backup.py --backup-path backups/<timestamp>  # validate backup integrity
```

Frontend commands run from `travel-guide-assistant/`:

```text
npm install            # once
npm test               # Vitest + React Testing Library (jsdom), runs frontend/tests
npm run test:e2e       # Playwright; config auto-launches frontend (5501) + backend (8000)
python -m http.server 5500   # static preview, then open pages/home.html
```

Start/stop/backup scripts at the repo root: `start-travelmate.cmd`, `stop-travelmate.cmd`, `backup-travelmate.cmd`, `restore-latest-travelmate.cmd` (thin wrappers over PowerShell in `scripts/local/`). Logs go to `.local/logs/`.

## Backend Architecture

**API surface** (`app/main.py`): `/api/health` (includes index health + embedding compatibility check), CRUD under `/api/trips` (persisted to SQLite via `TripStore` in `app/services/trips.py`), and `POST /api/chat` which returns an SSE stream (`sse-starlette`). The SSE contract has four events — `message` (text chunk + citations), `itinerary` (structured `Itinerary` + citations), `done` (id + session_id + usage + metrics), `error` (code + message). `frontend/tests/assistant-contract.test.js` and `backend/tests/contract/test_sse_contract.py` pin these shapes; update both when the contract changes.

**Chat flow** (`app/services/rag_chat.py`): `RAGChatService.respond()` retrieves context, detects itinerary intent, builds a prompt (system instruction + retrieved sources + capped history, `MAX_TURNS=3`, `MAX_TEXT_CHARS=8000`), calls the LLM, and falls back to a deterministic local LLM on transport failure. `ConversationStore` keeps a 24-hour in-memory session window (`SESSION_TTL`). Itinerary intent is detected by keyword heuristics in `app/rag/pipeline.py` (`is_plan_intent`, `detect_destination`, `detect_days`). The service has both `respond()` (non-streaming) and `stream()` (streaming) methods; main.py adapts both to the SSE contract.

**LLM selection**: `build_default_llm()` in `rag_chat.py` picks `DeterministicLocalLLM` when `TRAVELMATE_LLM_PROVIDER=local` (or no key), else `DeepSeekLLMAdapter` when `DEEPSEEK_API_KEY` is set in `backend/.env`. The key lives only in gitignored `backend/.env`; `.env.example` documents the fields. Playwright e2e forces `TRAVELMATE_LLM_PROVIDER=local` for deterministic runs. The DeepSeek adapter supports both streaming (`stream()`) and non-streaming (`complete()`) modes, with automatic `response_format: json_object` when itinerary intent is detected.

**Vector store** (`app/rag/chroma_store.py`): critical gotcha — `USE_CHROMA = os.name != "nt" or os.getenv("TRAVELMATE_VECTOR_BACKEND") == "chroma"`. On Windows, Chroma's HNSW native library is skipped by default and a JSON-file fallback store (`_JsonVectorStore`) is used instead; set `TRAVELMATE_VECTOR_BACKEND=chroma` to force real Chroma anywhere. Both backends share the `ChromaIndexer`/`ChromaRetriever` API. Embeddings come from `HashEmbedding` (character n-gram hashing, offline, zero model download) when `TRAVELMATE_EMBEDDING_PROVIDER=hash`, or `sentence_transformers` (BAAI/bge-small-zh-v1.5) when explicitly configured; `build_embedding_fn()` is the swap point. `ingest()` is idempotent per `(source_id, version)` and splits documents line-by-line (each non-blank line is one chunk). Citation scores are thresholded differently per caller: `rag_chat.MIN_SCORE = 0.3`, `pipeline.mock_citations` uses `0.01`. The retriever supports hybrid search with configurable dense/lexical weights (defaults: 55%/45%).

**Pydantic models** (`app/models/schemas.py`): `DayPlan`, `Itinerary`, `Trip` (Itinerary + id/timestamps), `Citation`, `ChatRequest`, and SSE event models. LLM JSON output is validated into `Itinerary` by `parse_llm_output()` in `app/rag/llm_output.py`, which degrades bad JSON to plain text (`error_code="invalid_json"`) rather than throwing.

## Frontend Architecture

No framework or bundler. Each `pages/*.html` is standalone and wires up behavior with inline scripts plus `shared/*.js` IIFE modules. `window.TravelMate.api` (`shared/api.js`) is the single API client: `chatStream()` reads the SSE body via `fetch` + `ReadableStream`, dispatching to `onMessage`/`onItinerary`/`onDone`/`onError` handlers; trip CRUD uses `saveTrip`/`getTrip`/`listTrips`/`updateTrip`. The API base defaults to `http://127.0.0.1:8000` and can be overridden via `window.TravelMateConfig.API_BASE`.

Many frontend tests are contract tests that read page HTML as text and assert on classes, IDs, and wired calls (e.g. `assistant.html` must reference `chatStream`, `saveTrip`, `cleanMarkdownForDisplay`, etc.). When changing a page's DOM, check `frontend/tests/*.test.js` for string assertions that pin the old markup.

## Tests & Conventions

- **Backend**: pytest configured by `backend/pytest.ini` (`asyncio_mode = auto`, testpaths `tests`, pythonpath `.`); `backend/conftest.py` puts the backend root on `sys.path`. Group: unit / integration / contract (SSE shape). Add a regression test for behavior changes.
- **Frontend**: Vitest (jsdom) for unit/contract, Playwright (`frontend/e2e/`, channel=chrome) for full-stack flows against both servers. Playwright auto-starts frontend (5501) + backend (8000) with `TRAVELMATE_LLM_PROVIDER=local`.
- **Style**: Python — 4 spaces, `snake_case` functions/modules/vars, `PascalCase` Pydantic models. JS — 2 spaces, semicolons, `camelCase`, IIFE pattern. Knowledge filenames lowercase kebab-case. No formatter or linter is configured; keep diffs focused and match nearby code.
- **Commits**: Conventional Commit style used in history, e.g. `feat(rag): ...`, `fix(frontend): ...` (messages are bilingual Chinese/English in history).
- Never commit API keys, `backend/.env`, `.venv`, vector-store artifacts (`backend/chroma_data*`, `index_versions/`), or SQLite databases — all gitignored.

## Data & Operations

- Knowledge ingestion: `python scripts/ingest.py` (from `backend/`) indexes `backend/data/knowledge/*.md|*.json` into the vector store. Re-run `--reset` after editing knowledge files to refresh.
- Embedding model upgrade: Use `backend/scripts/build_bge_index.ps1` to build a versioned BGE index with pre-deployment validation (runs retrieval tests before activating). Configure via `TRAVELMATE_INDEX_ROOT` + `TRAVELMATE_INDEX_VERSION` in `backend/.env`; the script manages `index_versions/active.json` to point to the validated version.
- Index health: Check `/api/health` for `embedding_compatible` (current runtime vs persisted index) and `manifest.compatible` (schema compatibility). The startup validator logs warnings when a rebuild is needed.
- Backups (`scripts/local_data.py`, `.cmd` wrappers) snapshot `trips.db` + `chroma_data/` (or versioned indexes when using `TRAVELMATE_INDEX_ROOT`) with a manifest. Browser nickname/avatar/preferences live in localStorage and are **not** part of backups.
- `.local/` holds runtime logs and pre-restore snapshots; `backups/` holds timestamped backups; both gitignored.
