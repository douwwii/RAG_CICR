"""Contrats du découpage, indépendants du transport et de l’index."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from schemas import DocumentMetadata, NonBlankText


FailureKind = Literal[
    'structure', 'coverage', 'order', 'duplication', 'fidelity',
    'timeout', 'connection', 'http', 'protocol', 'truncated',
]


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)


class PassageProposal(StrictModel):
    title: NonBlankText
    text: str = Field(min_length=1)


class SegmentationProposal(StrictModel):
    passages: list[PassageProposal] = Field(min_length=1)


class Passage(PassageProposal):
    start: int = Field(ge=0)
    end: int = Field(gt=0)


class SegmentedDocument(StrictModel):
    schema_version: Literal[1] = 1
    source: DocumentMetadata
    status: Literal['validated', 'fallback']
    passages: list[Passage] = Field(min_length=1)


class Generation(StrictModel):
    content: str
    done_reason: str | None = None
    server_seconds: float | None = None
    generation_seconds: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class GenerationError(RuntimeError):
    def __init__(self, kind: FailureKind, message: str, generation: Generation | None = None):
        super().__init__(message)
        self.kind = kind
        self.generation = generation


class SegmentationAttempt(StrictModel):
    elapsed_seconds: float
    generation: Generation | None = None
    error: FailureKind | None = None
    detail: str | None = None
    offset: int | None = None


class SegmentationRun(StrictModel):
    document: SegmentedDocument
    prompt_version: NonBlankText
    prompt_sha256: str
    source_sha256: str
    attempts: list[SegmentationAttempt] = Field(min_length=1)
