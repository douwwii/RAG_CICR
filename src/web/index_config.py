"""Profil de l’index web ; la bascule est un remplacement atomique du manifeste."""
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field

from config import EmbeddingConfig, VectorStoreConfig
from common import TEXT_BUILDER_VERSION
from passage_index import COLLECTION

BGE_CONFIG = EmbeddingConfig(
    model_name='BAAI/bge-m3', revision='5617a9f61b028005a4858fdac845db406aefb181',
    batch_size=4, device='cpu',
)
CONTEXT_VERSION = 'person_field_label_value_v1'


class WebIndexConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    schema_version: int = Field(default=1, ge=1, le=1)
    embedding: EmbeddingConfig = EmbeddingConfig()
    fields: VectorStoreConfig = VectorStoreConfig()
    passage_collection: str = COLLECTION
    text_builder_version: str = TEXT_BUILDER_VERSION
    artifact_path: Path
    coherent: bool = False

    @classmethod
    def load(cls, data_path):
        manifest = data_path / 'active_index.json'
        if manifest.exists():
            return cls.model_validate_json(manifest.read_text(encoding='utf-8'))
        return cls(artifact_path=data_path)


def create_embedder(config):
    # Même réglage CPU que le benchmark, sans charger plusieurs modèles simultanément.
    if config.device == 'cpu':
        import torch
        torch.set_num_threads(4)
    from embeddings import SentenceTransformerEmbedder
    return SentenceTransformerEmbedder(config)
