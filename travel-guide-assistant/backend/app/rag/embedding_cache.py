"""Persistent document-embedding cache keyed by source content and provider version."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Iterable, Mapping, Protocol, Sequence


class CacheProvider(Protocol):
    model_id: str
    version: str
    dimension: int


def embedding_cache_key(
    source_content_hash: str,
    chunk_index: int,
    text: str,
    provider: CacheProvider,
) -> str:
    """Include both source content and the exact provider contract in the key."""
    payload = {
        "content_hash": source_content_hash,
        "chunk_index": chunk_index,
        "text_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "model_id": provider.model_id,
        "version": provider.version,
        "dimension": provider.dimension,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


class EmbeddingCache:
    """Small SQLite cache with atomic batch writes and no third-party dependency."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS embeddings (
                    cache_key TEXT PRIMARY KEY,
                    dimension INTEGER NOT NULL,
                    vector_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def get_many(self, keys: Sequence[str]) -> dict[str, list[float]]:
        if not keys:
            return {}
        result: dict[str, list[float]] = {}
        for offset in range(0, len(keys), 500):
            batch = keys[offset : offset + 500]
            placeholders = ",".join("?" for _ in batch)
            with self._connect() as connection:
                rows = connection.execute(
                    f"SELECT cache_key, dimension, vector_json FROM embeddings "
                    f"WHERE cache_key IN ({placeholders})",
                    list(batch),
                ).fetchall()
            for key, dimension, vector_json in rows:
                try:
                    vector = json.loads(vector_json)
                except (TypeError, json.JSONDecodeError):
                    continue
                if isinstance(vector, list) and len(vector) == int(dimension):
                    result[str(key)] = [float(value) for value in vector]
        return result

    def put_many(self, vectors: Mapping[str, Sequence[float]]) -> None:
        if not vectors:
            return
        rows = [
            (
                key,
                len(vector),
                json.dumps(list(vector), ensure_ascii=False, separators=(",", ":")),
            )
            for key, vector in vectors.items()
        ]
        with self._connect() as connection:
            connection.executemany(
                "INSERT OR REPLACE INTO embeddings "
                "(cache_key, dimension, vector_json) VALUES (?, ?, ?)",
                rows,
            )

    def count(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) FROM embeddings").fetchone()
        return int(row[0]) if row else 0
