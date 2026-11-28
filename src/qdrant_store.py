"""Adaptateur Qdrant local : vecteurs, filtres, métadonnées et cycle de l’index."""
from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray
from pydantic import ValidationError
from qdrant_client import QdrantClient, models

from config import DEFAULT_TOP_K, VECTOR_STORE_CONFIG, VectorStoreConfig
from embeddings import EmbeddingCompatibilityError, EmbeddingProfile, ensure_embedding_compatible
from vector_store import (
    VECTOR_RECORD_SCHEMA_VERSION, VectorFilters, VectorHit, VectorRecord, VectorStoreError, validate_top_k,
)


def _make_index_metadata(profile: EmbeddingProfile, text_builder_version: str) -> dict:
    return {
        'embedding_profile': profile.model_dump(),
        'text_builder_version': text_builder_version,
        'vector_record_schema_version': VECTOR_RECORD_SCHEMA_VERSION,
    }


def _validate_definition(profile: EmbeddingProfile, text_builder_version: str) -> EmbeddingProfile:
    if not isinstance(profile, EmbeddingProfile):
        raise VectorStoreError('Un EmbeddingProfile est requis.')
    try:
        profile = EmbeddingProfile.model_validate(profile.model_dump())
    except ValidationError as exc:
        raise VectorStoreError(f'Profil invalide : {exc}') from exc
    if not isinstance(text_builder_version, str) or not text_builder_version.strip():
        raise VectorStoreError('La version de préparation des textes doit être renseignée.')
    return profile


def _validate_vectors(vectors, shape: tuple[int, ...], profile: EmbeddingProfile) -> NDArray[np.float32]:
    try:
        array = np.asarray(vectors)
    except (ValueError, TypeError) as exc:
        raise VectorStoreError('Les vecteurs doivent former un tableau numérique régulier.') from exc
    if array.shape != shape or array.dtype.kind != 'f':
        raise VectorStoreError(f'Vecteurs flottants de forme {shape} requis, reçu {array.shape}/{array.dtype}.')
    with np.errstate(over='ignore', invalid='ignore'):
        array = np.array(array, dtype=np.float32, copy=True)
    if not np.isfinite(array).all():
        raise VectorStoreError('Les vecteurs doivent être finis et représentables en float32.')
    norms = np.linalg.norm(array.astype(np.float64), axis=-1)
    if np.any(norms == 0):
        raise VectorStoreError('Les vecteurs nuls sont refusés pour la distance cosinus.')
    if profile.normalize_embeddings and not np.allclose(norms, 1., rtol=1e-4, atol=1e-5):
        raise VectorStoreError('Le profil impose des vecteurs normalisés.')
    return array


