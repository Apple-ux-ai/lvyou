# TravelMate Personal Local Runtime Design

## Goal

Turn the existing project into a dependable single-user local application without accounts, Docker, or a server deployment.

## Runtime

The root `start-travelmate.cmd` launcher calls a PowerShell controller. The controller validates the Python virtual environment, starts FastAPI on port 8000 and the static frontend on port 5501 in hidden processes, waits for both health URLs, writes process metadata under `.local/run/`, and opens `pages/home.html`. Re-running the launcher reuses healthy services.

`stop-travelmate.cmd` stops only processes recorded by the controller and verifies their command lines before termination. Logs live under `.local/logs/` and are excluded from Git.

## Backup And Restore

The Python backup module uses SQLite's backup API for a consistent `trips.db` copy and copies the local Chroma directory. Every backup contains a JSON manifest and is stored under `backups/<timestamp>/` by default. Restore validates the manifest, creates a pre-restore safety snapshot, and then replaces the SQLite and Chroma data.

Browser-local profile fields and avatars remain in browser storage and are outside this filesystem backup because browser storage is isolated from local scripts.

## Safety And Errors

- Missing virtual environments or failed health checks produce actionable console errors and log paths.
- Real API keys remain only in ignored `backend/.env`.
- Restore requires confirmation unless `-Force` is passed.
- Generated runtime state, logs, and backups are ignored by Git.

## Verification

Vitest contract tests verify launcher wiring and safety checks. Pytest exercises backup, restore, manifest validation, and safety snapshots with temporary directories. A smoke test starts the services on test ports, checks both URLs, and stops them.
