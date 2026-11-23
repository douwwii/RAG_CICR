"""Contrats de stockage des champs actuels, sans dépendance à Qdrant."""
from collections.abc import Sequence
from typing import Protocol

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field, model_validator

from config import DEFAULT_TOP_K, VECTOR_STORE_CONFIG, VectorStoreConfig
from embeddings import EmbeddingProfile
from schemas import FieldRecord, NonBlankText, RecordId

VECTOR_RECORD_SCHEMA_VERSION = 2


class VectorStoreError(ValueError):
    """Entrée, opération ou résultat de stockage invalide."""


class VectorRecord(FieldRecord):
    """Métadonnées d’un champ, avec le texte exact fourni à l’encodeur."""

    embedding_text: NonBlankText
    dossier_id: NonBlankText
    source_path: NonBlankText
    source_locator: NonBlankText


class VectorFilters(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)

    dossier_id: NonBlankText
    person_id: NonBlankText | None = None
    field_name: NonBlankText | None = None


class VectorHit(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)

    id: RecordId
    score: float = Field(allow_inf_nan=False)
    payload: VectorRecord

    @model_validator(mode='after')
    def consistent_id(self) -> 'VectorHit':
        if self.id != self.payload.id:
            raise ValueError('identifiant du résultat différent de celui des métadonnées')
        return self


def validate_top_k(top_k: int) -> None:
    if type(top_k) is not int or top_k < 1:
        raise VectorStoreError('top_k doit être un entier strictement positif.')


class VectorStore(Protocol):
    """Un seul espace vectoriel dense par instance, avec distance cosinus."""

    def check_compatibility(self, profile: EmbeddingProfile, text_builder_version: str) -> None: ...

    def rebuild(
        self, records: Sequence[VectorRecord], vectors: NDArray[np.float32], *,
        profile: EmbeddingProfile, text_builder_version: str,
    ) -> None: ...

    def search(
        self, vector: NDArray[np.float32], filters: VectorFilters,
        top_k: int = DEFAULT_TOP_K, *, profile: EmbeddingProfile, text_builder_version: str,
    ) -> list[VectorHit]: ...

    def close(self) -> None: ...


def open_vector_store(config: VectorStoreConfig = VECTOR_STORE_CONFIG) -> VectorStore:
    # L’import reste dans la fabrique : le retrieval peut utiliser un faux stockage
    # sans installer ou importer Qdrant, ni charger un modèle d’embedding.
    from qdrant_store import QdrantVectorStore

    return QdrantVectorStore(config)
