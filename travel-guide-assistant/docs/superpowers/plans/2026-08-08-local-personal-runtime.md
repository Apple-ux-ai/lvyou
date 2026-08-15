# TravelMate Personal Local Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide safe double-click local startup, shutdown, health checks, and local data backup/restore for one user.

**Architecture:** Thin CMD launchers call focused PowerShell controllers. A tested Python module owns SQLite/Chroma backup and restore semantics. Runtime files are kept outside version control.

**Tech Stack:** Windows CMD, PowerShell 5+, Python 3.11, sqlite3, pytest, Vitest

---

### Task 1: Runtime Script Contracts

**Files:**
- Create: `frontend/tests/local-runtime-contract.test.js`
- Create: `start-travelmate.cmd`
- Create: `stop-travelmate.cmd`
- Create: `scripts/local/Start-TravelMate.ps1`
- Create: `scripts/local/Stop-TravelMate.ps1`

- [x] Write Vitest assertions for launchers, health URLs, hidden processes, browser opening, PID metadata, and guarded shutdown.
- [x] Run `npm test -- --run frontend/tests/local-runtime-contract.test.js` and confirm RED because scripts do not exist.
- [x] Implement the launchers and PowerShell controllers with ports as parameters.
- [x] Re-run the focused test and confirm GREEN.

### Task 2: Backup And Restore Core

**Files:**
- Create: `backend/tests/unit/test_local_data.py`
- Create: `backend/scripts/local_data.py`

- [x] Write pytest cases that back up SQLite and Chroma, restore both, reject a missing manifest, and create a pre-restore snapshot.
- [x] Run `python -m pytest backend/tests/unit/test_local_data.py -q` and confirm RED because the module does not exist.
- [x] Implement `create_backup()` and `restore_backup()` using `sqlite3.Connection.backup`, JSON manifests, and explicit paths.
- [x] Re-run the focused test and confirm GREEN.

### Task 3: Backup Command Wrappers

**Files:**
- Create: `backup-travelmate.cmd`
- Create: `restore-latest-travelmate.cmd`
- Create: `scripts/local/Backup-TravelMate.ps1`
- Create: `scripts/local/Restore-TravelMate.ps1`
- Modify: `frontend/tests/local-runtime-contract.test.js`

- [x] Extend the contract test for backup and restore wrappers, latest-backup selection, and restore confirmation.
- [x] Run the focused test and confirm RED.
- [x] Implement wrappers that invoke `backend/scripts/local_data.py` with project-relative paths.
- [x] Re-run the focused test and confirm GREEN.

### Task 4: Documentation And Ignore Rules

**Files:**
- Modify: `.gitignore`
- Modify: `FINAL_PLAN.md`
- Modify: `ROADMAP.md`
- Create: `LOCAL_USE.md`

- [x] Ignore `.local/` and `backups/`.
- [x] Document double-click start/stop, logs, backup/restore, DeepSeek configuration, and browser-storage limitations.
- [x] Mark accounts, Docker, PostgreSQL, Qdrant, and server deployment as deferred.

### Task 5: Verification

- [ ] Run `python -m pytest -q` from `backend/`.
- [ ] Run `npm test -- --run`.
- [ ] Run `npm run test:e2e`.
- [ ] Start on test ports with `-NoBrowser`, verify both health URLs, and stop the recorded processes.
- [ ] Run `git diff --check` and confirm `backend/.env`, `.local/`, and `backups/` are ignored.
