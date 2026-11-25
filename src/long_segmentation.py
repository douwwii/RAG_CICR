"""Fenêtres avec contexte commun, frontières source et checkpoints atomiques."""
from hashlib import sha256
import json
import re
from pathlib import Path

from segmentation import segment_document
from segmentation_schemas import Passage, SegmentedDocument, SegmentationRun

CORE = 6000
CONTEXT = 1000
VERSION = 'windows-v1'
TRANSPORT = {'connection', 'timeout', 'http', 'protocol', 'truncated'}


def boundary(text, target, stop):
    # Préférer une phrase complète ; une très longue phrase reste découpable techniquement.
    ends = [m.end() for m in re.finditer(r'(?:[.!?。！？]\s+|\n\s*\n)', text[max(0, target-CONTEXT):stop])]
    base = max(0, target-CONTEXT)
    return min((base+n for n in ends), key=lambda n: abs(n-target), default=target)


def segment_long_document(text, source, client, *, prompt, prompt_version,
                          checkpoint_dir: Path, progress, coherent=False):
    config = getattr(client, 'config', None)
    identity = config.model_dump(mode='json') if hasattr(config, 'model_dump') else type(client).__name__
    fingerprint = sha256(json.dumps([VERSION, CORE, CONTEXT, text, source.model_dump(), prompt,
                                    prompt_version, coherent, identity], sort_keys=True).encode()).hexdigest()
    directory = checkpoint_dir / fingerprint
    directory.mkdir(parents=True, exist_ok=True)
    cursor, passages, attempts, fallback = 0, [], [], False
    while cursor < len(text):
        left = max(0, cursor-CONTEXT)
        target = min(len(text), cursor+CORE)
        right = min(len(text), target+CONTEXT)
        progress(f'Découpage Qwen : {cursor}/{len(text)} caractères')
        saved = directory / f'{cursor}.json'
        run = None
        if saved.exists():
            try:
                candidate = SegmentationRun.model_validate_json(saved.read_text(encoding='utf-8'))
                if (candidate.source_sha256 == sha256(text[left:right].encode()).hexdigest()
                        and candidate.document.source == source
                        and ''.join(p.text for p in candidate.document.passages) == text[left:right]
                        and all(text[left+p.start:left+p.end] == p.text for p in candidate.document.passages)):
                    run = candidate
            except ValueError:
                pass  # Checkpoint corrompu : recalculer cette fenêtre.
        if run is None:
            run = segment_document(text[left:right], source, client, prompt=prompt,
                                   prompt_version=prompt_version, restore_separators=True, coherent=coherent)
            if any(a.error in TRANSPORT for a in run.attempts):
                raise ValueError('Qwen interrompu : vérifiez le tunnel puis réimportez le même PDF pour reprendre.')
            temporary = saved.with_suffix('.tmp')
            temporary.write_text(run.model_dump_json(), encoding='utf-8')
            temporary.replace(saved)
        attempts.extend(run.attempts)
        fallback |= run.document.status == 'fallback'
        if target == len(text):
            end = target
        else:
            # Conserver si possible une frontière thématique proposée dans la zone commune.
            options = [left+p.end for p in run.document.passages
                       if target-CONTEXT//2 <= left+p.end <= target+CONTEXT//2 and left+p.end < right]
            end = min(options, key=lambda n: abs(n-target)) if options else boundary(text, target, right)
        for p in run.document.passages:
            a, b = max(cursor, left+p.start), min(end, left+p.end)
            if a < b:
                passages.append(Passage(title=p.title, text=text[a:b], start=a, end=b))
        cursor = end
    if (''.join(p.text for p in passages) != text or passages[0].start != 0
            or passages[-1].end != len(text)
            or any(a.end != b.start for a, b in zip(passages, passages[1:]))):
        raise ValueError('Couverture des fenêtres incohérente.')
    return SegmentationRun(document=SegmentedDocument(source=source,
        status='fallback' if fallback else 'validated', passages=passages),
        prompt_version=prompt_version+'+'+VERSION,
        prompt_sha256=sha256(prompt.encode()).hexdigest(), source_sha256=sha256(text.encode()).hexdigest(),
        attempts=attempts)
