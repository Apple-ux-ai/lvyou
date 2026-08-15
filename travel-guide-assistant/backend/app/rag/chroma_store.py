"""Vector storage and hybrid retrieval for the local knowledge base."""
from __future__ import annotations

import json
import logging
import math
import os
import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from app.core.config import load_settings
from app.rag.chunking import CHUNKING_VERSION, ParsedChunk, split_document
from app.rag.embedding_cache import EmbeddingCache, embedding_cache_key
from app.rag.embeddings import (
    EmbeddingCompatibilityError,
    EmbeddingProvider,
    build_embedding_fn,
    embedding_manifest,
)
from app.rag.lexical_retriever import BM25Index
from app.rag.index_manifest import inspect_manifest
from app.rag.retriever import Document

logger = logging.getLogger(__name__)


def _should_use_chroma() -> bool:
    configured = load_settings().travelmate_vector_backend
    backend = os.getenv("TRAVELMATE_VECTOR_BACKEND", configured).lower()
    if backend == "chroma":
        return True
    if backend == "json":
        return False
    return os.name != "nt"


USE_CHROMA = _should_use_chroma()
if USE_CHROMA:
    import chromadb
    from chromadb.config import Settings


def _collection_vector_dimensions(collection: Any) -> list[int]:
    try:
        result = collection.get(limit=1, include=["embeddings"])
        embeddings = result.get("embeddings") or []
        return [len(embeddings[0])] if embeddings else []
    except Exception:
        return []


@dataclass
class ChunkMeta:
    source_id: str
    version: int
    index: int
    text: str
    title: str = ""
    section: str = ""
    source_path: str = ""


@dataclass
class IngestResult:
    source_id: str
    version: int
    chunk_count: int
    embedding_model: str


