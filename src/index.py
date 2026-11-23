"""Indexation des champs fictifs via les interfaces d’embedding et de stockage."""
import sqlite3

from catalog import Catalog, CatalogError
from catalog_index import prepare_index_records
from common import CATALOG_FILE, DATA_FILE, TEXT_BUILDER_VERSION
from config import VECTOR_STORE_CONFIG
from data_loader import DataValidationError, load_field_records
from embeddings import EmbeddingError, SentenceTransformerEmbedder
from scope import ScopeError
from vector_store import VectorStoreError, open_vector_store


def main():
    docs = load_field_records(DATA_FILE)
    with Catalog(CATALOG_FILE, read_only=True) as catalog:
        records = prepare_index_records(docs, catalog, DATA_FILE)
    embedder = SentenceTransformerEmbedder()
    vectors = embedder.embed_documents([record.embedding_text for record in records])
    store = open_vector_store()
    try:
        store.rebuild(
            records, vectors, profile=embedder.profile, text_builder_version=TEXT_BUILDER_VERSION,
        )
        print(f"Indexation terminée : {len(records)} champs dans {VECTOR_STORE_CONFIG.collection_name}")
        print(f"Dimension des vecteurs : {vectors.shape[1]}")
        print(f"Profil d’embedding : {embedder.profile.fingerprint[:12]}")
    finally:
        store.close()


if __name__ == '__main__':
    try:
        main()
    except (EmbeddingError, VectorStoreError, ScopeError, CatalogError, DataValidationError, OSError, sqlite3.Error) as exc:
        raise SystemExit(f'Erreur : {exc}') from exc
