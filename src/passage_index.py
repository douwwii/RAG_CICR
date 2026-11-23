"""Index incrémental de passages ; le client Qdrant est partagé par le backend."""
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field
from qdrant_client import models

from embeddings import ensure_embedding_compatible
from schemas import NonBlankText

COLLECTION = 'spoc_pdf_passages_v1'


class IndexedPassage(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    passage_id: NonBlankText
    parent_id: NonBlankText
    document_id: NonBlankText
    dossier_id: NonBlankText
    title: NonBlankText
    text: NonBlankText
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)


def passage_id(document_id: str, start: int, end: int) -> str:
    return str(uuid5(NAMESPACE_URL, f'spoc:{document_id}:{start}:{end}'))


class PassageIndex:
    def __init__(self, client, *, collection=COLLECTION):
        self.client = client
        self.collection = collection

    def ensure(self, embedder):
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(
                self.collection, vectors_config=models.VectorParams(size=embedder.dimension, distance=models.Distance.COSINE),
                metadata={'embedding_profile': embedder.profile.model_dump(), 'schema': 1},
            )
        info = self.client.get_collection(self.collection)
        metadata = info.config.metadata or {}
        if metadata.get('schema') != 1:
            raise ValueError('Schéma de passages incompatible.')
        ensure_embedding_compatible(metadata.get('embedding_profile'), embedder.profile)
        vectors = info.config.params.vectors
        if vectors.size != embedder.dimension or vectors.distance != models.Distance.COSINE:
            raise ValueError('Espace vectoriel de passages incompatible.')

    def add(self, passages, embedder):
        self.ensure(embedder)
        vectors = embedder.embed_documents([p.text for p in passages])
        points = [models.PointStruct(id=p.passage_id, vector=v.tolist(), payload=p.model_dump())
                  for p, v in zip(passages, vectors, strict=True)]
        result = self.client.upsert(self.collection, points=points, wait=True)
        if result.status != models.UpdateStatus.COMPLETED:
            raise ValueError('Indexation Qdrant inachevée.')

    def search(self, vector, embedder, dossier_id, document_ids, limit):
        if not document_ids or not self.client.collection_exists(self.collection):
            return []
        self.ensure(embedder)
        hits = self.client.query_points(
            self.collection, query=vector.tolist(), limit=limit, with_payload=True,
            query_filter=models.Filter(must=[
                models.FieldCondition(key='dossier_id', match=models.MatchValue(value=dossier_id)),
                models.FieldCondition(key='document_id', match=models.MatchAny(any=document_ids)),
            ]),
        ).points
        results = []
        for hit in hits:
            p = IndexedPassage.model_validate(hit.payload)
            if p.dossier_id != dossier_id or p.document_id not in document_ids or str(hit.id) != p.passage_id:
                raise ValueError('Résultat hors dossier ou identifiant incohérent.')
            results.append((p, hit.score))
        return results
