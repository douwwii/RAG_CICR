"""Mesure BGE-M3 sur la transcription dans un Qdrant en mémoire, hors index actif."""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def normalize(text):
    return ' '.join(text.casefold().split())


def load_pages(path):
    source = path.read_text(encoding='utf-8')
    matches = list(re.finditer(r'^## Page (\d+)\s*$', source, re.MULTILINE))
    pages = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(source)
        # Le texte, les annotations et les pages quasi blanches restent inchangés.
        pages[int(match.group(1))] = source[match.end():end]
    if sorted(pages) != list(range(1, 81)) or len(matches) != 80:
        raise ValueError('Les 80 pages physiques de la transcription sont requises.')
    return source, pages


def make_passages(pages, size=1600, overlap=300):
    passages = []
    for page, text in pages.items():
        start = 0
        covered_until = 0
        while start < len(text):
            end = min(start + size, len(text))
            if end < len(text):
                boundary = text.rfind(' ', start + size // 2, end)
                if boundary > start:
                    end = boundary + 1
            assert start <= covered_until and end > start
            covered_until = max(covered_until, end)
            if text[start:end].strip():
                passages.append(dict(
                    passage_id=f'p{page:02}-{start:05}', dossier_id='MANCHA4-EVAL',
                    document_id='transcription-mancha4', page_start=page, page_end=page,
                    start=start, end=end, title='', name='transcription.md',
                    text=text[start:end],
                ))
            if end == len(text):
                break
            start = end - overlap
        assert covered_until == len(text)
    return passages


def contains_evidence(passage, alternative):
    return (passage['page_start'] in alternative['pages']
            and normalize(alternative['quote']) in normalize(passage['text']))


def group_found(hits, group):
    return any(contains_evidence(hit, alt) for hit in hits for alt in group)


def score(hits, case):
    # Les ancres ne prouvent pas l'exhaustivité sémantique d'une réponse générée.
    if case['answerability'] == 'not_in_corpus':
        return None
    groups = case['evidence_groups']
    found = [group_found(hits[:5], group) for group in groups]
    ranks = [rank for rank, hit in enumerate(hits[:5], 1)
             if any(group_found([hit], group) for group in groups)]
    return dict(
        hit1=bool(ranks and ranks[0] == 1),
        anchor_recall5=sum(found) / len(groups), coverage5=all(found),
        mrr5=1 / ranks[0] if ranks else 0,
        found_groups=[i + 1 for i, value in enumerate(found) if value],
        missing_groups=[i + 1 for i, value in enumerate(found) if not value],
    )


def validate(cases, pages, passages):
    if len(cases) != 40 or len({c['id'] for c in cases}) != 40:
        raise ValueError('40 cas distincts sont requis.')
    for case in cases:
        if case['answerability'] != 'not_in_corpus' and not case['evidence_groups']:
            raise ValueError(f'{case["id"]}: preuve manquante')
        for group in case['evidence_groups']:
            for alt in group:
                for page in alt['pages']:
                    if normalize(alt['quote']) not in normalize(pages[page]):
                        raise ValueError(f'{case["id"]}: citation absente de la page {page}: {alt["quote"]}')
            if not group_found(passages, group):
                raise ValueError(f'{case["id"]}: ancre non couverte par le découpage')
    for passage in passages:
        assert passage['text'] == pages[passage['page_start']][passage['start']:passage['end']]
    # Petits contrôles des métriques: rang, groupes obligatoires et abstention.
    demo = dict(answerability='supported', evidence_groups=[
        [dict(pages=[1], quote='alpha')], [dict(pages=[2], quote='beta')]])
    hits = [dict(page_start=9, text='rien'), dict(page_start=1, text='alpha'),
            dict(page_start=2, text='beta')]
    measured = score(hits, demo)
    assert measured['coverage5'] and measured['mrr5'] == 0.5 and not measured['hit1']
    assert score(hits[:2], demo)['anchor_recall5'] == 0.5
    assert score(hits, dict(answerability='not_in_corpus')) is None
    assert not contains_evidence(dict(page_start=2, text='alpha'), dict(pages=[1], quote='alpha'))


def probe(url):
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            response.read(1)
        return dict(url=url, available=True)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return dict(url=url, available=False, error=type(exc).__name__)


def aggregate(rows):
    measured = [r['metrics'] for r in rows if r['metrics'] is not None]
    return dict(n=len(measured),
                **{key: sum(m[key] for m in measured) / len(measured) if measured else None
                   for key in ['hit1', 'anchor_recall5', 'coverage5', 'mrr5']})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--transcript', type=Path, default=ROOT.parent / 'transcription.md')
    parser.add_argument('--validate-only', action='store_true')
    parser.add_argument('--qwen', action='store_true', help='Ajoute reformulation et reranking; le découpage reste technique.')
    args = parser.parse_args()
    source, pages = load_pages(args.transcript)
    questions_path = HERE / 'questions.json'
    annotations = json.loads(questions_path.read_text(encoding='utf-8'))
    cases = annotations['cases']
    passages = make_passages(pages)
    validate(cases, pages, passages)
    print(f'Validé: {len(cases)} questions, {len(pages)} pages, {len(passages)} passages exacts.', flush=True)
    if args.validate_only:
        return

    from config import OllamaConfig
    from web.index_config import BGE_CONFIG, create_embedder
    from qdrant_client import QdrantClient, models

    services = [probe('http://127.0.0.1:8000/openapi.json'),
                probe(OllamaConfig().base_url + '/api/tags')]
    qwen = None
    if args.qwen:
        if not services[1]['available']:
            raise SystemExit('Qwen indisponible: rétablir le tunnel avant --qwen.')
        from ollama_client import OllamaClient
        from segmentation_schemas import Generation
        cache_path = HERE / 'qwen-generations.json'
        cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}

        class RecordedClient(OllamaClient):
            def generate(self, prompt, text, schema):
                key = hashlib.sha256(json.dumps(
                    [self.config.model_dump(), prompt, text, schema],
                    sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                if key not in cache:
                    cache[key] = super().generate(prompt, text, schema).model_dump()
                    temporary = cache_path.with_suffix('.tmp')
                    temporary.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding='utf-8')
                    temporary.replace(cache_path)
                return Generation.model_validate(cache[key])

        qwen = RecordedClient(OllamaConfig(timeout_seconds=None))
    started = time.monotonic()
    encoder = create_embedder(BGE_CONFIG)
    load_seconds = time.monotonic() - started
    index_start = time.monotonic()
    vectors = encoder.embed_documents([p['text'] for p in passages])
    database = QdrantClient(':memory:')
    try:
        database.create_collection('mancha4', vectors_config=models.VectorParams(
            size=encoder.dimension, distance=models.Distance.COSINE))
        database.upsert('mancha4', [models.PointStruct(id=i, vector=vector.tolist(), payload=p)
                                  for i, (p, vector) in enumerate(zip(passages, vectors))])
        index_seconds = time.monotonic() - index_start
        rows = []
        for case in cases:
            start = time.monotonic()
            query = case['question_es']
            if qwen:
                from query_rewriting import rewrite_question
                query = rewrite_question(qwen, query, encoder)
            vector = encoder.embed_query(query)
            candidates = [dict(hit.payload, score=hit.score) for hit in database.query_points(
                'mancha4', query=vector.tolist(), limit=30).points]
            baseline = candidates[:5]
            response = None
            if qwen:
                from reranking import rerank
                response = rerank(qwen, case['question_es'], candidates)
            hits = response['results'] if response else baseline
            elapsed = time.monotonic() - start
            row = dict(id=case['id'], question_es=case['question_es'], query=query,
                       category=case['category'], answerability=case['answerability'],
                       seconds=round(elapsed, 4), metrics=score(hits, case),
                       baseline_metrics=score(baseline, case), results=hits,
                       assessment=response['assessment'] if response else None,
                       reranking=response['reranking'] if response else None,
                       manual_review=dict(status='pending', answer_score_0_to_2=None,
                                          critical_error=None, notes=None))
            rows.append(row)
            if qwen:
                partial = HERE / 'results-qwen.partial.json'
                partial.write_text(json.dumps(dict(complete=False, rows=rows), ensure_ascii=False, indent=2), encoding='utf-8')
            status = 'hors score' if row['metrics'] is None else ('complet' if row['metrics']['coverage5'] else 'incomplet')
            print(f'{case["id"]} {status} {elapsed:.2f}s', flush=True)
        report = dict(
            executed_at=datetime.now(ZoneInfo('Europe/Paris')).isoformat(),
            mode='technical_chunks_qwen' if qwen else 'technical_chunks_bge_only',
            qwen_config=qwen.config.model_dump() if qwen else None,
            transcript_sha256=hashlib.sha256(source.encode()).hexdigest(),
            questions_sha256=hashlib.sha256(questions_path.read_bytes()).hexdigest(),
            annotation_revision=annotations['annotation_revision'],
            annotation_audit=annotations['annotation_audit'],
            profile=encoder.profile.model_dump(), services=services,
            chunking=dict(size_characters=1600, overlap_characters=300,
                          respect_page_boundaries=True, preserve_blank_pages=True),
            page_count=len(pages), passage_count=len(passages), question_count=len(cases),
            answerability_counts=dict(Counter(c['answerability'] for c in cases)),
            load_seconds=round(load_seconds, 3), index_seconds=round(index_seconds, 3),
            search_seconds=round(sum(r['seconds'] for r in rows), 3),
            summary=aggregate(rows),
            by_category={category: aggregate([r for r in rows if r['category'] == category])
                         for category in dict.fromkeys(c['category'] for c in cases)},
            limitations=[
                'Corpus unique; faits et reformulations non indépendants.',
                'Découpage technique de la transcription, pas segmentation Qwen du PDF.',
                'Ancres minimales: localisation de preuves, pas validation sémantique complète.',
                'Les cas not_in_corpus sont exclus des métriques de retrieval.',
                'Aucune réponse générée ni évaluation automatique des hallucinations.',
                'Aucun corpus distracteur d’autres dossiers: isolation applicative non testée.',
            ], rows=rows,
        )
        destination = HERE / ('results-qwen.json' if qwen else 'results.json')
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        if qwen:
            (HERE / 'results-qwen.partial.json').unlink(missing_ok=True)
        print(json.dumps(report['summary'], ensure_ascii=False), flush=True)
    finally:
        database.close()


if __name__ == '__main__':
    main()
