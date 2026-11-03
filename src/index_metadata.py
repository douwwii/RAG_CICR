"""Raccord minimal des profils à Qdrant ; aucun calcul d’embedding ici."""
from qdrant_client import models

from embeddings import EmbeddingCompatibilityError, EmbeddingProfile, ensure_embedding_compatible


def make_index_metadata(profile: EmbeddingProfile, text_builder_version: str) -> dict:
    return {
        'embedding_profile': profile.model_dump(),
        'text_builder_version': text_builder_version,
    }


def ensure_collection_compatible(
    db, collection_name: str, profile: EmbeddingProfile, text_builder_version: str,
) -> None:
    if not db.collection_exists(collection_name):
        raise EmbeddingCompatibilityError(
            f'Collection absente : {collection_name}. Lancez python src/index.py.'
        )
    info = db.get_collection(collection_name)
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
