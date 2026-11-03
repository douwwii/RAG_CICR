from pathlib import Path

from config import EMBEDDING_CONFIG
from data_loader import load_field_records

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / 'data' / 'documents.json'
DB_DIR = ROOT / 'qdrant_data'
# Alias conservé pour les utilisateurs du prototype ; la configuration est dans config.py.
MODEL_NAME = EMBEDDING_CONFIG.model_name
COLLECTION = 'cicr_synthetic_minilm_v2'
TEXT_BUILDER_VERSION = 'field_label_value_v1'
CATALOG_FILE = ROOT / 'catalogue.sqlite'
CATALOG_SEED_FILE = ROOT / 'data' / 'catalog_seed.json'


def load_documents():
    # Conserver les dictionnaires attendus par le prototype après validation.
    return [record.model_dump() for record in load_field_records(DATA_FILE)]


def make_text(doc):
    # Conserver la relation label-valeur dans l'embedding.
    return f"Type de champ : {doc['field_label']}. Information : {doc['value']}"


def client():
    from qdrant_client import QdrantClient

    return QdrantClient(path=str(DB_DIR))
