"""Évalue le retrieval dans les dossiers explicitement annotés."""
import sqlite3

from catalog import Catalog, CatalogError
from catalog_index import prepare_index_records
from common import CATALOG_FILE, DATA_FILE, SCOPED_QUERIES_FILE
from data_loader import DataValidationError, load_field_records, load_scoped_evaluation_cases
from embeddings import EmbeddingError, SentenceTransformerEmbedder
from scope import ScopeError
from search import retrieve
from vector_store import VectorStoreError, open_vector_store


def main():
    records = load_field_records(DATA_FILE)
    with Catalog(CATALOG_FILE, read_only=True) as catalog:
        # Vérifier les sources et annotations avant de charger le modèle.
        prepare_index_records(records, catalog, DATA_FILE)
        cases = load_scoped_evaluation_cases(SCOPED_QUERIES_FILE, records, catalog)
        embedder = SentenceTransformerEmbedder()
        store = open_vector_store()
        modes = [('dossier seul', False), ('dossier + filtre personne', True)]
        try:
            for name, filtered in modes:
                hits1 = hits5 = 0
                print(f'\n===== {name} =====')
                for case in cases:
                    relevant = set(case.relevant_ids)
                    results = retrieve(
                        store, embedder, case.question, catalog=catalog, dossier_id=case.dossier_id,
                        person_id=case.person_id if filtered else None, top_k=5,
                    )
                    ranked = [result.id for result in results]
                    correct1 = bool(ranked and ranked[0] in relevant)
                    hits1 += correct1
                    hits5 += len(relevant.intersection(ranked)) / len(relevant)
                    print(f"{'OK' if correct1 else 'XX'} | {case.dossier_id} | {case.question} | top1={ranked[0] if ranked else None} attendu={sorted(relevant)}")
                n = len(cases)
                print(f'Hit@1 : {hits1/n:.1%} | Recall@5 moyen : {hits5/n:.1%}')
        finally:
            store.close()


if __name__ == '__main__':
    try:
        main()
    except (EmbeddingError, VectorStoreError, ScopeError, CatalogError, DataValidationError, OSError, sqlite3.Error) as exc:
        raise SystemExit(f'Erreur : {exc}') from exc
