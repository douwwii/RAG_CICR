"""Recherche dense avec filtres exacts facultatifs."""
import argparse
from qdrant_client import models
from common import COLLECTION, TEXT_BUILDER_VERSION, client
from embeddings import EmbeddingError, EmbeddingService, SentenceTransformerEmbedder
from index_metadata import ensure_collection_compatible


def retrieve(db, embedder: EmbeddingService, question, person_id=None, field_name=None, top_k=5):
    ensure_collection_compatible(db, COLLECTION, embedder.profile, TEXT_BUILDER_VERSION)
    conditions = []
    if person_id:
        conditions.append(models.FieldCondition(
            key='person_id', match=models.MatchValue(value=person_id)))
    if field_name:
        conditions.append(models.FieldCondition(
            key='field_name', match=models.MatchValue(value=field_name)))
    query_filter = models.Filter(must=conditions) if conditions else None
    vector = embedder.embed_query(question)
    return db.query_points(
        collection_name=COLLECTION,
        query=vector.tolist(),
        query_filter=query_filter,
        limit=top_k,
        with_payload=True,
    ).points


def main():
    parser = argparse.ArgumentParser(description='Rechercher dans les formulaires fictifs')
    parser.add_argument('question', help='Question en français')
    parser.add_argument('--person', help='Identifiant de personne (ex. P001)')
    parser.add_argument('--field', help='Nom technique du champ (ex. lieu_de_deces)')
    parser.add_argument('--top-k', type=int, default=5)
    args = parser.parse_args()
    try:
        embedder = SentenceTransformerEmbedder()
    except EmbeddingError as exc:
        parser.exit(1, f'Erreur : {exc}\n')
    db = client()
    try:
        hits = retrieve(db, embedder, args.question, args.person, args.field, args.top_k)
        if not hits:
            print('Aucun résultat pour ces filtres.')
        for rank, hit in enumerate(hits, start=1):
            p = hit.payload
            print(f"\n{rank}. score={hit.score:.3f} | {p['person_id']} | {p['field_name']}")
            print(f"   {p['value']}")
            print(f"   Source : {p['document_id']} / champ {hit.id}")
    except EmbeddingError as exc:
        parser.exit(1, f'Erreur : {exc}\n')
    finally:
        db.close()


if __name__ == '__main__':
    main()
