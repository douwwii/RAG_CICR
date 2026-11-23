"""Exécute un profil de segmentation sur le corpus fictif et écrit un relevé JSONL."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from statistics import mean
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))

from config import OllamaConfig
from ollama_client import OllamaClient
from schemas import DocumentMetadata
from segmentation import segment_document
from segmentation_schemas import GenerationError


CORPUS = Path(__file__).with_name('corpus.json')
PROMPTS = ROOT / 'prompts' / 'segmentation'


def read_exact(path):
    return path.read_bytes().decode('utf-8')


def unique_offset(text, excerpt):
    offset = text.find(excerpt)
    if not excerpt or offset < 0 or text.find(excerpt, offset + 1) >= 0:
        raise ValueError(f'Ancre d’annotation absente ou ambiguë : {excerpt!r}')
    return offset


def annotations(case):
    text = case['text']
    required = {unique_offset(text, anchor) for anchor in case['required_before']}
    optional = {unique_offset(text, anchor) for anchor in case['optional_before']}
    protected = [(start, start + len(excerpt)) for excerpt in case['keep_together']
                 for start in [unique_offset(text, excerpt)]]
    if required & optional or 0 in required | optional:
        raise ValueError(f'Frontières incompatibles pour {case["id"]}.')
    if any(start < cut < end for cut in required | optional for start, end in protected):
        raise ValueError(f'Frontière annotée au milieu d’un extrait protégé pour {case["id"]}.')
    return required, optional, protected


def boundary_scores(text, offsets, expected):
    required, optional, protected = expected
    cuts = set()
    for offset in offsets:
        # Tolérer le côté auquel les blancs sont attachés uniquement pour le score
        # sémantique. Le contrôle de copie exacte a déjà eu lieu.
        while offset < len(text) and text[offset].isspace():
            offset += 1
        cuts.add(offset)
    return {
        'required_found': sorted(required & cuts),
        'required_missed': sorted(required - cuts),
        'unexpected': sorted(cuts - required - optional),
        'protected_split': [[start, end] for start, end in protected
                            if any(start < cut < end for cut in cuts)],
    }


def fixed_size_offsets(text, size):
    # Les coupures de référence reculent au dernier espace disponible.
    start = 0
    while len(text) - start > size:
        end = text.rfind(' ', start + 1, start + size + 1)
        start = end + 1 if end >= 0 else start + size
        yield start


def main():
    defaults = OllamaConfig()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prompt', type=Path, default=PROMPTS / 'v1.txt')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--split', choices=('calibration', 'reserve'), default='calibration')
    parser.add_argument('--case', action='append', help='Identifiant de cas, option répétable')
    parser.add_argument('--model', default=defaults.model_name)
    parser.add_argument('--url', default=defaults.base_url)
    parser.add_argument('--temperature', type=float, default=defaults.temperature)
    parser.add_argument('--think', choices=('yes', 'no', 'default'), default='no')
    parser.add_argument('--format', choices=('schema', 'json'), default=defaults.output_format)
    parser.add_argument('--timeout', type=float, default=defaults.timeout_seconds)
    parser.add_argument('--num-predict', type=int, default=defaults.num_predict)
    parser.add_argument('--retry', action='store_true', help='Autorise une reprise sur sortie invalide')
    parser.add_argument('--allow-load', action='store_true',
                        help='Autorise le chargement d’un modèle installé si Ollama est vide au démarrage')
    parser.add_argument('--fixed-size', type=int, default=240, help='Taille de référence en caractères')
    parser.add_argument('--baseline-only', action='store_true', help='Évalue la référence sans appeler Ollama')
    args = parser.parse_args()
    if args.fixed_size < 1:
        parser.error('--fixed-size doit être positif.')
    if args.output.exists():
        parser.error('Choisir un nouveau fichier --output.')

    raw_corpus = read_exact(CORPUS)
    selected = [case for case in json.loads(raw_corpus) if case['split'] == args.split
                and (not args.case or case['id'] in args.case)]
    if not selected or (args.case and {case['id'] for case in selected} != set(args.case)):
        parser.error('Aucun cas correspondant ou identifiant absent de la partition choisie.')
    cases = [(case, annotations(case)) for case in selected]
    prompt = read_exact(args.prompt)
    config = OllamaConfig(
        base_url=args.url, model_name=args.model, timeout_seconds=args.timeout,
        temperature=args.temperature, num_predict=args.num_predict,
        think={'yes': True, 'no': False, 'default': None}[args.think], output_format=args.format,
    )
    client = OllamaClient(config)
    digest = None
    if not args.baseline_only:
        try:
            loaded = client.loaded_models()
            available = loaded if loaded or not args.allow_load else client.installed_models()
        except GenerationError as exc:
            parser.exit(1, f'Accès à Ollama impossible ({exc.kind}) — {exc}\n')
        if config.model_name not in available:
            parser.exit(1, f'{config.model_name} indisponible avec les conditions de chargement choisies.\n')
        digest = available[config.model_name]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    counts = Counter()
    errors = Counter()
    durations = []
    generation_durations = []
    validated_scores = Counter()
    fixed_scores = Counter()
    with args.output.open('x', encoding='utf-8') as stream:
        def write(record):
            stream.write(json.dumps(record, ensure_ascii=False) + '\n')
            stream.flush()

        write({
            'type': 'run', 'split': args.split, 'cases': [case['id'] for case, _ in cases],
            'corpus_sha256': sha256(raw_corpus.encode('utf-8')).hexdigest(),
            'prompt_version': args.prompt.stem, 'prompt': prompt,
            'model_digest': digest, 'ollama': config.model_dump(), 'retry': args.retry,
            'allow_load': args.allow_load,
            'baseline_only': args.baseline_only, 'fixed_size': args.fixed_size,
        })
        for case, expected in cases:
            text = case['text']
            record = {'type': 'case', 'fixture': case}
            fixed = boundary_scores(text, fixed_size_offsets(text, args.fixed_size), expected)
            record['fixed_size_scores'] = fixed
            fixed_scores.update({key: len(value) for key, value in fixed.items()})
            if not args.baseline_only:
                source = DocumentMetadata(
                    dossier_id='DOS-SEG-FICTIF', document_id=case['id'],
                    source_kind='synthetic_text', source_path=str(CORPUS.relative_to(ROOT)),
                    source_locator=case['id'],
                )
                result = segment_document(
                    text, source, client, prompt=prompt, prompt_version=args.prompt.stem,
                    retry_invalid=args.retry,
                )
                record['output'] = result.model_dump()
                attempts = result.attempts
                durations.extend(item.elapsed_seconds for item in attempts)
                generation_durations.extend(
                    item.generation.generation_seconds for item in attempts
                    if item.generation is not None and item.generation.generation_seconds is not None
                )
                errors.update(item.error for item in attempts if item.error is not None)
                if result.document.status == 'validated':
                    counts['first_attempt' if len(attempts) == 1 else 'after_retry'] += 1
                    scores = boundary_scores(text, (item.end for item in result.document.passages[:-1]), expected)
                    record['llm_scores'] = scores
                    validated_scores.update({key: len(value) for key, value in scores.items()})
                else:
                    counts['fallback'] += 1
                print(case['id'], result.document.status, len(result.document.passages), 'passage(s)', flush=True)
            write(record)
        summary = {
            'type': 'summary', 'documents': len(cases),
            'outcomes': {key: counts[key] for key in ('first_attempt', 'after_retry', 'fallback')},
            'attempt_errors': dict(errors),
            'first_attempt_success_rate': counts['first_attempt'] / len(cases) if durations else None,
            'fallback_rate': counts['fallback'] / len(cases) if durations else None,
            'mean_call_seconds': mean(durations) if durations else None,
            'mean_generation_seconds': mean(generation_durations) if generation_durations else None,
            'llm_validated_only': dict(validated_scores),
            'fixed_size': dict(fixed_scores),
        }
        write(summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
