"""Préparation d’une requête dense, sans produire de réponse à l’enquête."""
import logging
from contextlib import nullcontext
from pathlib import Path
import re

from pydantic import BaseModel, ConfigDict, Field
from segmentation_schemas import GenerationError

PROMPT = (Path(__file__).resolve().parents[1] / 'prompts/query_rewriting/v5-multilingual.txt').read_text(encoding='utf-8')
_COMMON_CAPITALS = set('Qui Que Quel Quelle Quels Quelles Où Quand Pourquoi Comment Dans Le La Les Un Une Est Qu Je Il Elle Ce Ces Peut À A Y On Et Bonjour Salut Pouvez Peux Pourriez J L Personne Lieu Date Déclarations Témoignage Raisons Informations Éléments Origine Confirmation Vérification Source Identité'.split())
_COMMON_CAPITALS.update('What Where When Who Which Why How Is Are Was Were Did Does Do Can Could The A An Has Have Qué Cuál Cuáles Quién Quiénes Dónde Cuándo Cómo Por El Los Las Se Puede Está Hay'.split())
_NEGATION = r"\b(?:ne|pas|sans|jamais|aucun|aucune|ni|not|no|never|without|neither|nunca|sin|ningún|ninguna|لا|لم|لن|ليس|بدون)\b|\bn[’']"
_MONTHS = r'\b(?:janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre|january|february|march|april|may|june|july|august|september|october|november|december|enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre|يناير|فبراير|مارس|أبريل|ابريل|مايو|يونيو|يوليو|أغسطس|سبتمبر|أكتوبر|نوفمبر|ديسمبر)\b'


class SearchQuery(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    query: str = Field(min_length=1, max_length=800)


def validate_rewrite(question: str, query: str) -> None:
    """Garde-fous conservateurs ; ils ne remplacent pas une validation sémantique."""
    if not query.strip():
        raise ValueError('Requête vide.')
    for pattern in [r'\d+(?:[-/.:]\d+)*', _MONTHS, _NEGATION]:
        if set(re.findall(pattern, question.lower())) != set(re.findall(pattern, query.lower())):
            raise ValueError('Nombre, mois ou négation modifié.')
    # shortcut: les mots capitalisés sont des ancres prudentes, pas une reconnaissance d’entités.
    capitals = lambda text: set(re.findall(r'\b[A-ZÀ-ÖØ-Þ][\w]*(?:-[\w]+)*', text)) - _COMMON_CAPITALS
    if capitals(question) != capitals(query):
        raise ValueError('Nom ou identifiant potentiellement modifié.')
    for marker in ['pense', 'aurait', 'pourrait', 'peut-être', 'might', 'may have', 'possibly', 'habría', 'podría', 'quizás', 'ربما']:
        if marker in question.lower() and marker not in query.lower():
            raise ValueError('Marqueur d’incertitude omis.')
    verification = re.search(r'confirm|vérifi|établi|certain|a-t-il|a-t-elle', question.lower())
    if verification and not query.endswith('?'):
        raise ValueError('Une vérification doit rester une question.')


def rewrite_question(client, question, embedder, *, validation_lock=None):
    try:
        generation = client.generate(PROMPT, question, SearchQuery.model_json_schema())
        query = SearchQuery.model_validate_json(generation.content).query.strip()
        validate_rewrite(question, query)
        # Compter les tokens sans calculer un embedding qui serait jeté.
        with (validation_lock if validation_lock is not None else nullcontext()):
            embedder.validate_query(query)
        return query
    except (GenerationError, ValueError) as exc:
        logging.getLogger(__name__).warning('Reformulation non utilisée (%s) ; question originale conservée.', type(exc).__name__)
        return question
