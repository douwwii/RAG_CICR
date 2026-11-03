"""Lecture et validation des fichiers JSON, sans embedding ni accès à Qdrant."""
import json
from collections.abc import Sequence
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from schemas import EvaluationCase, FieldRecord


class DataValidationError(ValueError):
    """Données invalides : le message indique le fichier ou l’enregistrement."""


def _read_json_array(path: Path) -> list:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise DataValidationError(f'{path}: JSON UTF-8 invalide : {exc}') from exc
    if not isinstance(data, list):
        raise DataValidationError(f'{path}: une liste JSON est attendue à la racine')
    if not data:
        raise DataValidationError(f'{path}: la liste ne doit pas être vide')
    return data


def validate_corpus(records: Sequence[FieldRecord]) -> None:
    """Vérifie les identifiants d’enregistrements déjà validés individuellement."""
    if not records:
        raise DataValidationError('le corpus ne doit pas être vide')
    seen: dict[int, int] = {}
    for index, record in enumerate(records):
        if record.id in seen:
            raise DataValidationError(
                f'id {record.id} dupliqué aux enregistrements '
                f'[{seen[record.id]}] et [{index}]'
            )
        seen[record.id] = index


def load_field_records(path: Path) -> list[FieldRecord]:
    """Charge un corpus non vide et retourne ses champs typés et validés."""
    path = Path(path)
    data = _read_json_array(path)
    try:
        records = TypeAdapter(list[FieldRecord]).validate_python(data, strict=True)
    except ValidationError as exc:
        raise DataValidationError(f'{path}: {exc}') from exc
    try:
        validate_corpus(records)
    except DataValidationError as exc:
        raise DataValidationError(f'{path}: {exc}') from exc
    return records


def load_evaluation_cases(
    path: Path, records: Sequence[FieldRecord],
) -> list[EvaluationCase]:
    """Valide les questions et leurs références dans le corpus fourni."""
    path = Path(path)
    try:
        validate_corpus(records)
    except DataValidationError as exc:
        raise DataValidationError(f'{path}: corpus de référence invalide : {exc}') from exc
    data = _read_json_array(path)
    try:
        cases = TypeAdapter(list[EvaluationCase]).validate_python(data, strict=True)
    except ValidationError as exc:
        raise DataValidationError(f'{path}: {exc}') from exc

    by_id = {record.id: record for record in records}
    for index, case in enumerate(cases):
        if len(case.relevant_ids) != len(set(case.relevant_ids)):
            raise DataValidationError(
                f'{path}: question [{index}].relevant_ids contient des doublons'
            )
        for reference_index, record_id in enumerate(case.relevant_ids):
            location = f'{path}: question [{index}].relevant_ids[{reference_index}]'
            if record_id not in by_id:
                raise DataValidationError(f'{location}: id {record_id} inexistant')
            if by_id[record_id].person_id != case.person_id:
                raise DataValidationError(
                    f'{location}: id {record_id} associé à '
                    f'{by_id[record_id].person_id}, pas à {case.person_id}'
                )
    return cases
