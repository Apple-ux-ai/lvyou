"""Backend configuration loaded from environment variables or backend/.env."""
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    deepseek_api_key: SecretStr | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    travelmate_llm_provider: Literal["auto", "local"] = "auto"
    travelmate_vector_backend: Literal["auto", "chroma", "json"] = "auto"
    travelmate_embedding_provider: Literal["auto", "hash", "sentence_transformers"] = "auto"
    travelmate_embedding_model: str = "BAAI/bge-small-zh-v1.5"
    travelmate_embedding_version: str = "bge-small-zh-v1.5"
    travelmate_embedding_device: str = "cpu"
    travelmate_embedding_batch_size: int = Field(default=32, ge=1, le=256)
    travelmate_embedding_dimension: int = Field(default=1024, ge=8, le=8192)
    travelmate_embedding_lora_path: str = ""  # 可选：LoRA 适配器路径
    # Hash embeddings are an explicit offline mode; production must fail fast
    # when the configured semantic model is unavailable.
    travelmate_embedding_allow_fallback: bool = False
    travelmate_index_root: str = ""
    travelmate_index_version: str = ""
    travelmate_index_backup_root: str = "backups/indexes"
    travelmate_retrieval_min_score: float = Field(default=0.4, ge=0.0, le=1.0)
    travelmate_retrieval_top_k: int = Field(default=3, ge=1, le=50)
    travelmate_retrieval_dense_weight: float = Field(default=0.55, ge=0.0, le=1.0)
    travelmate_retrieval_lexical_weight: float = Field(default=0.45, ge=0.0, le=1.0)
    travelmate_cors_origins: str = "http://127.0.0.1:5501,http://localhost:5501"
    travelmate_max_sessions: int = Field(default=1000, ge=1, le=100_000)
    # Optional in-memory protection for a public single-instance demo.
    travelmate_rate_limit_enabled: bool = False
    travelmate_rate_limit_per_window: int = Field(default=5, ge=1, le=10_000)
    travelmate_rate_limit_window_seconds: int = Field(default=600, ge=1, le=86_400)
    travelmate_global_chat_limit: int = Field(default=100, ge=1, le=1_000_000)
    travelmate_global_chat_window_seconds: int = Field(default=86_400, ge=1, le=604_800)
    travelmate_max_concurrent_chats: int = Field(default=2, ge=1, le=1_000)


def load_settings() -> Settings:
    return Settings()
