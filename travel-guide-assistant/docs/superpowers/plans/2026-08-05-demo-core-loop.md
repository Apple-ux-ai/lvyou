# Demo Core Loop Implementation Plan

**Status:** Completed on 2026-08-05. Verified with 59 backend tests, 20 frontend tests, the Node SSE contract test, and the Playwright core-loop test.

> Execute task by task. Keep the existing page styling and preserve unrelated user changes.

**Goal:** Make the primary TravelMate flow demonstrable end to end: home prompt, AI itinerary, editing, backend save, profile listing, and reopening.

**Design:** Use SQLite through Python's standard `sqlite3` module for saved trips. Keep browser storage for drafts/sessions only. Add collection/update API operations, then connect the existing static profile and planner surfaces to those APIs.

**Verification:** Run focused tests after each layer, then `npm test`, backend pytest, and Playwright's full-flow suite with both local services.

## Task 1: Persistent Trip Store and API Contract

**Files:** `backend/app/services/trips.py`, `backend/app/models/schemas.py`, `backend/app/main.py`, `backend/data/.gitkeep`, `backend/.gitignore`

- Add a configurable SQLite-backed `TripStore` with automatic table initialization.
- Store validated itinerary JSON, ID, and created/updated timestamps.
- Implement `create`, `list`, `get`, and `update` methods with newest-first ordering.
- Add `GET /api/trips` and `PUT /api/trips/{trip_id}` while preserving existing create/get behavior.
- Keep all request validation at the Pydantic boundary and return `404` for unknown IDs.

## Task 2: Backend Regression Tests

**Files:** `backend/tests/integration/test_trips_api.py`, `backend/tests/unit/test_trip_store.py`

- Add isolated temporary-database tests for initialization, create/list/get/update, and persistence across store instances.
- Extend API tests for list ordering, update, validation, and missing IDs.
- Ensure tests do not write into the development database.

## Task 3: Frontend API and Assistant Save Flow

**Files:** `shared/api.js`, `shared/api.test.js`, `frontend/tests/api-client.test.js`, `pages/assistant.html`

- Add API wrapper methods for list/update and normalize HTTP errors.
- Make assistant save state disable repeated saves, retain the returned trip ID, and expose a direct link to the saved trip/profile.
- Keep the generated itinerary available when saving fails and show an actionable inline error.
- Preserve the existing SSE event contract and chat behavior.

## Task 4: Planner and Profile Integration

**Files:** `pages/planner.html`, `pages/profile.html`, `frontend/tests/navigation.test.js`, `frontend/tests/profile-contract.test.js`, `frontend/tests/planner-contract.test.js`

- Load `planner.html?tripId=...` from the API; retain local draft loading for unsaved plans.
- Convert planner edits back to API itinerary shape and use create for new drafts or update for existing trips.
- Replace static trip cards with API-backed loading, empty, error, and retry states.
- Open saved cards in the planner with the real trip ID and keep the existing new-trip entry.
- Keep visual conventions and responsive layout consistent with the current pages.

## Task 5: Full-Flow Verification and Documentation

**Files:** `frontend/e2e/demo-core-loop.spec.js`, `FINAL_PLAN.md`, `ROADMAP.md`

- Add a deterministic Playwright flow covering home navigation, assistant generation, edit, save, profile listing, and reopen.
- Run frontend unit tests, backend tests, and the E2E flow against local services.
- Update project documentation to mark the completed foundation and identify the next deferred phase: real model configuration and user accounts.
- Record any environment limitation, especially temporary-directory or service-port issues, instead of masking failures.