class _JsonVectorStore:
    """Persistent fallback with an in-memory read cache and atomic writes."""

    def __init__(self, persist_dir: str, collection: str):
        self._path = Path(persist_dir) / f"{collection}.json"
        self._records: list[dict[str, Any]] | None = None
        self._mtime_ns: int | None = None

    def replace_source(
        self,
        source_id: str,
        version: int,
        documents: list[str],
        embeddings: list[list[float]],
        metadata: list[dict[str, Any]] | None = None,
    ) -> None:
        records = [record for record in self.all_records() if record.get("source_id") != source_id]
        metadata = metadata or [{} for _ in documents]
        records.extend(
            {
                "id": f"{source_id}::{version}::{index}",
                "source_id": source_id,
                "version": version,
                "index": index,
                "text": text,
                "embedding": embedding,
                **metadata[index],
            }
            for index, (text, embedding) in enumerate(zip(documents, embeddings))
        )
        self.replace_all(records)

    def replace_all(self, records: Iterable[dict[str, Any]]) -> None:
        self._write({"records": list(records)})

    def delete_source(self, source_id: str) -> None:
        self.replace_all(record for record in self.all_records() if record.get("source_id") != source_id)

    def clear(self) -> None:
        self.replace_all([])

    def source_records(self, source_id: str) -> list[dict[str, Any]]:
        return [record for record in self.all_records() if record.get("source_id") == source_id]

    def all_records(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            self._records = []
            self._mtime_ns = None
            return []

        mtime_ns = self._path.stat().st_mtime_ns
        if self._records is not None and self._mtime_ns == mtime_ns:
            return self._records

        try:
            value = json.loads(self._path.read_text(encoding="utf-8"))
            records = value.get("records", []) if isinstance(value, dict) else []
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Unable to read vector fallback %s: %s", self._path, exc)
            records = []
        self._records = records if isinstance(records, list) else []
        self._mtime_ns = mtime_ns
        return self._records

    def count(self) -> int:
        return len(self.all_records())

    def search(self, query_embedding: list[float], limit: int) -> list[dict[str, Any]]:
        records = self.all_records()
        if not records:
            return []

        dimensions = len(query_embedding)
        stored_dimensions = {len(record.get("embedding", [])) for record in records}
        if stored_dimensions != {dimensions}:
            raise EmbeddingCompatibilityError(
                f"stored dimensions {sorted(stored_dimensions)} do not match active dimension "
                f"{dimensions}; rebuild the index"
            )
        compatible = records

        try:
            import numpy as np

            matrix = np.asarray([record["embedding"] for record in compatible], dtype="float32")
            scores = matrix @ np.asarray(query_embedding, dtype="float32")
            order = np.argsort(-scores)[:limit]
            return [
                {**compatible[int(index)], "dense_score": max(0.0, float(scores[int(index)]))}
                for index in order
            ]
        except ImportError:
            scored = []
            for record in compatible:
                score = sum(a * b for a, b in zip(query_embedding, record["embedding"]))
                scored.append({**record, "dense_score": max(0.0, score)})
            scored.sort(key=lambda record: record["dense_score"], reverse=True)
            return scored[:limit]

    def _write(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(self._path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary.replace(self._path)
        self._records = data["records"]
        self._mtime_ns = self._path.stat().st_mtime_ns


class ChromaIndexer:
    def __init__(
        self,
        persist_dir: str = "./chroma_data",
        collection: str = "knowledge",
        embedding_fn: EmbeddingProvider | None = None,
        embedding_cache: EmbeddingCache | None = None,
    ):
        self.persist_dir = persist_dir
        self.collection_name = collection
        self._fallback_store = _JsonVectorStore(persist_dir, collection) if not USE_CHROMA else None
        self._embed = embedding_fn or build_embedding_fn()
        self._embedding_cache = embedding_cache or EmbeddingCache(
            Path(persist_dir) / f"{collection}.embedding-cache.sqlite3"
        )
        self._cache_hits = 0
        self._cache_misses = 0
        if self._fallback_store is not None:
            return

        self._client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=collection,
            metadata={
                "hnsw:space": "cosine",
                "embedding_model": self._embed.model_id,
                "embedding_dimension": self._embed.dimension,
                "chunking_version": CHUNKING_VERSION,
            },
        )

    @property
    def embedding_model(self) -> str:
        return self._embed.model_id

    @property
    def embedding_dimension(self) -> int:
        return self._embed.dimension

    @property
    def embedding_provider(self) -> EmbeddingProvider:
        return self._embed

    @property
    def storage_backend(self) -> str:
        return "json" if self._fallback_store is not None else "chroma"

    def ingest(
        self,
        source_id: str,
        content: str,
        version: int = 1,
        *,
        chunks: list[ParsedChunk] | None = None,
        source_path: str = "",
        content_hash: str = "",
    ) -> IngestResult:
        """Ingest one source, replacing every previous version atomically per source.

        Direct callers without ``chunks`` keep the historical line behavior for
        compatibility.  The ingestion script supplies section-aware chunks.
        """
        if chunks is None:
            legacy_lines = [line.strip() for line in content.splitlines() if line.strip()]
            if not legacy_lines and content.strip():
                legacy_lines = [content.strip()]
            chunks = [
                ParsedChunk(text=line, index=index, title=source_id, section="")
                for index, line in enumerate(legacy_lines)
            ]
        if not chunks:
            self.delete_source(source_id)
            return IngestResult(source_id, version, 0, self.embedding_model)

        documents = [chunk.text for chunk in chunks]
        source_content_hash = content_hash or hashlib.sha256(content.encode("utf-8")).hexdigest()
        embeddings = self._embed_documents(documents, source_content_hash)
        if len(embeddings) != len(documents):
            raise EmbeddingCompatibilityError("embedding provider returned an unexpected batch size")
        metadata = [
            {
                "title": chunk.title,
                "section": chunk.section,
                "source_path": source_path,
                "content_hash": content_hash,
            }
            for chunk in chunks
        ]
        ids = [f"{source_id}::{version}::{index}" for index in range(len(documents))]

        if self._fallback_store is not None:
            self._fallback_store.replace_source(source_id, version, documents, embeddings, metadata)
        else:
            self._delete_source(source_id)
            self._collection.add(
                ids=ids,
                documents=documents,
                metadatas=[
                    {
                        "source_id": source_id,
                        "version": version,
                        "index": index,
                        **metadata[index],
                    }
                    for index in range(len(documents))
                ],
                embeddings=embeddings,
            )
        return IngestResult(source_id, version, len(documents), self.embedding_model)

    def _embed_documents(self, documents: list[str], source_content_hash: str) -> list[list[float]]:
        keys = [
            embedding_cache_key(source_content_hash, index, text, self._embed)
            for index, text in enumerate(documents)
        ]
        cached = self._embedding_cache.get_many(keys)
        vectors: list[list[float] | None] = [cached.get(key) for key in keys]
        missing_indexes = [index for index, vector in enumerate(vectors) if vector is None]
        self._cache_hits += len(documents) - len(missing_indexes)
        self._cache_misses += len(missing_indexes)
        if missing_indexes:
            missing_texts = [documents[index] for index in missing_indexes]
            embed_documents = getattr(self._embed, "embed_documents", None)
            generated = (
                embed_documents(missing_texts)
                if callable(embed_documents)
                else self._embed(missing_texts)
            )
            if len(generated) != len(missing_indexes):
                raise EmbeddingCompatibilityError(
                    "embedding provider returned an unexpected batch size"
                )
            to_cache = {}
            for index, vector in zip(missing_indexes, generated):
                vectors[index] = vector
                to_cache[keys[index]] = vector
            self._embedding_cache.put_many(to_cache)
        return [vector for vector in vectors if vector is not None]

    def delete_source(self, source_id: str) -> None:
        if self._fallback_store is not None:
            self._fallback_store.delete_source(source_id)
            return
        self._delete_source(source_id)

    def _delete_source(self, source_id: str) -> None:
        if self._fallback_store is not None:
            self._fallback_store.delete_source(source_id)
            return
        existing = self._collection.get(where={"source_id": source_id}, include=["metadatas"])
        if existing and existing.get("ids"):
            self._collection.delete(ids=existing["ids"])

    def reset(self) -> None:
        if self._fallback_store is not None:
            self._fallback_store.clear()
            return
        existing = self._collection.get(include=["metadatas"])
        if existing and existing.get("ids"):
            self._collection.delete(ids=existing["ids"])

    def count_chunks(self, source_id: str) -> int:
        if self._fallback_store is not None:
            return len(self._fallback_store.source_records(source_id))
        result = self._collection.get(where={"source_id": source_id}, include=["metadatas"])
        return len(result.get("ids", []))

    def get_chunks(self, source_id: str) -> list[ChunkMeta]:
        records = self._records_for_source(source_id)
        return [
            ChunkMeta(
                source_id=record.get("source_id", source_id),
                version=int(record.get("version", 1)),
                index=int(record.get("index", index)),
                text=record.get("text", ""),
                title=record.get("title", ""),
                section=record.get("section", ""),
                source_path=record.get("source_path", ""),
            )
            for index, record in enumerate(sorted(records, key=lambda item: int(item.get("index", 0))))
        ]

    def exists(self, source_id: str) -> bool:
        return self.count_chunks(source_id) > 0

    def all_records(self) -> list[dict[str, Any]]:
        if self._fallback_store is not None:
            return list(self._fallback_store.all_records())
        result = self._collection.get(include=["documents", "metadatas"])
        return _records_from_chroma(result)

    def source_ids(self) -> set[str]:
        return {str(record.get("source_id")) for record in self.all_records() if record.get("source_id")}

    def count(self) -> int:
        if self._fallback_store is not None:
            return self._fallback_store.count()
        return self._collection.count()

    def _records_for_source(self, source_id: str) -> list[dict[str, Any]]:
        if self._fallback_store is not None:
            return self._fallback_store.source_records(source_id)
        result = self._collection.get(where={"source_id": source_id}, include=["documents", "metadatas"])
        return _records_from_chroma(result)

    def health(self) -> dict[str, Any]:
        records = self.all_records()
        dimensions = (
            sorted({len(record.get("embedding", [])) for record in records if record.get("embedding")})
            if self._fallback_store is not None
            else _collection_vector_dimensions(self._collection)
        )
        dimensions_compatible = not dimensions or dimensions == [self.embedding_dimension]
        manifest = inspect_manifest(
            self.persist_dir,
            self.collection_name,
            embedding=embedding_manifest(self._embed),
            chunking_version=CHUNKING_VERSION,
            source_ids={str(record.get("source_id")) for record in records if record.get("source_id")},
            chunk_count=len(records),
        )
        return {
            "backend": self.storage_backend,
            "collection": self.collection_name,
            "persist_dir": self.persist_dir,
            "chunk_count": len(records),
            "source_count": len({record.get("source_id") for record in records if record.get("source_id")}),
            "embedding_model": self.embedding_model,
            "embedding_dimension": self.embedding_dimension,
            "stored_dimensions": dimensions,
            "embedding_compatible": dimensions_compatible,
            "manifest": manifest,
            "embedding_cache": {
                "path": str(self._embedding_cache.path),
                "entries": self._embedding_cache.count(),
                "hits": self._cache_hits,
                "misses": self._cache_misses,
            },
        }


class ChromaRetriever:
    def __init__(
        self,
        persist_dir: str = "./chroma_data",
        collection: str = "knowledge",
        min_score: float | None = None,
        embedding_fn: EmbeddingProvider | None = None,
    ):
        configured = load_settings()
        self.min_score = configured.travelmate_retrieval_min_score if min_score is None else min_score
        self.dense_weight = configured.travelmate_retrieval_dense_weight
        self.lexical_weight = configured.travelmate_retrieval_lexical_weight
        weight_total = self.dense_weight + self.lexical_weight
        if weight_total <= 0:
            self.dense_weight, self.lexical_weight = 0.55, 0.45
        else:
            self.dense_weight /= weight_total
            self.lexical_weight /= weight_total
        self._fallback_store = _JsonVectorStore(persist_dir, collection) if not USE_CHROMA else None
        self._embed = embedding_fn or build_embedding_fn()
        self.persist_dir = persist_dir
        self._embedding_cache = EmbeddingCache(
            Path(persist_dir) / f"{collection}.embedding-cache.sqlite3"
        )
        self.last_search_metrics: dict[str, Any] = {}
        self.collection_name = collection
        if self._fallback_store is None:
            self._client = chromadb.PersistentClient(
                path=persist_dir,
                settings=Settings(anonymized_telemetry=False),
            )
            self._collection = self._client.get_or_create_collection(
                name=collection,
                metadata={"hnsw:space": "cosine"},
            )
        self._lexical = BM25Index(self._all_records())

    @property
    def embedding_model(self) -> str:
        return self._embed.model_id

    @property
    def embedding_dimension(self) -> int:
        return self._embed.dimension

    def search(self, query: str, top_k: int = 5) -> list[Document]:
        """Return source-diverse hybrid results ordered by combined relevance."""
        started = time.perf_counter()
        embedding_ms = 0.0
        dense_ms = 0.0
        lexical_ms = 0.0
        if not query.strip() or top_k <= 0:
            self.last_search_metrics = self._search_metrics(
                started, embedding_ms, dense_ms, lexical_ms, []
            )
            return []
        candidate_limit = max(top_k * 4, 20)
        records = self._all_records()
        if not records:
            self.last_search_metrics = self._search_metrics(
                started, embedding_ms, dense_ms, lexical_ms, []
            )
            return []
        self._lexical.replace(records)

        dense_records: list[dict[str, Any]] = []
        embedding_started = time.perf_counter()
        try:
            embed_query = getattr(self._embed, "embed_query", None)
            query_embedding = (
                embed_query(query)
                if callable(embed_query)
                else self._embed([query])[0]
            )
            embedding_ms = (time.perf_counter() - embedding_started) * 1000
            dense_started = time.perf_counter()
            if self._fallback_store is not None:
                dense_records = self._fallback_store.search(query_embedding, candidate_limit)
            else:
                dense_records = self._dense_chroma_search(query_embedding, candidate_limit)
            dense_ms = (time.perf_counter() - dense_started) * 1000
        except EmbeddingCompatibilityError as exc:
            embedding_ms = (time.perf_counter() - embedding_started) * 1000
            logger.warning("Dense index is incompatible with active embedding: %s", exc)
        except Exception as exc:
            embedding_ms = (time.perf_counter() - embedding_started) * 1000
            logger.warning("Dense retrieval unavailable; using lexical retrieval: %s", exc)

        lexical_started = time.perf_counter()
        lexical_records = self._lexical.search(query, candidate_limit)
        lexical_ms = (time.perf_counter() - lexical_started) * 1000
        dense_by_id = {record.get("id"): record for record in dense_records}
        lexical_by_id = {record.get("id"): record for record in lexical_records}
        combined: list[dict[str, Any]] = []
        for record_id in set(dense_by_id) | set(lexical_by_id):
            dense = dense_by_id.get(record_id)
            lexical = lexical_by_id.get(record_id)
            base = dense or lexical
            dense_score = float(dense.get("dense_score", 0.0)) if dense else 0.0
            lexical_score = float(lexical.get("lexical_score", 0.0)) if lexical else 0.0
            lexical_normalized = (
                1.0 - math.exp(-lexical_score / 4.0) if lexical_score else 0.0
            )
            if dense and lexical:
                score = self.dense_weight * dense_score + self.lexical_weight * lexical_normalized
            elif lexical:
                score = self.lexical_weight * lexical_normalized
            else:
                score = self.dense_weight * dense_score
            combined.append({**base, "score": score})

        combined.sort(key=lambda record: (-record["score"], str(record.get("id", ""))))
        documents: list[Document] = []
        seen_sources: set[str] = set()
        for record in combined:
            if record["score"] < self.min_score:
                continue
            source_id = str(record.get("source_id", "unknown"))
            if source_id in seen_sources:
                continue
            seen_sources.add(source_id)
            documents.append(
                Document(
                    source_id=source_id,
                    text=str(record.get("text", "")),
                    score=float(record["score"]),
                    metadata={
                        "title": record.get("title", ""),
                        "section": record.get("section", ""),
                        "index": record.get("index", 0),
                    },
                )
            )
            if len(documents) >= top_k:
                break
        self.last_search_metrics = self._search_metrics(
            started,
            embedding_ms,
            dense_ms,
            lexical_ms,
            documents,
        )
        return documents

    def _search_metrics(
        self,
        started: float,
        embedding_ms: float,
        dense_ms: float,
        lexical_ms: float,
        documents: list[Document],
    ) -> dict[str, Any]:
        return {
            "embedding_ms": round(embedding_ms, 3),
            "dense_ms": round(dense_ms, 3),
            "lexical_ms": round(lexical_ms, 3),
            "retrieval_ms": round((time.perf_counter() - started) * 1000 - embedding_ms, 3),
            "source_ids": [document.source_id for document in documents],
            "top_score": round(documents[0].score, 6) if documents else 0.0,
            "embedding_model": self.embedding_model,
        }

    def exists(self, source_id: str) -> bool:
        if self._fallback_store is not None:
            return bool(self._fallback_store.source_records(source_id))
        try:
            result = self._collection.get(where={"source_id": source_id}, include=["metadatas"])
            return bool(result.get("ids"))
        except Exception:
            return False

    def count(self) -> int:
        if self._fallback_store is not None:
            return self._fallback_store.count()
        return self._collection.count()

    def _all_records(self) -> list[dict[str, Any]]:
        if self._fallback_store is not None:
            return self._fallback_store.all_records()
        return _records_from_chroma(self._collection.get(include=["documents", "metadatas"]))

    def health(self) -> dict[str, Any]:
        records = self._all_records()
        stored_dimensions: list[int] = []
        if self._fallback_store is not None:
            stored_dimensions = sorted({len(record.get("embedding", [])) for record in records if record.get("embedding")})
        else:
            stored_dimensions = _collection_vector_dimensions(self._collection)
            if not stored_dimensions:
                metadata = getattr(self._collection, "metadata", {}) or {}
                configured_dimension = metadata.get("embedding_dimension")
                if configured_dimension is not None:
                    stored_dimensions = [int(configured_dimension)]
        dimensions_compatible = not stored_dimensions or stored_dimensions == [self.embedding_dimension]
        manifest = inspect_manifest(
            self.persist_dir,
            self.collection_name,
            embedding=embedding_manifest(self._embed),
            chunking_version=CHUNKING_VERSION,
            source_ids={str(record.get("source_id")) for record in records if record.get("source_id")},
            chunk_count=len(records),
        )
        return {
            "backend": "json" if self._fallback_store is not None else "chroma",
            "collection": self.collection_name,
            "persist_dir": self.persist_dir,
            "chunk_count": len(records),
            "source_count": len({record.get("source_id") for record in records if record.get("source_id")}),
            "embedding_model": self.embedding_model,
            "embedding_dimension": self.embedding_dimension,
            "stored_dimensions": stored_dimensions,
            "embedding_compatible": dimensions_compatible,
            "manifest": manifest,
            "embedding_cache": {
                "path": str(self._embedding_cache.path),
                "entries": self._embedding_cache.count(),
            },
        }

    def _dense_chroma_search(self, query_embedding: list[float], limit: int) -> list[dict[str, Any]]:
        count = self._collection.count()
        if count == 0:
            return []
        result = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=min(limit, count),
            include=["documents", "metadatas", "distances"],
        )
        distances = (result.get("distances") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        ids = (result.get("ids") or [[]])[0]
        records = []
        for index, distance in enumerate(distances):
            metadata = metadatas[index] if index < len(metadatas) else {}
            records.append(
                {
                    "id": ids[index] if index < len(ids) else f"result-{index}",
                    "source_id": metadata.get("source_id", "unknown"),
                    "version": metadata.get("version", 1),
                    "index": metadata.get("index", index),
                    "text": documents[index] if index < len(documents) else "",
                    "title": metadata.get("title", ""),
                    "section": metadata.get("section", ""),
                    "dense_score": max(0.0, 1.0 - float(distance)),
                }
            )
        return records


def _records_from_chroma(result: dict[str, Any]) -> list[dict[str, Any]]:
    ids = result.get("ids") or []
    documents = result.get("documents") or []
    metadatas = result.get("metadatas") or []
    records = []
    for index, record_id in enumerate(ids):
        metadata = metadatas[index] if index < len(metadatas) else {}
        records.append(
            {
                "id": record_id,
                "source_id": metadata.get("source_id", "unknown"),
                "version": metadata.get("version", 1),
                "index": metadata.get("index", index),
                "text": documents[index] if index < len(documents) else "",
                "title": metadata.get("title", ""),
                "section": metadata.get("section", ""),
                "source_path": metadata.get("source_path", ""),
            }
        )
    return records
