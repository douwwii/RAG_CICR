"""Configuration locale ; aucun modèle ni stockage n’est ouvert à l’import."""
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from schemas import NonBlankText

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TOP_K = 5


class VectorStoreConfig(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)

    backend: Literal['qdrant'] = 'qdrant'
    path: Path = ROOT / 'qdrant_data'
    collection_name: NonBlankText = 'cicr_synthetic_minilm_v3'


class EmbeddingConfig(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)

    model_name: NonBlankText = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
    revision: str = Field(
        default='e8f8c211226b894fcb81acc59f3b34ba3efd5f42',
        pattern=r'^[0-9a-f]{40}$',
    )
    normalize_embeddings: bool = True
    batch_size: int = Field(default=32, ge=1)
    device: NonBlankText | None = None
    local_files_only: bool = True
    # None hérite des instructions du modèle ; "" les désactive explicitement.
    query_prompt: str | None = None
    document_prompt: str | None = None


class OllamaConfig(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)

    base_url: str = Field(default='http://127.0.0.1:11435', pattern=r'^https?://[^\s]+$')
    model_name: NonBlankText = 'qwen3.8:27b-mlx'
    timeout_seconds: float = Field(default=90.0, gt=0, allow_inf_nan=False)
    temperature: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    num_predict: int = Field(default=4096, ge=1)
    think: bool | None = False
    output_format: Literal['schema', 'json'] = 'schema'


EMBEDDING_CONFIG = EmbeddingConfig()
VECTOR_STORE_CONFIG = VectorStoreConfig()
