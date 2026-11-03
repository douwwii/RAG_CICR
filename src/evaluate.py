"""Évalue Hit@1 et Recall@5 sur une liste de requêtes annotées."""
from common import DATA_FILE, ROOT, client
from data_loader import load_evaluation_cases, load_field_records
from embeddings import EmbeddingError, SentenceTransformerEmbedder
from search import retrieve


def main():
    records = load_field_records(DATA_FILE)
    cases = load_evaluation_cases(ROOT / 'data' / 'queries.json', records)
    embedder = SentenceTransformerEmbedder()
    db = client()
    modes = [('dense seul', False), ('dense + filtre personne', True)]
    try:
        for name, filtered in modes:
            hits1 = hits5 = 0
            print(f'\n===== {name} =====')
            for case in cases:
                relevant = set(case.relevant_ids)
                results = retrieve(
                    db, embedder, case.question,
                    person_id=case.person_id if filtered else None,
                    top_k=5,
                )
                ranked = [r.id for r in results]
                correct1 = bool(ranked and ranked[0] in relevant)
                # Recall@5: fraction des champs pertinents retrouvés parmi les 5 premiers.
                recall5 = len(relevant.intersection(ranked)) / len(relevant)
                hits1 += correct1
                hits5 += recall5
                print(f"{'OK' if correct1 else 'XX'} | {case.question} | top1={ranked[0] if ranked else None} attendu={sorted(relevant)}")
            n = len(cases)
            print(f'Hit@1 : {hits1/n:.1%} | Recall@5 moyen : {hits5/n:.1%}')
    finally:
        db.close()


if __name__ == '__main__':
    try:
        main()
    except EmbeddingError as exc:
        raise SystemExit(f'Erreur : {exc}') from exc
