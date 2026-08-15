"""Embedding providers used by indexing and retrieval.

The sentence-transformers provider is the quality path.  The deterministic hash
provider keeps local development and tests usable when the model package or model
files are not installed yet.
"""
from __future__ import annotations

import hashlib
import logging
import math
import re
from typing import Protocol, Sequence

from app.core.config import Settings, load_settings

logger = logging.getLogger(__name__)


class EmbeddingUnavailableError(RuntimeError):
    """Raised when a configured embedding provider cannot be loaded."""


class EmbeddingCompatibilityError(RuntimeError):
    """Raised when stored vectors do not match the active provider."""


class EmbeddingProvider(Protocol):
    model_id: str
    version: str
    dimension: int

    def __call__(self, texts: Sequence[str]) -> list[list[float]]:
        """Encode a batch of texts."""

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Encode document texts as a batch."""

    def embed_query(self, text: str) -> list[float]:
        """Encode one query text."""


_TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]+|[a-zA-Z0-9]+")
_CJK_PATTERN = re.compile(r"[\u4e00-\u9fff]+")


class HashEmbedding:
    """Deterministic lexical fallback with signed feature hashing.

    This is intentionally named as a fallback, not a semantic model.  Compared
    with the old implementation it keeps word boundaries, includes unigram
    features, uses a larger vector, and uses signed hashing to reduce collision
    bias.  The lexical retriever remains the source of truth for exact entities.
    """

    model_id = "hash-ngram-v2"

    def __init__(self, dimension: int = 1024, version: str = "hash-ngram-v2"):
        self.dimension = dimension
        self.version = version

    def __call__(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._encode(str(text)) for text in texts]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self(texts)

    def embed_query(self, text: str) -> list[float]:
        return self([text])[0]

    def _encode(self, text: str) -> list[float]:
        features = self._features(text)
        vector = [0.0] * self.dimension
        for feature, count in features.items():
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=16).digest()
            index = int.from_bytes(digest[:8], "big") % self.dimension
            sign = 1.0 if digest[8] & 1 else -1.0
            weight = 1.0 + math.log1p(count)
            vector[index] += sign * weight

        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    @staticmethod
    def _features(text: str) -> dict[str, int]:
        normalized = text.casefold()
        features: dict[str, int] = {}
        for token in _TOKEN_PATTERN.findall(normalized):
            if _CJK_PATTERN.fullmatch(token):
                grams = [token[index : index + size] for size in (1, 2, 3) for index in range(len(token) - size + 1)]
            else:
                grams = [f"word:{token}"]
                grams.extend(f"word:{token[index : index + size]}" for size in (2, 3) for index in range(len(token) - size + 1))
            for gram in grams:
                features[gram] = features.get(gram, 0) + 1
        if not features:
            features["<empty>"] = 1
        return features


class SentenceTransformerEmbedding:
    """Lazy sentence-transformers adapter with normalized output vectors."""

    def __init__(
        self,
        model_name: str,
        device: str = "cpu",
        batch_size: int = 32,
        version: str | None = None,
    ):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise EmbeddingUnavailableError(
                "sentence-transformers is not installed; install backend requirements to use the semantic model"
            ) from exc

        try:
            self._model = SentenceTransformer(model_name, device=device)
        except Exception as exc:
            raise EmbeddingUnavailableError(f"embedding model could not be loaded: {model_name}") from exc

        self.model_id = model_name
        self.version = version or model_name
        self.dimension = int(self._model.get_sentence_embedding_dimension())
        self.batch_size = batch_size

    def __call__(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._model.encode(
            list(texts),
            batch_size=self.batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return vectors.tolist()

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self(texts)

    def embed_query(self, text: str) -> list[float]:
        return self([text])[0]


def build_embedding_fn(settings: Settings | None = None) -> EmbeddingProvider:
    """Build the configured provider, falling back safely in auto mode."""
    configured = settings or load_settings()
    if configured.travelmate_embedding_provider == "hash":
        return HashEmbedding(configured.travelmate_embedding_dimension, "hash-ngram-v2")

    if configured.travelmate_embedding_provider == "sentence_transformers":
        return SentenceTransformerEmbedding(
            configured.travelmate_embedding_model,
            configured.travelmate_embedding_device,
            configured.travelmate_embedding_batch_size,
            configured.travelmate_embedding_version,
        )

    try:
        return SentenceTransformerEmbedding(
            configured.travelmate_embedding_model,
            configured.travelmate_embedding_device,
            configured.travelmate_embedding_batch_size,
            configured.travelmate_embedding_version,
        )
    except EmbeddingUnavailableError as exc:
        if not configured.travelmate_embedding_allow_fallback:
            raise
        logger.warning("Semantic embedding unavailable; using deterministic fallback: %s", exc)
        return HashEmbedding(configured.travelmate_embedding_dimension, "hash-ngram-v2")


def embedding_manifest(provider: EmbeddingProvider) -> dict[str, str | int | bool]:
    return {
        "provider": provider.__class__.__name__,
        "model_id": provider.model_id,
        "version": provider.version,
        "dimension": provider.dimension,
        "normalized": True,
    }
