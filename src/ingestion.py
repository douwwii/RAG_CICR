"""Orchestration PDF : extraction, segmentation existante, provenance et indexation."""
from dataclasses import asdict
from contextlib import nullcontext
import json
from pathlib import Path

from pdf_extraction import extract_pdf
from passage_index import IndexedPassage, passage_id
from segmentation import segment_document


def ingest_pdf(path, source, client, embedder, index, artifact_path: Path, progress, *, model_lock=None, coherent=False):
    progress('Extraction du texte')
    extracted = extract_pdf(path)
    progress('Découpage thématique par Qwen')
    root = Path(__file__).resolve().parents[1]
    prompt_version = 'v4-multilingual' if coherent else 'v2-exemples'
    prompt = (root / f'prompts/segmentation/{prompt_version}.txt').read_text(encoding='utf-8')
    if len(extracted.text) > 8000:
        from long_segmentation import segment_long_document
        run = segment_long_document(
            extracted.text, source, client, prompt=prompt, prompt_version=prompt_version,
            checkpoint_dir=artifact_path.parent / 'checkpoints' / source.document_id,
            progress=progress, coherent=coherent,
        )
    else:
        run = segment_document(
            extracted.text, source, client, prompt=prompt, prompt_version=prompt_version,
            restore_separators=True, coherent=coherent,
        )
    if any(a.error in {'connection', 'timeout', 'http', 'protocol', 'truncated'} for a in run.attempts):
        raise ValueError('Qwen est indisponible ou sa réponse est incomplète. Vérifiez le tunnel SSH puis réessayez.')
    progress('Préparation des extraits indexables')
    passages = []
    for parent in run.document.passages:
        parent_id = passage_id(source.document_id, parent.start, parent.end)
        with (model_lock if model_lock is not None else nullcontext()):
            spans = embedder.document_spans(parent.text)
        for left, right in spans:
            start, end = parent.start + left, parent.start + right
            first, last = extracted.page_range(start, end)
            passages.append(IndexedPassage(
                passage_id=passage_id(source.document_id, start, end), parent_id=parent_id,
                document_id=source.document_id, dossier_id=source.dossier_id,
                title=parent.title if run.document.status == 'validated' else 'Extrait du document',
                text=extracted.text[start:end], start=start, end=end, page_start=first, page_end=last,
            ))
    if not passages:
        raise ValueError('Aucun extrait indexable dans ce document.')
    # Source extraite et journal complet conservés avant publication dans l’index.
    artifact = dict(pipeline=('context_coherent_v1' if coherent else 'strict_v1') + ('+windows-v1' if len(extracted.text) > 8000 else ''),
                    text=extracted.text, pages=[asdict(p) for p in extracted.pages],
                    segmentation=run.model_dump(), passages=[p.model_dump() for p in passages])
    temporary = artifact_path.with_suffix('.tmp')
    temporary.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(artifact_path)
    progress('Embeddings et indexation')
    index.add(passages, embedder)
    warning = ('Découpage thématique indisponible : extraits techniques du texte original.'
               if run.document.status == 'fallback' else None)
    return len(extracted.pages), len(passages), warning
