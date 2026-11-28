"""OCR Inkling : sources durables indépendantes de la génération d'index."""
import base64
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from pydantic import BaseModel, ConfigDict, StrictStr
from pypdf import PdfReader
from config import ROOT, OllamaConfig
from ollama_client import OllamaClient
from pdf_extraction import ExtractedPDF, PageSpan


class OCRPage(BaseModel):
    model_config = ConfigDict(extra='forbid')
    transcription: StrictStr
    observations: StrictStr


def save(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def sidecar(pdf):
    return Path(pdf).with_suffix('.ocr.json')


def client():
    return OllamaClient(OllamaConfig(
        base_url=os.environ.get('SPOC_OCR_URL', 'http://127.0.0.1:11435'),
        model_name=os.environ.get('SPOC_OCR_MODEL', 'inkling-2-mini:26b-a5b-nvfp4'),
        timeout_seconds=600.0, num_predict=16384, think=False))


def transcribe(pdf, progress, *, transport=None, renderer=None):
    pdf = Path(pdf)
    path = sidecar(pdf)
    state = json.loads(path.read_text(encoding='utf-8'))
    llm = transport or client()
    models = llm.installed_models()
    digest = models.get(llm.config.model_name)
    if not digest:
        raise ValueError('Modèle Inkling absent. Vérifiez le tunnel et SPOC_OCR_MODEL.')
    prompt = (ROOT / 'prompts/ocr/v1.txt').read_text(encoding='utf-8')
    reader = PdfReader(pdf)
    if reader.is_encrypted or not 1 <= len(reader.pages) <= 1000:
        raise ValueError('PDF protégé ou nombre de pages invalide.')
    fingerprint = sha256(json.dumps([sha256(pdf.read_bytes()).hexdigest(), digest,
        prompt, llm.config.model_dump(), 'pdftoppm-200dpi-scale2400-v1'], sort_keys=True).encode()).hexdigest()
    if state.get('fingerprint') != fingerprint:
        if state.get('pages'):
            state.setdefault('previous_runs', []).append({k: v for k, v in state.items() if k != 'previous_runs'})
        state.update(pages=[], fingerprint=fingerprint, revisions=[], approved=None)
    state.update(model=llm.config.model_name, model_digest=digest, prompt=prompt,
                 page_count=len(reader.pages), config=llm.config.model_dump())
    if len(state['pages']) > len(reader.pages):
        raise ValueError('Checkpoint OCR incohérent.')
    for number, page in enumerate(state['pages'], 1):
        if page.get('page') != number:
            raise ValueError('Ordre des pages OCR invalide.')
        OCRPage.model_validate({k: page[k] for k in ('transcription', 'observations')})
    save(path, state)
    numbers = ([state['retry_page']] if state.get('retry_page') else
               range(len(state['pages']) + 1, len(reader.pages) + 1))
    for number in numbers:
        progress(f'OCR : {number}/{len(reader.pages)}')
        with TemporaryDirectory(prefix='sillage-ocr-') as directory:
            target = Path(directory) / 'page'
            if renderer:
                image = renderer(pdf, number)
            else:
                subprocess.run(['pdftoppm', '-f', str(number), '-l', str(number), '-r', '200',
                    '-scale-to', '2400', '-singlefile', '-png', str(pdf), str(target)],
                    check=True, timeout=120, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                image = target.with_suffix('.png').read_bytes()
            response = llm._request('/api/chat', dict(model=llm.config.model_name,
                stream=False, think=False, format=OCRPage.model_json_schema(),
                options=dict(temperature=0, num_predict=16384), messages=[
                    dict(role='system', content=prompt),
                    dict(role='user', content=f'Page physique {number}.',
                         images=[base64.b64encode(image).decode()])]))
        if response.get('done') is not True or response.get('done_reason') == 'length':
            raise ValueError('Réponse OCR incomplète. Réessayez cette page.')
        raw = response.get('message', {}).get('content')
        page = OCRPage.model_validate_json(raw)
        result = dict(page=number, **page.model_dump(), raw=raw)
        if number <= len(state['pages']):
            state['revisions'].append(dict(page=number, previous=state['pages'][number - 1]))
            state['pages'][number - 1] = result
        else:
            state['pages'].append(result)
        state.pop('retry_page', None)
        save(path, state)
    return state


def extracted(pdf):
    state = json.loads(sidecar(pdf).read_text(encoding='utf-8'))
    approved = state.get('approved')
    if not approved or len(approved) != state['page_count']:
        raise ValueError('Transcription OCR non approuvée.')
    parts, spans, cursor = [], [], 0
    for number, page in enumerate(approved, 1):
        part = page['transcription'] + '\n\n'
        spans.append(PageSpan(number, cursor, cursor + len(part)))
        cursor += len(part)
        parts.append(part)
    text = ''.join(parts)
    if not text.strip() or len(text) > 2_000_000:
        raise ValueError('Transcription vide ou trop longue.')
    return ExtractedPDF(text, spans)
