"""Découpage thématique avec validation exacte et repli explicite."""
from hashlib import sha256
from time import monotonic
from typing import Protocol

from schemas import DocumentMetadata
from segmentation_schemas import (
    Generation, GenerationError, Passage, SegmentationAttempt, SegmentationProposal, SegmentationRun,
    SegmentedDocument,
)
from segmentation_validation import SegmentationValidationError, validate_segmentation


class SegmentationClient(Protocol):
    def generate(self, system_prompt: str, text: str, schema: dict) -> Generation: ...


def segment_document(
    text: str,
    source: DocumentMetadata,
    client: SegmentationClient,
    *,
    prompt: str,
    prompt_version: str,
    retry_invalid: bool = True,
) -> SegmentationRun:
    if not text or not prompt.strip() or not prompt_version.strip():
        raise ValueError('Le texte, le prompt et sa version sont requis.')
    source_digest = sha256(text.encode('utf-8')).hexdigest()
    prompt_digest = sha256(prompt.encode('utf-8')).hexdigest()
    schema = SegmentationProposal.model_json_schema()
    attempts = []
    passages = None
    system_prompt = prompt
    for _ in range(2 if retry_invalid else 1):
        started = monotonic()
        try:
            generation = client.generate(system_prompt, text, schema)
        except GenerationError as exc:
            attempts.append(SegmentationAttempt(
                elapsed_seconds=monotonic() - started, generation=exc.generation,
                error=exc.kind, detail=str(exc),
            ))
            break
        elapsed = monotonic() - started
        try:
            passages = validate_segmentation(text, generation.content)
        except SegmentationValidationError as exc:
            attempts.append(SegmentationAttempt(
                elapsed_seconds=elapsed, generation=generation,
                error=exc.kind, detail=str(exc), offset=exc.offset,
            ))
            system_prompt = (
                f'{prompt}\n\nLa proposition précédente a échoué au contrôle {exc.kind}. {exc} '
                'Repars du document complet et recopie tous les caractères, séparateurs compris.'
            )
        else:
            attempts.append(SegmentationAttempt(elapsed_seconds=elapsed, generation=generation))
            break

    status = 'validated' if passages is not None else 'fallback'
    document = SegmentedDocument(
        source=source, status=status,
        passages=passages if passages is not None else [
            Passage(title='Document intégral', text=text, start=0, end=len(text)),
        ],
    )
    return SegmentationRun(
        document=document, prompt_version=prompt_version, prompt_sha256=prompt_digest,
        source_sha256=source_digest, attempts=attempts,
    )
