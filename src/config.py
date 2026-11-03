"""Paramètres d’embedding ; aucun modèle n’est chargé à l’import."""
from pydantic import BaseModel, ConfigDict, Field

from schemas import NonBlankText


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


EMBEDDING_CONFIG = EmbeddingConfig()
