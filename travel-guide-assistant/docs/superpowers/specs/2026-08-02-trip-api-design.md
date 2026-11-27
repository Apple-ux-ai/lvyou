# Trip API Design

## Goal

Complete the assistant's current save flow by adding APIs that create and retrieve an itinerary during a running FastAPI process.

## Design

`POST /api/trips` accepts the existing `Itinerary` request shape and returns the same itinerary fields plus a generated `id` with HTTP 201. `GET /api/trips/{id}` returns that saved record or HTTP 404 when it is absent. A small `TripStore` service owns the in-memory dictionary so routing remains limited to HTTP concerns.

The store is intentionally process-local. It provides the M3 browser flow without adding PostgreSQL configuration before the persistence layer is designed. Restarting the API clears saved trips; replacing the store with a repository is a later, compatible change.

## Validation

Integration tests will exercise real FastAPI routes through `httpx` and verify creation, read-back fidelity, and the missing-ID error. Existing SSE behavior remains unchanged.
