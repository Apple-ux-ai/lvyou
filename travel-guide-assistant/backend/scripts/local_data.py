"""Backup and restore TravelMate's local SQLite and Chroma data."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


class BackupError(RuntimeError):
    pass


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _copy_database(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_connection = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    destination_connection = sqlite3.connect(destination)
    try:
        source_connection.backup(destination_connection)
    finally:
        destination_connection.close()
        source_connection.close()


def _dotenv_value(root: Path, key: str) -> str | None:
    """Read one non-secret setting without loading or printing credentials."""
    env_path = root / "backend" / ".env"
    if not env_path.is_file():
        return None
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        if name.strip() == key:
            return value.strip().strip('"').strip("'")
    return None


def _versioned_index(root: Path) -> tuple[Path, str] | None:
    """Resolve a versioned index root that is safe to include in a backup."""
    configured = os.getenv("TRAVELMATE_INDEX_ROOT") or _dotenv_value(root, "TRAVELMATE_INDEX_ROOT")
    backend_root = (root / "backend").resolve()
    if configured:
        index_root = Path(configured)
        if not index_root.is_absolute():
            index_root = backend_root / index_root
    else:
        index_root = backend_root / "index_versions"
    index_root = index_root.resolve()
    try:
        relative = index_root.relative_to(backend_root).as_posix()
    except ValueError as exc:
        raise BackupError("TRAVELMATE_INDEX_ROOT must be inside the project backend directory") from exc
    if not index_root.is_dir():
        return None
    return index_root, relative


def _active_version(index_root: Path) -> str | None:
    pointer = index_root / "active.json"
    if not pointer.is_file():
        return None
    try:
        value = json.loads(pointer.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    active = value.get("active_version") if isinstance(value, dict) else None
    return active if isinstance(active, str) else None


def _index_manifest_summary(index_root: Path, relative_root: str) -> dict:
    active = _active_version(index_root)
    versions_root = index_root / "versions"
    versions = sorted(path.name for path in versions_root.iterdir() if path.is_dir()) if versions_root.is_dir() else []
    summary = {
        "versioned_root": relative_root,
        "active_version": active,
        "version_count": len(versions),
    }
    if active:
        manifest_path = versions_root / active / "knowledge.manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = {}
        if isinstance(manifest, dict):
            summary["active_manifest_path"] = f"{relative_root}/versions/{active}/knowledge.manifest.json"
            summary["embedding"] = manifest.get("embedding", {})
            summary["chunking_version"] = manifest.get("chunking_version")
            sources = manifest.get("sources", {})
            summary["source_count"] = len(sources) if isinstance(sources, dict) else 0
    return summary


def create_backup(
    project_root: str | Path,
    destination: str | Path | None = None,
    *,
    timestamp: str | None = None,
) -> Path:
    root = Path(project_root).resolve()
    created_at = timestamp or _timestamp()
    backup_path = Path(destination).resolve() if destination else root / "backups" / created_at
    if backup_path.exists() and any(backup_path.iterdir()):
        raise BackupError(f"Backup destination is not empty: {backup_path}")
    backup_path.mkdir(parents=True, exist_ok=True)

    database_path = root / "backend" / "data" / "trips.db"
    chroma_path = root / "backend" / "chroma_data"
    versioned_index = _versioned_index(root)
    contains_database = database_path.is_file()
    contains_chroma = chroma_path.is_dir()
    contains_versioned_index = versioned_index is not None

    if contains_database:
        _copy_database(database_path, backup_path / "trips.db")
    if contains_chroma:
        shutil.copytree(chroma_path, backup_path / "chroma_data")
    if versioned_index is not None:
        shutil.copytree(versioned_index[0], backup_path / "index_versions")

    index_metadata = {}
    index_manifest_path = chroma_path / "knowledge.manifest.json"
    if index_manifest_path.is_file():
        try:
            index_manifest = json.loads(index_manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            index_manifest = {}
        if isinstance(index_manifest, dict):
            index_metadata = {
                "manifest_path": "chroma_data/knowledge.manifest.json",
                "embedding": index_manifest.get("embedding", {}),
                "chunking_version": index_manifest.get("chunking_version"),
                "source_count": len(index_manifest.get("sources", {}))
                if isinstance(index_manifest.get("sources"), dict)
                else 0,
            }
    if versioned_index is not None:
        index_metadata["versioned_index"] = _index_manifest_summary(*versioned_index)

    contains = {
        "trips_db": contains_database,
        "chroma_data": contains_chroma,
    }
    if contains_versioned_index:
        contains["index_versions"] = True
    manifest = {
        "version": 1,
        "created_at": created_at,
        "contains": contains,
        "index": index_metadata,
    }
    (backup_path / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return backup_path


def _load_manifest(backup_path: Path) -> dict:
    manifest_path = backup_path / "manifest.json"
    if not manifest_path.is_file():
        raise BackupError(f"Backup manifest not found: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        raise BackupError(f"Backup manifest is invalid: {manifest_path}") from exc
    if not isinstance(manifest, dict) or manifest.get("version") != 1 or not isinstance(manifest.get("contains"), dict):
        raise BackupError(f"Backup manifest has an unsupported format: {manifest_path}")
    if manifest["contains"].get("trips_db") and not (backup_path / "trips.db").is_file():
        raise BackupError("Backup manifest references a missing trips.db")
    if manifest["contains"].get("chroma_data") and not (backup_path / "chroma_data").is_dir():
        raise BackupError("Backup manifest references missing Chroma data")
    if manifest["contains"].get("index_versions") and not (backup_path / "index_versions").is_dir():
        raise BackupError("Backup manifest references missing versioned index data")
    return manifest


def _restore_index_target(root: Path, manifest: dict) -> Path:
    versioned = (manifest.get("index") or {}).get("versioned_index") or {}
    relative = versioned.get("versioned_root", "index_versions")
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise BackupError("Backup contains an invalid versioned index root")
    backend_root = (root / "backend").resolve()
    target = (backend_root / relative).resolve()
    try:
        target.relative_to(backend_root)
    except ValueError as exc:
        raise BackupError("Backup versioned index root escapes the backend directory") from exc
    return target


def verify_backup(backup_path: str | Path) -> dict:
    """Validate a backup without changing project data."""
    source = Path(backup_path).resolve()
    return _verify_backup(source, _load_manifest(source))


def _verify_backup(source: Path, manifest: dict) -> dict:
    result: dict = {
        "path": str(source),
        "created_at": manifest.get("created_at"),
        "contains": manifest.get("contains", {}),
    }

    if manifest["contains"].get("trips_db"):
        try:
            database = sqlite3.connect(f"{(source / 'trips.db').as_uri()}?mode=ro", uri=True)
            try:
                integrity = database.execute("PRAGMA integrity_check").fetchone()[0]
            finally:
                database.close()
        except sqlite3.Error as exc:
            raise BackupError(f"SQLite integrity check failed: {exc}") from exc
        if integrity != "ok":
            raise BackupError(f"SQLite integrity check failed: {integrity}")
        result["trips_db"] = {"integrity": integrity}

    if manifest["contains"].get("chroma_data"):
        index_manifest_path = source / "chroma_data" / "knowledge.manifest.json"
        legacy = {"manifest_present": index_manifest_path.is_file()}
        if index_manifest_path.is_file():
            try:
                index_manifest = json.loads(index_manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise BackupError(f"Legacy index manifest is invalid: {index_manifest_path}") from exc
            if not isinstance(index_manifest, dict):
                raise BackupError(f"Legacy index manifest must be an object: {index_manifest_path}")
            sources = index_manifest.get("sources", {})
            legacy.update(
                {
                    "source_count": len(sources) if isinstance(sources, dict) else 0,
                    "chunking_version": index_manifest.get("chunking_version"),
                    "embedding": index_manifest.get("embedding", {}),
                }
            )
        result["legacy_index"] = legacy

    if manifest["contains"].get("index_versions"):
        versioned_root = source / "index_versions"
        active = _active_version(versioned_root)
        if active:
            active_manifest = versioned_root / "versions" / active / "knowledge.manifest.json"
            if not active_manifest.is_file():
                raise BackupError(f"Active version references a missing manifest: {active}")
            try:
                metadata = json.loads(active_manifest.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise BackupError(f"Active version manifest is invalid: {active_manifest}") from exc
            if not isinstance(metadata, dict):
                raise BackupError(f"Active version manifest must be an object: {active_manifest}")
        versioned = _index_manifest_summary(versioned_root, "index_versions")
        expected = ((manifest.get("index") or {}).get("versioned_index") or {}).get("active_version")
        if expected != active:
            raise BackupError(
                f"Backup active version mismatch: manifest={expected!r}, pointer={active!r}"
            )
        result["versioned_index"] = versioned

    return result


def restore_backup(
    project_root: str | Path,
    backup_path: str | Path,
    *,
    timestamp: str | None = None,
) -> Path:
    root = Path(project_root).resolve()
    source = Path(backup_path).resolve()
    manifest = _load_manifest(source)
    _verify_backup(source, manifest)
    target_index = _restore_index_target(root, manifest) if manifest["contains"].get("index_versions") else None
    restored_at = timestamp or _timestamp()
    safety_path = root / ".local" / "pre-restore" / restored_at
    create_backup(root, safety_path, timestamp=restored_at)

    backend_root = root / "backend"
    if manifest["contains"].get("trips_db"):
        _copy_database(source / "trips.db", backend_root / "data" / "trips.db")

    if manifest["contains"].get("chroma_data"):
        current_chroma = backend_root / "chroma_data"
        temporary_chroma = backend_root / f".chroma-restore-{uuid4().hex}"
        shutil.copytree(source / "chroma_data", temporary_chroma)
        if current_chroma.exists():
            shutil.rmtree(current_chroma)
        temporary_chroma.replace(current_chroma)

    if target_index is not None:
        temporary_index = backend_root / f".index-restore-{uuid4().hex}"
        shutil.copytree(source / "index_versions", temporary_index)
        if target_index.exists():
            shutil.rmtree(target_index)
        target_index.parent.mkdir(parents=True, exist_ok=True)
        temporary_index.replace(target_index)

    return safety_path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    backup_parser = subparsers.add_parser("backup")
    backup_parser.add_argument("--destination", type=Path)
    restore_parser = subparsers.add_parser("restore")
    restore_parser.add_argument("--backup-path", type=Path, required=True)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if args.command == "backup":
        result = create_backup(args.project_root, args.destination)
        print(result)
        return 0
    safety_path = restore_backup(args.project_root, args.backup_path)
    print(f"Restored {args.backup_path}")
    print(f"Pre-restore safety backup: {safety_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