class QdrantVectorStore:
    """Stockage local ; l’instance possède et ferme son client, même injecté en test."""

    def __init__(
        self, config: VectorStoreConfig = VECTOR_STORE_CONFIG, *, client: QdrantClient | None = None,
    ):
        try:
            self._config = VectorStoreConfig.model_validate(config.model_dump())
            self._client = client if client is not None else QdrantClient(path=str(self._config.path))
        except Exception as exc:
            raise VectorStoreError(f'Impossible d’ouvrir le stockage vectoriel : {exc}') from exc

    def __enter__(self) -> 'QdrantVectorStore':
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def check_compatibility(self, profile: EmbeddingProfile, text_builder_version: str) -> None:
        profile = _validate_definition(profile, text_builder_version)
        collection = self._config.collection_name
        try:
            if not self._client.collection_exists(collection):
                raise EmbeddingCompatibilityError(
                    f'Collection absente : {collection}. Lancez python src/index.py.'
                )
            info = self._client.get_collection(collection)
            vectors = info.config.params.vectors
            if not isinstance(vectors, models.VectorParams):
                raise EmbeddingCompatibilityError('Une collection à vecteur dense unique est requise.')
            if vectors.size != profile.dimension or vectors.distance != models.Distance.COSINE:
                raise EmbeddingCompatibilityError(
                    'Dimension ou distance de la collection incompatible. Réindexation requise.'
                )
            metadata = info.config.metadata or {}
            ensure_embedding_compatible(metadata.get('embedding_profile'), profile)
            if metadata.get('text_builder_version') != text_builder_version:
                raise EmbeddingCompatibilityError(
                    'Version de préparation des textes incompatible. Réindexation requise.'
                )
            schema_version = metadata.get('vector_record_schema_version')
            if type(schema_version) is not int or schema_version != VECTOR_RECORD_SCHEMA_VERSION:
                raise EmbeddingCompatibilityError(
                    'Schéma des métadonnées incompatible : dossier et provenance requis. Réindexation requise.'
                )
        except EmbeddingCompatibilityError:
            raise
        except Exception as exc:
            raise VectorStoreError(f'Impossible de vérifier la collection {collection} : {exc}') from exc

    def rebuild(
        self, records: Sequence[VectorRecord], vectors: NDArray[np.float32], *,
        profile: EmbeddingProfile, text_builder_version: str,
    ) -> None:
        profile = _validate_definition(profile, text_builder_version)
        if isinstance(records, (str, bytes)) or not isinstance(records, Sequence) or not records:
            raise VectorStoreError('Une séquence non vide de VectorRecord est requise.')
        try:
            records = [VectorRecord.model_validate(record.model_dump()) for record in records]
        except (AttributeError, ValidationError) as exc:
            raise VectorStoreError(f'Métadonnées invalides : {exc}') from exc
        if len({record.id for record in records}) != len(records):
            raise VectorStoreError('Les identifiants des entrées doivent être uniques.')
        vectors = _validate_vectors(vectors, (len(records), profile.dimension), profile)
        # Toute la validation et la construction des points précèdent la suppression.
        points = [models.PointStruct(id=record.id, vector=vector.tolist(), payload=record.model_dump())
                  for record, vector in zip(records, vectors, strict=True)]
        collection = self._config.collection_name
        try:
            if self._client.collection_exists(collection):
                self.check_compatibility(profile, text_builder_version)
                if not self._client.delete_collection(collection):
                    raise VectorStoreError('La suppression de la collection a échoué.')
            if not self._client.create_collection(
                collection_name=collection,
                vectors_config=models.VectorParams(size=profile.dimension, distance=models.Distance.COSINE),
            ):
                raise VectorStoreError('La création de la collection a échoué.')
            result = self._client.upsert(collection_name=collection, points=points, wait=True)
            if result.status != models.UpdateStatus.COMPLETED:
                raise VectorStoreError('Insertion non terminée ; le profil ne sera pas publié.')
            if self._client.count(collection_name=collection, exact=True).count != len(records):
                raise VectorStoreError('Index incomplet ; le profil ne sera pas publié.')
            # Un échec avant cette publication laisse l’index inutilisable par search().
            if not self._client.update_collection(
                collection_name=collection,
                metadata=_make_index_metadata(profile, text_builder_version),
            ):
                raise VectorStoreError('La publication du profil a échoué.')
        except (EmbeddingCompatibilityError, VectorStoreError):
            raise
        except Exception as exc:
            raise VectorStoreError(f'Échec de reconstruction de {collection} : {exc}') from exc

    def search(
        self, vector: NDArray[np.float32], filters: VectorFilters,
        top_k: int = DEFAULT_TOP_K, *, profile: EmbeddingProfile, text_builder_version: str,
    ) -> list[VectorHit]:
        profile = _validate_definition(profile, text_builder_version)
        validate_top_k(top_k)
        try:
            filters = VectorFilters.model_validate(filters.model_dump())
        except (AttributeError, ValidationError) as exc:
            raise VectorStoreError(f'Filtres invalides : {exc}') from exc
        vector = _validate_vectors(vector, (profile.dimension,), profile)
        # search() reste protégé quand il est appelé sans passer par retrieve().
        self.check_compatibility(profile, text_builder_version)
        conditions = [models.FieldCondition(key=key, match=models.MatchValue(value=value))
                      for key, value in filters.model_dump(exclude={'document_ids'}).items() if value is not None]
        if filters.document_ids is not None:
            if not filters.document_ids:
                return []
            conditions.append(models.FieldCondition(key='document_id', match=models.MatchAny(any=filters.document_ids)))
        try:
            hits = self._client.query_points(
                collection_name=self._config.collection_name, query=vector.tolist(),
                query_filter=models.Filter(must=conditions) if conditions else None,
                limit=top_k, with_payload=True, with_vectors=False,
            ).points
            results = [VectorHit(id=hit.id, score=hit.score, payload=VectorRecord.model_validate(hit.payload))
                       for hit in hits]
            for hit in results:
                if (any(getattr(hit.payload, key) != value for key, value in filters.model_dump(exclude={'document_ids'}).items()
                        if value is not None) or
                        (filters.document_ids is not None and hit.payload.document_id not in filters.document_ids)):
                    raise VectorStoreError('Résultat hors du périmètre demandé.')
            return results
        except Exception as exc:
            raise VectorStoreError(f'Échec de recherche ou résultat invalide : {exc}') from exc
