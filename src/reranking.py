"""Reranking Qwen : identifiants contrôlés, bilan de pertinence, sources inchangées."""
import json
from hashlib import sha256
import logging
from pathlib import Path
from threading import BoundedSemaphore
from time import monotonic
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from segmentation_schemas import GenerationError

PROMPT = (Path(__file__).resolve().parents[1] / 'prompts/reranking/v2.txt').read_text(encoding='utf-8')
MAX_INPUT_BYTES = 60000
_GATE = BoundedSemaphore(1)
Label = Literal['direct', 'partial', 'context', 'unrelated']
Coverage = Literal['direct', 'partial', 'context', 'none', 'contradictory']


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Choice(StrictModel):
    passage_id: str = Field(min_length=1, max_length=200)
    label: Label
    reason: str = Field(min_length=1, max_length=500)


class Proposal(StrictModel):
    selected: list[Choice] = Field(min_length=1, max_length=5)
    coverage: Coverage


def validate_proposal(content, candidates, limit):
    proposal = Proposal.model_validate_json(content)
    known = {c['passage_id']: c for c in candidates}
    selected = [c.passage_id for c in proposal.selected]
    if len(selected) != min(limit, len(candidates)) or len(set(selected)) != len(selected) or not set(selected) <= known.keys():
        raise ValueError('Sélection incomplète, dupliquée ou identifiant inconnu.')
    for choice in proposal.selected:
        if not choice.reason.strip():
            raise ValueError('Justification manquante.')
    labels = [c.label for c in proposal.selected]
    if proposal.coverage == 'direct' and not any(label in {'direct', 'partial'} for label in labels):
        raise ValueError('Bilan direct sans passage direct.')
    if proposal.coverage == 'none' and any(label in {'direct', 'partial'} for label in labels):
        raise ValueError('Bilan sans réponse incohérent avec la sélection.')
    return proposal


def relevance_assessment(proposal):
    """Afficher le jugement de pertinence, sans paraphrase factuelle potentiellement infidèle."""
    groups = {label: [p.passage_id for p in proposal.selected if p.label == label]
              for label in ['direct', 'partial', 'context', 'unrelated']}
    messages = {
        'direct': 'Selon Qwen, les passages sélectionnés permettent de répondre directement à la question.',
        'partial': 'Selon Qwen, ces passages ne répondent qu’à une partie de la question.',
        'context': 'Selon Qwen, ces extraits apportent du contexte mais pas de réponse explicite.',
        'none': 'Selon Qwen, aucune réponse explicite n’est présente dans ces extraits ; cela ne prouve pas son absence du dossier.',
        'contradictory': 'Qwen relève des éléments contradictoires ; les extraits doivent être confrontés sans trancher automatiquement.',
    }
    positive = [p.passage_id for p in proposal.selected if p.label in {'direct', 'partial'}]
    summary = [dict(text=messages[proposal.coverage], passage_ids=positive or [p.passage_id for p in proposal.selected])]
    if groups['direct'] and groups['partial']:
        summary.append(dict(text='Certains passages répondent explicitement, les autres ne couvrent qu’une partie de la demande.', passage_ids=positive))
    related = [p.passage_id for p in proposal.selected if p.label in {'context', 'unrelated'}]
    if positive and related:
        summary.append(dict(text='Les extraits suivants apportent seulement du contexte ou une proximité thématique.', passage_ids=related))
    return dict(coverage=proposal.coverage, summary=summary, summary_mode='relevance_only')


def _payload(question, candidates, limit):
    return json.dumps(dict(question=question, select_count=min(limit, len(candidates)), candidates=[
        {k: c[k] for k in ['passage_id', 'title', 'text', 'name', 'page_start', 'page_end'] if k in c}
        for c in candidates
    ]), ensure_ascii=False)


def cache_key(question, candidates, limit, model):
    # Les scores cosinus ne sont pas envoyés à Qwen : ils ne doivent pas invalider son cache.
    scope = candidates[0]['dossier_id'] if candidates else ''
    return sha256((PROMPT + model + scope + _payload(question, candidates, limit)).encode()).hexdigest()


def rerank(client, question, candidates, *, limit=5, input_budget=MAX_INPUT_BYTES):
    if not 1 <= limit <= 5 or len(candidates) > 30:
        raise ValueError('Cinq résultats maximum et trente candidats maximum.')
    ids = [c['passage_id'] for c in candidates]
    if len(ids) != len(set(ids)) or len({c['dossier_id'] for c in candidates}) > 1:
        raise ValueError('Candidats dupliqués ou issus de plusieurs dossiers.')
    start = monotonic()
    metadata = dict(status='empty', candidate_count=len(candidates), calls=0, duration_seconds=0.0, warning=None)
    if not candidates:
        return dict(results=[], assessment=None, reranking=metadata)
    known = {c['passage_id']: c for c in candidates}
    def call(items):
        payload = _payload(question, items, limit)
        if len(payload.encode('utf-8')) > input_budget:
            raise ValueError('Budget dépassé sans possibilité de conserver les extraits entiers.')
        metadata['calls'] += 1
        generation = client.generate(PROMPT, payload, Proposal.model_json_schema())
        try:
            return validate_proposal(generation.content, items, limit)
        except ValueError:
            schema = Proposal.model_json_schema()
            schema['$defs']['Choice']['properties']['passage_id']['enum'] = [p['passage_id'] for p in items]
            size = min(limit, len(items))
            schema['properties']['selected'].update(minItems=size, maxItems=size)
            metadata['calls'] += 1
            repaired = client.generate(PROMPT + '\nLa réponse précédente était invalide. Respecte exactement les identifiants proposés, le nombre demandé et la cohérence des catégories.', payload, schema)
            return validate_proposal(repaired.content, items, limit)
    try:
        if not _GATE.acquire(timeout=5):
            raise ValueError('Le reranker est occupé.')
        try:
            groups, group = [], []
            for candidate in candidates:
                if group and len(_payload(question, group + [candidate], limit).encode('utf-8')) > input_budget:
                    groups.append(group); group = []
                group.append(candidate)
            if group: groups.append(group)
            if len(groups) > 4:
                raise ValueError('Trop de lots pour une analyse interactive complète.')
            if len(groups) == 1:
                proposal = call(candidates)
            else:
                finalists = []
                for group in groups:
                    finalists.extend(known[c.passage_id] for c in call(group).selected)
                proposal = call(finalists)
        finally:
            _GATE.release()
        results = [dict(known[c.passage_id], relevance=c.label, relevance_reason=c.reason)
                   for c in proposal.selected]
        metadata['status'] = 'applied'
        assessment = relevance_assessment(proposal)
    except (GenerationError, ValueError) as exc:
        reason = str(exc) if type(exc) is ValueError else type(exc).__name__
        logging.getLogger(__name__).warning('Reranking non appliqué : %s', reason)
        metadata.update(status='fallback', warning='Analyse Qwen indisponible ou invalide : classement par similarité, sans bilan.')
        metadata['failure_reason'] = reason
        results, assessment = candidates[:limit], None
    metadata['duration_seconds'] = round(monotonic() - start, 3)
    return dict(results=results, assessment=assessment, reranking=metadata)
