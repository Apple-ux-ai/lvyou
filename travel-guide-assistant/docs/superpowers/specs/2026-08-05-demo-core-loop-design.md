# TravelMate Demo Core Loop Design

**Date:** 2026-08-05  
**Status:** Approved for implementation

## Goal

Deliver one reliable, demonstrable journey through the existing application:

`Home prompt -> AI response -> itinerary preview -> planner edit -> save -> profile list -> reopen`

The saved itinerary must remain available after refreshing the browser or restarting the backend. Existing page styling and shared navigation remain unchanged except where new loading, empty, success, or error states are required.

## Scope

This phase connects `pages/home.html`, `pages/assistant.html`, `pages/planner.html`, and `pages/profile.html` to the existing FastAPI backend. It does not add production authentication, real-user ownership, maps, PDF export, collaboration, community APIs, or a new LLM provider.

## Data Ownership and Persistence

The backend is the source of truth for saved trips. Browser `localStorage` remains limited to unsaved planner drafts and chat sessions.

Replace the process-memory `TripStore` with a SQLite-backed store using Python's standard `sqlite3` module. Store each validated itinerary as JSON with its ID and timestamps. The database location is configurable through `TRAVELMATE_DB_PATH`, with a repository-local development default under `backend/data/`. Database initialization is automatic.

## API Contract

Keep the existing endpoints and add the missing collection/update operations:

- `POST /api/trips`: create a trip and return the stored `Trip`.
- `GET /api/trips`: return saved trips ordered newest first.
- `GET /api/trips/{trip_id}`: return one trip or `404`.
- `PUT /api/trips/{trip_id}`: replace itinerary fields, preserve the ID, and return the updated trip.

Pydantic models remain the validation boundary. Malformed payloads return FastAPI's normal `422` response. Unknown IDs return a consistent `404` response.

## Frontend Flow

1. The home page sends the user's prompt to `assistant.html?query=...`.
2. The assistant consumes the existing SSE `message`, `itinerary`, `done`, and `error` events.
3. "Edit itinerary" converts the generated itinerary to the planner model and opens `planner.html` with a local draft.
4. Saving from either assistant or planner calls the backend. The returned trip ID is retained and duplicate clicks are disabled while saving.
5. The profile page loads `GET /api/trips`, renders real trip cards, and provides loading, empty, and retry states.
6. Selecting a saved trip opens `planner.html?tripId=...`; the planner fetches it and saves later edits with `PUT`.

The API wrapper in `shared/api.js` owns HTTP and response parsing. Pages own display state and navigation. Static sample trips may be retained only as explicitly labeled visual fallback data during a backend failure; they must not appear as saved user data.

## Failure Handling

Backend unavailability, SSE errors, failed saves, empty itineraries, and unknown trip IDs must produce visible Chinese messages with a retry or return action where useful. Failed requests must not discard the current itinerary or local draft.

## Verification

Backend tests cover database initialization, create/list/get/update, persistence across store instances, validation, and `404` behavior. Frontend tests cover the API methods and planner model conversion. Playwright covers the full deterministic journey from the home page through reopening a saved trip. Existing frontend and backend test suites must continue to pass.

## Acceptance Criteria

- A user can complete the core journey without typing a URL manually.
- Saved trips appear in the profile and reopen with the same content.
- Planner edits survive browser refresh and backend restart after saving.
- Repeated save clicks do not create accidental duplicates.
- Desktop and mobile layouts have no blocking overlap or unreachable action.
