"""Persistent metadata for knowledge and embedding index consistency."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

MANIFEST_VERSION = 1


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def manifest_path(persist_dir: str | Path, collection: str) -> Path:
    return Path(persist_dir) / f"{collection}.manifest.json"


def load_manifest(persist_dir: str | Path, collection: str) -> dict[str, Any]:
    path = manifest_path(persist_dir, collection)
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def save_manifest(persist_dir: str | Path, collection: str, value: dict[str, Any]) -> Path:
    path = manifest_path(persist_dir, collection)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"manifest_version": MANIFEST_VERSION, **value}
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
    return path


def inspect_manifest(
    persist_dir: str | Path,
    collection: str,
    *,
    embedding: dict[str, Any],
    chunking_version: str,
    source_ids: set[str],
    chunk_count: int,
) -> dict[str, Any]:
    """Compare persisted metadata with the live index without hiding drift."""
    path = manifest_path(persist_dir, collection)
    manifest = load_manifest(persist_dir, collection)
    if not manifest:
        return {
            "path": str(path),
            "present": False,
            "compatible": False,
            "status": "missing",
        }

    manifest_sources = manifest.get("sources")
    stored_source_ids = set(manifest_sources) if isinstance(manifest_sources, dict) else set()
    stored_chunk_count = sum(
        int(value.get("chunk_count", 0))
        for value in manifest_sources.values()
        if isinstance(value, dict)
    ) if isinstance(manifest_sources, dict) else -1
    embedding_match = manifest.get("embedding") == embedding
    chunking_match = manifest.get("chunking_version") == chunking_version
    sources_match = stored_source_ids == source_ids
    chunks_match = stored_chunk_count == chunk_count
    compatible = embedding_match and chunking_match and sources_match and chunks_match
    return {
        "path": str(path),
        "present": True,
        "compatible": compatible,
        "status": "ok" if compatible else "mismatch",
        "embedding_match": embedding_match,
        "chunking_match": chunking_match,
        "sources_match": sources_match,
        "chunks_match": chunks_match,
        "manifest_source_count": len(stored_source_ids),
        "manifest_chunk_count": stored_chunk_count,
    }
