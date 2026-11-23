"""Recherche dense dans un dossier explicite, avec références vérifiées."""
import argparse
from pathlib import Path
import sqlite3

from pydantic import ValidationError

from catalog import Catalog, CatalogError
from common import CATALOG_FILE, TEXT_BUILDER_VERSION
from config import DEFAULT_TOP_K
from embeddings import EmbeddingError, EmbeddingService, SentenceTransformerEmbedder
from scope import ScopeError, resolve_scope, validate_field_reference
from vector_store import (
    VectorFilters, VectorHit, VectorStore, VectorStoreError, open_vector_store, validate_top_k,
)


def retrieve(
    store: VectorStore, embedder: EmbeddingService, question: str, *,
    catalog: Catalog, dossier_id: str, person_id: str | None = None,
    field_name: str | None = None, top_k: int = DEFAULT_TOP_K,
    text_builder_version: str = TEXT_BUILDER_VERSION,
) -> list[VectorHit]:
    validate_top_k(top_k)
    try:
        filters = VectorFilters(dossier_id=dossier_id, person_id=person_id, field_name=field_name)
    except ValidationError as exc:
        raise VectorStoreError(f'Filtres invalides : {exc}') from exc
    scope = resolve_scope(catalog, filters.dossier_id, filters.person_id)
    if not scope.documents:
        return []
    store.check_compatibility(embedder.profile, text_builder_version)
    vector = embedder.embed_query(question)
    hits = store.search(
        vector, filters, top_k, profile=embedder.profile, text_builder_version=text_builder_version,
    )
    documents = {document.document_id: document for document in scope.documents}
    # Vérifier le lot complet avant de le remettre au futur constructeur de contexte.
    for hit in hits:
        record = hit.payload
        if (
            record.dossier_id != scope.dossier_id or record.document_id not in documents
            or (person_id is not None and record.person_id != person_id)
            or (field_name is not None and record.field_name != field_name)
        ):
            raise ScopeError('Le stockage a retourné un résultat hors du périmètre demandé.')
        document = documents[record.document_id]
        if document.dossier_id != record.dossier_id:
            raise ScopeError('Dossier du résultat incohérent avec le catalogue.')
        validate_field_reference(
            record, document, source_path=record.source_path, source_locator=record.source_locator,
        )
    return hits


def main():
    parser = argparse.ArgumentParser(description='Rechercher dans un dossier fictif')
    parser.add_argument('question', help='Question en français')
    parser.add_argument('--dossier', required=True, help='Dossier sélectionné (ex. DOS001)')
    parser.add_argument('--person', help='Identifiant de personne (ex. P001)')
    parser.add_argument('--field', help='Nom technique du champ (ex. lieu_de_deces)')
    parser.add_argument('--top-k', type=int, default=DEFAULT_TOP_K)
    parser.add_argument('--catalog', type=Path, default=CATALOG_FILE, help='Catalogue SQLite existant')
    args = parser.parse_args()
    try:
        validate_top_k(args.top_k)
        VectorFilters(dossier_id=args.dossier, person_id=args.person, field_name=args.field)
        with Catalog(args.catalog, read_only=True) as catalog:
            scope = resolve_scope(catalog, args.dossier, args.person)
            if not scope.documents:
                print('Aucun résultat dans ce dossier pour ces filtres.')
                return
            embedder = SentenceTransformerEmbedder()
            store = open_vector_store()
            try:
                hits = retrieve(
                    store, embedder, args.question, catalog=catalog, dossier_id=args.dossier,
                    person_id=args.person, field_name=args.field, top_k=args.top_k,
                )
                if not hits:
                    print('Aucun résultat dans ce dossier pour ces filtres.')
                for rank, hit in enumerate(hits, start=1):
                    p = hit.payload
                    print(f'\n{rank}. score={hit.score:.3f} | {p.dossier_id} | {p.person_id} | {p.field_name}')
                    print(f'   {p.value}')
                    print(f'   Source : {p.document_id} / champ {hit.id}')
                    print(f'   Emplacement : {p.source_path} / {p.source_locator}')
            finally:
                store.close()
    except (EmbeddingError, VectorStoreError, ScopeError, CatalogError, ValidationError, OSError, sqlite3.Error) as exc:
        parser.exit(1, f'Erreur : {exc}\n')


if __name__ == '__main__':
    main()
