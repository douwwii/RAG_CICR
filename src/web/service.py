"""Ressources locales partagées : un encodeur, un client Qdrant, une file d’import."""
from concurrent.futures import ThreadPoolExecutor
from collections import OrderedDict
from copy import deepcopy
from hashlib import sha256
import json
import logging
import os
from pathlib import Path
from threading import RLock
from uuid import uuid4

from qdrant_client import QdrantClient

from catalog import Catalog
from common import CATALOG_FILE, DATA_FILE
from config import ROOT, OllamaConfig
from ingestion import ingest_pdf
from ollama_client import OllamaClient
from passage_index import PassageIndex
from qdrant_store import QdrantVectorStore
from schemas import DocumentMetadata
from search import retrieve
from query_rewriting import rewrite_question
from reranking import rerank, cache_key as reranking_key
from web.jobs import JobRepository
from web.index_config import WebIndexConfig, create_embedder

log = logging.getLogger(__name__)


class WebService:
    def __init__(self, *, catalog_path=CATALOG_FILE, data_path=None, vector_path=None,
                 embedder=None, llm=None, qdrant=None, index_config=None):
        self.catalog_path = Path(catalog_path)
        self.data_path = Path(data_path or os.environ.get('SPOC_WEB_DATA', ROOT / 'web_data')).resolve()
        self.data_path.mkdir(parents=True, exist_ok=True)
        self.index_config = index_config or (WebIndexConfig(artifact_path=self.data_path) if (qdrant is not None or vector_path is not None) else WebIndexConfig.load(self.data_path))
        self.artifact_path = self.index_config.artifact_path
        self.artifact_path.mkdir(parents=True, exist_ok=True)
        self.jobs = JobRepository(self.data_path / 'jobs.sqlite')
        self.lock = RLock()
        self.reranking_cache = OrderedDict()
        self.rerank_candidates = int(os.environ.get('SPOC_RERANK_CANDIDATES', '30'))
        if not 20 <= self.rerank_candidates <= 30:
            raise ValueError('SPOC_RERANK_CANDIDATES doit être compris entre 20 et 30.')
        self.embedder = embedder
        self.llm = llm or OllamaClient(OllamaConfig(
            base_url=os.environ.get('SPOC_OLLAMA_URL', 'http://127.0.0.1:11435'),
            model_name=os.environ.get('SPOC_OLLAMA_MODEL', 'qwen3.8:27b-mlx'),
            timeout_seconds=180.0, num_predict=16384,
        ))
        self.client = qdrant or QdrantClient(path=str(vector_path or self.index_config.fields.path))
        self.legacy = QdrantVectorStore(config=self.index_config.fields, client=self.client)
        self.passages = PassageIndex(self.client, collection=self.index_config.passage_collection)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='pdf-ingestion')

    def close(self):
        self.executor.shutdown(wait=True)
        self.client.close()

    def encoder(self):
        if self.embedder is None:
            self.embedder = create_embedder(self.index_config.embedding)
        return self.embedder

    def dossiers(self):
        with Catalog(self.catalog_path, read_only=True) as catalog:
            return [d.model_dump() for d in catalog.list_dossiers()]

    def require_dossier(self, dossier_id):
        with Catalog(self.catalog_path, read_only=True) as catalog:
            catalog.list_documents(dossier_id)

    def legacy_ids(self):
        if not self.client.collection_exists(self.index_config.fields.collection_name):
            return set()
        ids, offset = set(), None
        while True:
            points, offset = self.client.scroll(self.index_config.fields.collection_name, limit=256,
                                               offset=offset, with_payload=['document_id'], with_vectors=False)
            ids.update(p.payload['document_id'] for p in points)
            if offset is None:
                return ids

    def documents(self, dossier_id):
        with self.lock, Catalog(self.catalog_path, read_only=True) as catalog:
            documents = catalog.list_documents(dossier_id)
            jobs = self.jobs.documents(dossier_id)
            for document_id, job in jobs.items():
                if job['status'] == 'done' and not (self.artifact_path / (document_id + '.json')).exists():
                    job.update(status='not_indexed', stage='Non indexé dans cette version',
                               warning='Réimportez ce document pour l’indexer dans cette version.')
            indexed = self.legacy_ids()
            from data_loader import load_field_records
            labels = {r.document_id: r for r in load_field_records(DATA_FILE)}
            persons = {p.person_id: p.display_name for p in catalog.list_persons(dossier_id)}
            def display_name(document):
                if document.document_id in jobs:
                    return jobs[document.document_id]['filename']
                record = labels.get(document.document_id)
                if record:
                    return f'{record.field_label} · {persons.get(record.person_id, record.person_id)}'
                return Path(document.source_path).name
            return [dict(document_id=d.document_id, dossier_id=d.dossier_id,
                         name=display_name(d),
                         kind=d.source_kind, person_ids=d.person_ids,
                         status=jobs[d.document_id]['status'] if d.document_id in jobs else
                         ('done' if d.document_id in indexed else 'not_indexed'),
                         job=self.jobs.public(jobs[d.document_id]) if d.document_id in jobs else None,
                         has_pdf=d.source_kind == 'pdf' and d.document_id in jobs)
                    for d in documents]

    def submit(self, dossier_id, filename, content):
        self.require_dossier(dossier_id)
        digest = sha256(content).hexdigest()
        with self.lock:
            previous = self.jobs.duplicate(dossier_id, digest)
            if previous:
                missing_artifact = previous['status'] == 'done' and not (self.artifact_path / (previous['document_id'] + '.json')).exists()
                if previous['status'] != 'error' and not missing_artifact:
                    return dict(job=self.jobs.public(previous), duplicate=True)
                self.jobs.update(previous['job_id'], status='queued', stage='En attente', error=None, warning=None)
                job_id, document_id = previous['job_id'], previous['document_id']
                with Catalog(self.catalog_path, read_only=True) as catalog:
                    source = catalog.get_document(dossier_id, document_id)
                if source is None:
                    raise ValueError('La source de cet import est absente du catalogue.')
            else:
                job_id, document_id = str(uuid4()), 'DOC-' + str(uuid4())
                path = self.data_path / (document_id + '.pdf')
                path.write_bytes(content)
                source = DocumentMetadata(document_id=document_id, dossier_id=dossier_id,
                                          source_kind='pdf', source_path=str(path))
                with Catalog(self.catalog_path) as catalog:
                    catalog.register(documents=[source])
                self.jobs.create(job_id, document_id, dossier_id, digest, filename)
            self.executor.submit(self.process, job_id, source)
            return dict(job=self.jobs.public(self.jobs.get(job_id)), duplicate=False)

    def process(self, job_id, source):
        def progress(stage):
            self.jobs.update(job_id, status='running', stage=stage)
        try:
            progress('Chargement du modèle d’embedding')
            with self.lock:
                embedder = self.encoder()
            # Qwen peut travailler pendant une recherche ; seul l’accès local au modèle/index est sérialisé.
            class LockedIndex:
                def add(_, passages, encoder):
                    with self.lock:
                        self.passages.add(passages, encoder)
            pages, count, warning = ingest_pdf(
                Path(source.source_path), source, self.llm, embedder, LockedIndex(),
                self.artifact_path / (source.document_id + '.json'), progress, model_lock=self.lock,
                coherent=self.index_config.coherent,
            )
            self.jobs.update(job_id, status='done', stage='Terminé', page_count=pages,
                             passage_count=count, warning=warning)
        except Exception as exc:
            log.exception('Échec de l’import %s', job_id)
            message = str(exc) if isinstance(exc, ValueError) else 'Le traitement a échoué. Consultez le journal du serveur.'
            # Les chemins internes ne font jamais partie des erreurs renvoyées au navigateur.
            if str(ROOT) in message or str(self.data_path) in message:
                message = 'Le traitement a échoué. Consultez le journal du serveur.'
            self.jobs.update(job_id, status='error', stage='Erreur', error=message)

    def artifact(self, dossier_id, document_id):
        job = self.jobs.documents(dossier_id).get(document_id)
        if not job or job['status'] != 'done':
            raise ValueError('Document pas encore indexé.')
        return json.loads((self.artifact_path / (document_id + '.json')).read_text(encoding='utf-8'))

    def retrieve_candidates(self, dossier_id, question, candidate_k=30):
        self.require_dossier(dossier_id)
        if not 1 <= candidate_k <= 30:
            raise ValueError('Entre 1 et 30 candidats sont requis.')
        top_k = candidate_k
        # L’appel distant ne bloque pas le catalogue ni les autres recherches.
        with self.lock:
            embedder = self.encoder()
        client = self.llm
        if isinstance(client, OllamaClient):
            client = OllamaClient(client.config.model_copy(update={'num_predict': 512, 'timeout_seconds': 45.0}))
        question = rewrite_question(client, question, embedder, validation_lock=self.lock)
        with self.lock, Catalog(self.catalog_path, read_only=True) as catalog:
            documents = {d.document_id: d for d in catalog.list_documents(dossier_id)}
            if not documents:
                return []
            embedder = self.encoder()
            results = []
            persons = {p.person_id: p.display_name for p in catalog.list_persons(dossier_id)}
            if self.client.collection_exists(self.index_config.fields.collection_name):
                for hit in retrieve(self.legacy, embedder, question, catalog=catalog,
                                    dossier_id=dossier_id, top_k=top_k,
                                    text_builder_version=self.index_config.text_builder_version):
                    p = hit.payload
                    results.append(dict(passage_id=str(hit.id), document_id=p.document_id,
                                        dossier_id=dossier_id, title=p.field_label, text=p.value,
                                        score=hit.score, page_start=None, page_end=None,
                                        name=f'{p.field_label} · {persons.get(p.person_id, p.person_id)}', kind=p.source_kind))
            ready = {k: j for k, j in self.jobs.documents(dossier_id).items() if j['status'] == 'done'}
            ready = {k: j for k, j in ready.items() if (self.artifact_path / (k + '.json')).exists()}
            vector = embedder.embed_query(question)
            for p, score in self.passages.search(vector, embedder, dossier_id, list(ready), top_k):
                if p.document_id not in documents:
                    raise ValueError('Source absente du dossier.')
                artifact = self.artifact(dossier_id, p.document_id)
                saved = next((item for item in artifact['passages'] if item['passage_id'] == p.passage_id), None)
                if saved != p.model_dump() or artifact['text'][p.start:p.end] != p.text:
                    raise ValueError('Le passage ne correspond plus au texte source.')
                results.append(dict(passage_id=p.passage_id, parent_id=p.parent_id,
                                    document_id=p.document_id, dossier_id=dossier_id, title=p.title,
                                    text=p.text, score=score, page_start=p.page_start, page_end=p.page_end,
                                    name=ready[p.document_id]['filename'], kind='pdf'))
            return sorted(results, key=lambda r: r['score'], reverse=True)[:top_k]

    def search_analysis(self, dossier_id, question, top_k=5, *, candidate_k=None):
        if not 1 <= top_k <= 5:
            raise ValueError('Entre 1 et 5 résultats sont requis.')
        candidates = self.retrieve_candidates(dossier_id, question, candidate_k or self.rerank_candidates)
        model = self.llm.config.model_name if isinstance(self.llm, OllamaClient) else type(self.llm).__name__
        cache_key = reranking_key(question, candidates, top_k, model)
        with self.lock:
            cached = self.reranking_cache.get(cache_key)
            if cached is not None:
                self.reranking_cache.move_to_end(cache_key)
                response = deepcopy(cached)
                current = {p['passage_id']: p for p in candidates}
                response['results'] = [dict(current[p['passage_id']], relevance=p['relevance'],
                                            relevance_reason=p['relevance_reason']) for p in response['results']]
                response['reranking'].update(cached=True, calls=0, duration_seconds=0.0)
                return response
        client = self.llm
        if isinstance(client, OllamaClient):
            client = OllamaClient(client.config.model_copy(update={'num_predict': 2048, 'timeout_seconds': 90.0}))
        response = rerank(client, question, candidates, limit=top_k)
        response['reranking']['cached'] = False
        if response['reranking']['status'] == 'applied':
            with self.lock:
                self.reranking_cache[cache_key] = deepcopy(response)
                if len(self.reranking_cache) > 32:
                    self.reranking_cache.popitem(last=False)
        return response

    def search(self, dossier_id, question, top_k):
        return self.search_analysis(dossier_id, question, top_k)['results']

    def source(self, dossier_id, document_id):
        with Catalog(self.catalog_path, read_only=True) as catalog:
            doc = catalog.get_document(dossier_id, document_id)
        if doc is None:
            raise FileNotFoundError('Document absent de ce dossier.')
        path = Path(doc.source_path).resolve()
        if not (path.is_relative_to(ROOT / 'data') or path.is_relative_to(self.data_path)):
            raise ValueError('Source non autorisée.')
        if doc.source_kind == 'pdf':
            job = self.jobs.documents(dossier_id).get(document_id)
            if not job or path != self.data_path / (document_id + '.pdf'):
                raise FileNotFoundError('PDF indisponible.')
            return dict(kind='pdf', path=path, name=job['filename'])
        if path.suffix == '.json':
            from data_loader import load_field_records
            records = load_field_records(path)
            record = next((r for r in records if r.document_id == document_id and doc.source_locator == f'id={r.id}'), None)
            if record is None:
                raise ValueError('Référence JSON introuvable.')
            return dict(kind='text', text=record.value, name=f'{record.field_label} · {document_id}')
        return dict(kind='text', text=path.read_text(encoding='utf-8'), name=document_id)
