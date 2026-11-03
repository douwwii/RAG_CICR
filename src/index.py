"""Indexation unique des documents fictifs vers Qdrant local."""
from qdrant_client import models
from common import COLLECTION, TEXT_BUILDER_VERSION, client, load_documents, make_text
from embeddings import EmbeddingError, SentenceTransformerEmbedder
from index_metadata import ensure_collection_compatible, make_index_metadata


def main():
    docs = load_documents()
    embedder = SentenceTransformerEmbedder()
    texts = [make_text(d) for d in docs]
    vectors = embedder.embed_documents(texts)
    points = [
        models.PointStruct(
            id=d['id'], vector=v.tolist(),
            payload={**d, 'embedding_text': text},
        )
        for d, v, text in zip(docs, vectors, texts)
    ]
    db = client()
    try:
        # Recrée l'index à chaque exécution : rend le test reproductible.
        if db.collection_exists(COLLECTION):
            # Ne jamais remplacer silencieusement un index d’un autre profil.
            ensure_collection_compatible(db, COLLECTION, embedder.profile, TEXT_BUILDER_VERSION)
            db.delete_collection(COLLECTION)
        db.create_collection(
            collection_name=COLLECTION,
            vectors_config=models.VectorParams(
                size=embedder.dimension,
                distance=models.Distance.COSINE,
            ),
        )
        db.upsert(collection_name=COLLECTION, points=points, wait=True)
        # Publier le profil uniquement après une insertion réussie. Sans profil,
        # un index incomplet sera refusé par la recherche.
        db.update_collection(
            collection_name=COLLECTION,
            metadata=make_index_metadata(embedder.profile, TEXT_BUILDER_VERSION),
        )
        print(f"Indexation terminée : {len(points)} champs dans {COLLECTION}")
        print(f"Dimension des vecteurs : {vectors.shape[1]}")
        print(f"Profil d’embedding : {embedder.profile.fingerprint[:12]}")
    finally:
        db.close()


if __name__ == '__main__':
    try:
        main()
    except EmbeddingError as exc:
        raise SystemExit(f'Erreur : {exc}') from exc
