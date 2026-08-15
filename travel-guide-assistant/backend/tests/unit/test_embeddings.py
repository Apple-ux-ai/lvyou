import math

import pytest

from app.core.config import Settings
from app.rag.embedding_cache import EmbeddingCache, embedding_cache_key
from app.rag.embeddings import (
    EmbeddingUnavailableError,
    HashEmbedding,
    build_embedding_fn,
    embedding_manifest,
)


def test_hash_embedding_is_deterministic_normalized_and_batched():
    provider = HashEmbedding(dimension=64)
    vectors = provider.embed_documents(["京都伏见稻荷", "京都伏见稻荷"])

    assert vectors[0] == vectors[1]
    assert len(vectors[0]) == 64
    assert math.isclose(math.sqrt(sum(value * value for value in vectors[0])), 1.0, rel_tol=1e-6)
    assert provider.embed_query("京都") == provider(["京都"])[0]


def test_hash_provider_manifest_contains_active_version_and_dimension():
    provider = HashEmbedding(dimension=32)
    manifest = embedding_manifest(provider)

    assert manifest["model_id"] == "hash-ngram-v2"
    assert manifest["version"] == "hash-ngram-v2"
    assert manifest["dimension"] == 32
    assert manifest["normalized"] is True


def test_explicit_hash_embedding_provider_uses_configured_dimension():
    settings = Settings(
        _env_file=None,
        travelmate_embedding_provider="hash",
        travelmate_embedding_dimension=48,
    )

    provider = build_embedding_fn(settings)

    assert isinstance(provider, HashEmbedding)
    assert provider.dimension == 48


def test_auto_embedding_falls_back_only_when_enabled(monkeypatch):
    import app.rag.embeddings as embeddings

    def unavailable(*args, **kwargs):
        raise EmbeddingUnavailableError("model unavailable")

    monkeypatch.setattr(embeddings, "SentenceTransformerEmbedding", unavailable)
    settings = Settings(
        _env_file=None,
        travelmate_embedding_provider="auto",
        travelmate_embedding_allow_fallback=True,
        travelmate_embedding_dimension=48,
    )

    provider = build_embedding_fn(settings)

    assert isinstance(provider, HashEmbedding)
    assert provider.dimension == 48


def test_embedding_fallback_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("TRAVELMATE_EMBEDDING_PROVIDER", raising=False)
    monkeypatch.delenv("TRAVELMATE_EMBEDDING_ALLOW_FALLBACK", raising=False)
    settings = Settings(_env_file=None)

    assert settings.travelmate_embedding_provider == "auto"
    assert settings.travelmate_embedding_allow_fallback is False


def test_embedding_cache_key_changes_with_source_or_provider_version(tmp_path):
    provider = HashEmbedding(dimension=32, version="hash-v1")
    same = embedding_cache_key("source-a", 0, "京都交通", provider)
    changed_source = embedding_cache_key("source-b", 0, "京都交通", provider)
    changed_provider = embedding_cache_key(
        "source-a", 0, "京都交通", HashEmbedding(dimension=32, version="hash-v2")
    )

    assert same != changed_source
    assert same != changed_provider


def test_embedding_cache_round_trip_preserves_vectors(tmp_path):
    cache = EmbeddingCache(tmp_path / "embeddings.sqlite3")
    cache.put_many({"key": [0.25, 0.75]})

    assert cache.get_many(["key", "missing"]) == {"key": [0.25, 0.75]}
    assert cache.count() == 1


def test_auto_embedding_can_fail_fast_when_fallback_is_disabled(monkeypatch):
    import app.rag.embeddings as embeddings

    def unavailable(*args, **kwargs):
        raise EmbeddingUnavailableError("model unavailable")

    monkeypatch.setattr(embeddings, "SentenceTransformerEmbedding", unavailable)
    settings = Settings(
        _env_file=None,
        travelmate_embedding_provider="auto",
        travelmate_embedding_allow_fallback=False,
    )

    with pytest.raises(EmbeddingUnavailableError, match="model unavailable"):
        build_embedding_fn(settings)
