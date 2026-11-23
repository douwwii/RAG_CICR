"""Validation exacte des extraits et positions dans le texte donné au modèle."""
from collections import Counter
import json

from pydantic import ValidationError

from segmentation_schemas import FailureKind, Passage, SegmentationProposal


class SegmentationValidationError(ValueError):
    def __init__(self, kind: FailureKind, message: str, offset: int | None = None):
        super().__init__(message)
        self.kind = kind
        self.offset = offset


def _diagnose(source: str, excerpts: list[str], index: int, offset: int) -> FailureKind:
    # Un alignement glouton sert au diagnostic uniquement. Une même
    # répétition peut avoir plusieurs alignements dans la source.
    if any(count > source.count(text) > 0 for text, count in Counter(excerpts).items()):
        return 'duplication'
    cursor = 0
    last_start = -1
    for excerpt in excerpts:
        start = source.find(excerpt, cursor)
        if start < 0:
            previous = source.find(excerpt)
            if 0 <= previous < last_start:
                return 'order'
            if previous >= 0:
                return 'duplication'
            break
        last_start = start
        cursor = start + len(excerpt)
    if source.find(excerpts[index], offset + 1) >= 0:
        return 'coverage'
    return 'fidelity'


def validate_segmentation(source: str, response: str) -> list[Passage]:
    try:
        proposal = SegmentationProposal.model_validate_json(response)
    except ValidationError as exc:
        issue = exc.errors(include_input=False, include_url=False, include_context=False)[0]
        location = '.'.join(map(str, issue['loc'])) or 'réponse'
        raise SegmentationValidationError('structure', f'{location} — {issue["msg"]}') from exc

    excerpts = [item.text for item in proposal.passages]
    cursor = 0
    passages = []
    for index, item in enumerate(proposal.passages):
        end = cursor + len(item.text)
        expected = source[cursor:end]
        if expected != item.text:
            divergence = next(
                (i for i, (left, right) in enumerate(zip(expected, item.text)) if left != right),
                len(expected),
            )
            kind = _diagnose(source, excerpts, index, cursor)
            raise SegmentationValidationError(
                kind, f'Passage {index + 1}, divergence à la position {cursor + divergence}.',
                cursor + divergence,
            )
        passages.append(Passage(title=item.title, text=expected, start=cursor, end=end))
        cursor = end
    if cursor != len(source):
        raise SegmentationValidationError(
            'coverage', f'{len(source) - cursor} caractères non couverts en fin de texte.', cursor,
        )
    return passages


def validate_source_alignment(source: str, response: str) -> list[Passage]:
    """Restaurer seulement les séparateurs omis entre extraits exacts et ordonnés."""
    try:
        return validate_segmentation(source, response)
    except SegmentationValidationError as original:
        try:
            proposal = SegmentationProposal.model_validate_json(response)
        except ValidationError:
            raise original
        cursor = 0
        starts = []
        for passage in proposal.passages:
            start = source.find(passage.text, cursor)
            if not passage.text.strip() or start < 0 or source[cursor:start].strip():
                raise original
            starts.append(start)
            cursor = start + len(passage.text)
        if source[cursor:].strip():
            raise original
        bounds = [0, *starts[1:], len(source)]
        restored = {'passages': [
            {'title': p.title, 'text': source[a:b]}
            for p, a, b in zip(proposal.passages, bounds[:-1], bounds[1:], strict=True)
        ]}
        return validate_segmentation(source, json.dumps(restored))
