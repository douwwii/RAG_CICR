"""Contrats du corpus actuel, indépendants du modèle et du stockage vectoriel."""
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field


def _not_blank(value: str) -> str:
    # Vérifier avec strip(), mais conserver exactement le texte source.
    if not value.strip():
        raise ValueError('le texte ne doit pas être vide ou uniquement composé d’espaces')
    return value


NonBlankText = Annotated[str, AfterValidator(_not_blank)]
# Le format existant utilise des identifiants entiers non signés sur 64 bits.
RecordId = Annotated[int, Field(ge=0, le=2**64 - 1)]


class FieldRecord(BaseModel):
    """Un champ préextrait ; il ne représente pas un document complet."""

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)

    id: RecordId
    document_id: NonBlankText
    person_id: NonBlankText
    field_name: NonBlankText
    field_label: NonBlankText
    value: NonBlankText
    source_kind: NonBlankText


class EvaluationCase(BaseModel):
    """Une question annotée au format déjà utilisé par l’évaluation."""

    model_config = ConfigDict(strict=True, extra='forbid')

    question: NonBlankText
    person_id: NonBlankText
    relevant_ids: Annotated[list[RecordId], Field(min_length=1)]


def _unique_person_ids(values: list[str]) -> list[str]:
    if len(values) != len(set(values)):
        raise ValueError('les identifiants de personnes ne doivent pas être dupliqués')
    return values


PersonIds = Annotated[list[NonBlankText], AfterValidator(_unique_person_ids)]


class Dossier(BaseModel):
    """Périmètre logique d’enquête, pouvant concerner plusieurs personnes."""

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)

    dossier_id: NonBlankText
    title: NonBlankText
    person_ids: PersonIds = Field(default_factory=list)


class Person(BaseModel):
    """Identité de catalogue ; le nom d’affichage n’est pas un identifiant."""

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)

    person_id: NonBlankText
    display_name: NonBlankText


class DocumentMetadata(BaseModel):
    """Référence à une source, sans contenu extrait ni vecteur."""

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)

    document_id: NonBlankText
    dossier_id: NonBlankText
    source_kind: NonBlankText
    source_path: NonBlankText
    source_locator: NonBlankText | None = None
    person_ids: PersonIds = Field(default_factory=list)


class CatalogSeed(BaseModel):
    """Manifeste explicite utilisé pour initialiser le catalogue fictif."""

    model_config = ConfigDict(strict=True, extra='forbid')

    dossiers: Annotated[list[Dossier], Field(min_length=1)]
    persons: list[Person]
    documents: list[DocumentMetadata]
