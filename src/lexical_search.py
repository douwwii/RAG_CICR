"""Classement lexical local et fusion de rangs, sans modifier les index persistants."""
from collections import Counter
from math import log
import re
import unicodedata


def tokens(text):
    normalized = unicodedata.normalize('NFKD', text.casefold())
    normalized = ''.join(c for c in normalized if not unicodedata.combining(c))
    return re.findall(r'[^\W_]+', normalized, flags=re.UNICODE)


def rank_lexical(question, candidates, limit, *, exact=False):
    """BM25 sur les mots entiers ; en mode exact, suite contiguë de tous les mots.

    Casse, accents et séparateurs sont normalisés. Une correspondance dans un
    seul champ suffit ; les frontières entre texte et métadonnées sont conservées.
    """
    query = tokens(question)
    if not query or not candidates:
        return []
    sequences = [[tokens(str(c.get(key, ''))) for key in ('text', 'title', 'name', 'document_id')]
                 for c in candidates]
    counts = [Counter(t for sequence in fields for t in sequence) for fields in sequences]
    average = sum(sum(c.values()) for c in counts) / len(counts) or 1
    frequency = {t: sum(t in c for c in counts) for t in set(query)}
    ranked = []
    for candidate, fields, count in zip(candidates, sequences, counts):
        phrase = any(any(seq[i:i + len(query)] == query for i in range(len(seq) - len(query) + 1))
                     for seq in fields)
        if exact and not phrase:
            continue
        length = sum(count.values())
        score = sum(log(1 + (len(counts) - frequency[t] + .5) / (frequency[t] + .5)) *
                    count[t] * 2.2 / (count[t] + 1.2 * (.25 + .75 * length / average))
                    for t in set(query) if count[t])
        if score:
            ranked.append(dict(candidate, score=score, score_kind='lexical', exact_match=phrase))
    return sorted(ranked, key=lambda c: (-c['exact_match'], -c['score'], c['passage_id']))[:limit]


def fuse_ranks(dense, lexical, limit):
    """RRF à poids égaux (k=60), sans comparer BM25 et cosinus."""
    candidates, scores = {}, Counter()
    for ranking in (dense, lexical):
        for rank, candidate in enumerate(ranking, 1):
            key = candidate['passage_id']
            candidates.setdefault(key, candidate)
            scores[key] += 1 / (60 + rank)
    return [dict(candidates[key], score=scores[key], score_kind='rrf')
            for key in sorted(scores, key=lambda k: (-scores[k], k))[:limit]]
