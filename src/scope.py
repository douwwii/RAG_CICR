"""Périmètre et références du corpus JSON, sans modèle ni stockage vectoriel."""
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from catalog import Catalog
from schemas import DocumentMetadata, FieldRecord, NonBlankText


class ScopeError(ValueError):
    """Périmètre ou provenance incohérents ; aucun élargissement automatique."""


class SearchScope(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)

    dossier_id: NonBlankText
    person_id: NonBlankText | None = None
    documents: tuple[DocumentMetadata, ...] = ()


def resolve_scope(catalog: Catalog, dossier_id: str, person_id: str | None = None) -> SearchScope:
    try:
        scope = SearchScope(dossier_id=dossier_id, person_id=person_id)
    except ValidationError as exc:
        raise ScopeError(f'Périmètre invalide : {exc}') from exc
    # Le catalogue refuse un dossier inconnu et retourne [] pour une personne
    # absente du périmètre. Le nom de la personne n’intervient jamais ici.
    documents = catalog.list_documents(scope.dossier_id, scope.person_id)
    return scope.model_copy(update={'documents': tuple(documents)})


def validate_field_reference(
    record: FieldRecord, document: DocumentMetadata, *, source_path: Path | str, source_locator: str,
) -> None:
    """Vérifie la référence à un champ préextrait ; aucun PDF ni page n’est déduit."""
    if (
        record.document_id != document.document_id
        or record.person_id not in document.person_ids
        or record.source_kind != document.source_kind
        or source_locator != f'id={record.id}'
        or source_locator != document.source_locator
        or Path(source_path).resolve() != Path(document.source_path).resolve()
    ):
        raise ScopeError(f'Provenance incohérente pour le champ {record.id} / {record.document_id}.')
