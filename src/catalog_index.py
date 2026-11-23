"""Raccord des champs JSON au catalogue, avant tout calcul d’embedding."""
from collections.abc import Sequence
from pathlib import Path

from catalog import Catalog
from common import make_text
from data_loader import validate_corpus
from schemas import FieldRecord
from scope import ScopeError, validate_field_reference
from vector_store import VectorRecord


def prepare_index_records(
    records: Sequence[FieldRecord], catalog: Catalog, source_path: Path,
) -> list[VectorRecord]:
    validate_corpus(records)
    source_path = Path(source_path).resolve()
    indexed = []
    for record in records:
        document = catalog.lookup_document(record.document_id)
        if document is None:
            raise ScopeError(f'Document absent du catalogue : {record.document_id}.')
        locator = f'id={record.id}'
        validate_field_reference(record, document, source_path=source_path, source_locator=locator)
        indexed.append(VectorRecord(
            **record.model_dump(), dossier_id=document.dossier_id,
            source_path=str(source_path), source_locator=locator,
            embedding_text=make_text(record.model_dump()),
        ))
    return indexed
