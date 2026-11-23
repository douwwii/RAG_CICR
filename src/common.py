from config import EMBEDDING_CONFIG, ROOT, VECTOR_STORE_CONFIG
from data_loader import load_field_records

DATA_FILE = ROOT / 'data' / 'documents.json'
# Alias conservés ; les paramètres sont définis uniquement dans config.py.
DB_DIR = VECTOR_STORE_CONFIG.path
MODEL_NAME = EMBEDDING_CONFIG.model_name
COLLECTION = VECTOR_STORE_CONFIG.collection_name
TEXT_BUILDER_VERSION = 'field_label_value_v1'
CATALOG_FILE = ROOT / 'catalogue.sqlite'
CATALOG_SEED_FILE = ROOT / 'data' / 'catalog_seed.json'
SCOPED_QUERIES_FILE = ROOT / 'data' / 'scoped_queries.json'


def load_documents():
    # Conserver les dictionnaires attendus par le prototype après validation.
    return [record.model_dump() for record in load_field_records(DATA_FILE)]


def make_text(doc):
    # Conserver la relation label-valeur dans l'embedding.
    return f"Type de champ : {doc['field_label']}. Information : {doc['value']}"
