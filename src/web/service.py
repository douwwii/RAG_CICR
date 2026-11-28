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

from qdrant_client import QdrantClient, models

from catalog import Catalog
from common import CATALOG_FILE, DATA_FILE
from config import ROOT, OllamaConfig
from ingestion import ingest_pdf
from ollama_client import OllamaClient
from passage_index import PassageIndex
from qdrant_store import QdrantVectorStore
from schemas import DocumentMetadata
from search import retrieve
from lexical_search import rank_lexical, fuse_ranks
from vector_store import VectorRecord
from scope import validate_field_reference
from passage_index import IndexedPassage
from query_rewriting import rewrite_question
from reranking import rerank, cache_key as reranking_key
from web.jobs import JobRepository
from web.index_config import WebIndexConfig, create_embedder

OCR_WORKSPACE = '__ocr_workspace__'

log = logging.getLogger(__name__)


from web.management import Management


class WebService(Management):
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
        from schemas import Dossier
        with Catalog(self.catalog_path) as catalog:
            catalog.register(dossiers=[Dossier(dossier_id=OCR_WORKSPACE, title='OCR — préparation')])
        self.recover_move()
        self.recover_delete()
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
            return [dict(d.model_dump(), archived=d.dossier_id in self.jobs.archived()) for d in catalog.list_dossiers() if d.dossier_id != OCR_WORKSPACE]

    def require_dossier(self, dossier_id):
        if dossier_id in self.jobs.archived():
            raise ValueError('Ce dossier est archivé. Restaurez-le pour continuer.')
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
                         has_pdf=d.source_kind == 'pdf' and d.document_id in jobs,
                         ocr=d.source_kind == 'pdf' and Path(d.source_path).with_suffix('.ocr.json').exists())
                    for d in documents]

    def submit(self, dossier_id, filename, content, *, ocr=False):
        if ocr and dossier_id != OCR_WORKSPACE:
            raise ValueError('Lancez la transcription depuis l’espace OCR indépendant.')
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
            from ocr import sidecar, save
            ocr_path = sidecar(Path(source.source_path))
            if ocr and not ocr_path.exists():
                save(ocr_path, dict(pages=[], revisions=[], approved=None))
            needs_ocr = ocr_path.exists() and (ocr or not json.loads(ocr_path.read_text()).get('approved'))
            worker = self.process_ocr if needs_ocr else self.process
            self.executor.submit(worker, job_id, source)
            return dict(job=self.jobs.public(self.jobs.get(job_id)), duplicate=False)

    def process_ocr(self, job_id, source):
        from ocr import transcribe
        try:
            state = transcribe(Path(source.source_path), lambda stage:
                self.jobs.update(job_id, status='running', stage=stage))
            self.jobs.update(job_id, status='review', stage='OCR à vérifier',
                             page_count=state['page_count'], error=None)
        except Exception:
            log.warning('Échec OCR %s', job_id)
            self.jobs.update(job_id, status='error', stage='Erreur OCR',
                error='OCR interrompu. Vérifiez Inkling, le tunnel et Poppler puis réessayez.')

    def ocr_state(self, dossier_id, document_id):
        from ocr import sidecar
        source = self.source(dossier_id, document_id)
        return json.loads(sidecar(source['path']).read_text(encoding='utf-8'))

    def edit_ocr(self, dossier_id, document_id, pages=None, *, publish=False, retry=False, retry_page=None, destination=None):
        from ocr import sidecar, save
        self.require_dossier(dossier_id)
        if publish:
            if not destination or destination == OCR_WORKSPACE:
                raise ValueError('Choisissez explicitement un dossier de destination.')
            self.require_dossier(destination)
        if (publish and retry) or (retry_page is not None and not retry):
            raise ValueError('Actions OCR incompatibles.')
        if pages is not None and sum(map(len, pages)) > 2_000_000:
            raise ValueError('Transcription trop longue.')
        with self.lock:
            job = self.jobs.documents(dossier_id).get(document_id)
            if not job or job['status'] in {'queued', 'running'}:
                raise ValueError('Document indisponible ou occupé.')
            path = Path(self.source(dossier_id, document_id)['path'])
            state = self.ocr_state(dossier_id, document_id)
            if retry:
                # Ne jamais remplacer une version déjà indexée par une reprise partielle.
                if job['status'] == 'done':
                    raise ValueError('Document déjà indexé.')
                if retry_page is not None and not 1 <= retry_page <= len(state['pages']):
                    raise ValueError('Page OCR inconnue.')
                if retry_page is not None:
                    state['retry_page'] = retry_page
                state['approved'] = None
            else:
                if len(state['pages']) != state['page_count']:
                    raise ValueError('OCR incomplet.')
                if pages is not None:
                    if len(pages) != len(state['pages']):
                        raise ValueError('Nombre de pages incorrect.')
                    state['revisions'].append([p['transcription'] for p in state['pages']])
                    for page, text in zip(state['pages'], pages):
                        page['transcription'] = text
                state['approved'] = state['pages'] if publish else None
                if publish and not any(p['transcription'].strip() for p in state['pages']):
                    raise ValueError('Transcription vide.')
            if publish and dossier_id != destination:
                self.move_document(dossier_id, document_id, destination)
                dossier_id = destination
            save(sidecar(path), state)
            self.jobs.update(job['job_id'], status='queued' if publish or retry else 'review',
                             stage='En attente' if publish or retry else 'OCR à vérifier', error=None)
            if publish or retry:
                with Catalog(self.catalog_path, read_only=True) as catalog:
                    source = catalog.get_document(dossier_id, document_id)
                self.executor.submit(self.process_ocr if retry else self.process, job['job_id'], source)
        return {'ok': True, 'dossier_id': dossier_id}

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
                        from qdrant_client import models
                        if self.client.collection_exists(self.passages.collection):
                            self.client.delete(self.passages.collection, points_selector=models.FilterSelector(
                                filter=models.Filter(must=[models.FieldCondition(key='document_id',
                                    match=models.MatchValue(value=source.document_id))])), wait=True)
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

    def _scoped_points(self, collection, dossier_id, document_ids):
        if not document_ids or not self.client.collection_exists(collection):
            return
        offset = None
        scope = models.Filter(must=[
            models.FieldCondition(key='dossier_id', match=models.MatchValue(value=dossier_id)),
            models.FieldCondition(key='document_id', match=models.MatchAny(any=list(document_ids))),
        ])
        while True:
            points, offset = self.client.scroll(collection, scroll_filter=scope, limit=256,
                                                offset=offset, with_payload=True, with_vectors=False)
            yield from points
            if offset is None:
                break

    def _pdf_candidate(self, p, score, dossier_id, documents, ready):
        if p.dossier_id != dossier_id or p.document_id not in documents or p.document_id not in ready:
            raise ValueError('Source absente du dossier ou non publiée.')
        artifact = self.artifact(dossier_id, p.document_id)
        saved = next((item for item in artifact['passages'] if item['passage_id'] == p.passage_id), None)
        if saved != p.model_dump() or artifact['text'][p.start:p.end] != p.text:
            raise ValueError('Le passage ne correspond plus au texte source.')
        return dict(passage_id=p.passage_id, parent_id=p.parent_id,
                    document_id=p.document_id, dossier_id=dossier_id, title=p.title,
                    text=p.text, score=score, page_start=p.page_start, page_end=p.page_end,
                    name=ready[p.document_id]['filename'], kind='pdf')

    @staticmethod
    def _field_candidate(p, score, dossier_id, persons):
        return dict(passage_id=str(p.id), document_id=p.document_id,
                    dossier_id=dossier_id, title=p.field_label, text=p.value,
                    score=score, page_start=None, page_end=None,
                    name=f'{p.field_label} · {persons.get(p.person_id, p.person_id)}', kind=p.source_kind)

    def retrieve_candidates(self, dossier_id, question, candidate_k=30, *, mode='semantic', document_ids=None):
        self.require_dossier(dossier_id)
        if mode not in {'semantic', 'hybrid', 'exact'}:
            raise ValueError('Mode de recherche inconnu.')
        if not 1 <= candidate_k <= 30:
            raise ValueError('Entre 1 et 30 candidats sont requis.')
        original = question
        # La requête lexicale conserve toujours les termes originaux.
        if mode != 'exact':
            with self.lock:
                embedder = self.encoder()
            client = self.llm
            if isinstance(client, OllamaClient):
                client = OllamaClient(client.config.model_copy(update={'num_predict': 512, 'timeout_seconds': 45.0}))
            question = rewrite_question(client, question, embedder, validation_lock=self.lock)
        with self.lock, Catalog(self.catalog_path, read_only=True) as catalog:
            documents = {d.document_id: d for d in catalog.list_documents(dossier_id)}
            if document_ids is not None:
                if not set(document_ids) <= documents.keys():
                    raise ValueError('Document absent du dossier sélectionné.')
                documents = {k: d for k, d in documents.items() if k in document_ids}
            if not documents:
                return []
            persons = {p.person_id: p.display_name for p in catalog.list_persons(dossier_id)}
            ready = {k: j for k, j in self.jobs.documents(dossier_id).items()
                     if k in documents and j['status'] == 'done' and (self.artifact_path / (k + '.json')).exists()}
            dense = []
            if mode != 'exact':
                if self.client.collection_exists(self.index_config.fields.collection_name):
                    for hit in retrieve(self.legacy, embedder, question, catalog=catalog,
                                        dossier_id=dossier_id, top_k=candidate_k, document_ids=list(documents),
                                        text_builder_version=self.index_config.text_builder_version):
                        dense.append(self._field_candidate(hit.payload, hit.score, dossier_id, persons))
                vector = embedder.embed_query(question)
                for p, score in self.passages.search(vector, embedder, dossier_id, list(ready), candidate_k):
                    dense.append(self._pdf_candidate(p, score, dossier_id, documents, ready))
                dense = sorted(dense, key=lambda r: r['score'], reverse=True)[:candidate_k]
            if mode == 'semantic':
                return dense
            lexical, records = [], {}
            for point in self._scoped_points(self.index_config.fields.collection_name, dossier_id, documents):
                p = VectorRecord.model_validate(point.payload)
                if str(point.id) != str(p.id) or p.dossier_id != dossier_id or p.document_id not in documents:
                    raise ValueError('Champ hors périmètre ou identifiant incohérent.')
                validate_field_reference(p, documents[p.document_id], source_path=p.source_path, source_locator=p.source_locator)
                candidate = self._field_candidate(p, 0., dossier_id, persons)
                lexical.append(candidate)
            for point in self._scoped_points(self.passages.collection, dossier_id, ready):
                p = IndexedPassage.model_validate(point.payload)
                if str(point.id) != p.passage_id or p.dossier_id != dossier_id or p.document_id not in ready:
                    raise ValueError('Passage hors périmètre ou identifiant incohérent.')
                records[p.passage_id] = p
                lexical.append(dict(passage_id=p.passage_id, document_id=p.document_id, title=p.title,
                                    text=p.text, name=ready[p.document_id]['filename']))
            lexical = rank_lexical(original, lexical, candidate_k, exact=mode == 'exact')
            # Seuls les passages retenus nécessitent la relecture des artefacts.
            for i, candidate in enumerate(lexical):
                p = records.get(candidate['passage_id'])
                if p is not None:
                    lexical[i] = dict(self._pdf_candidate(p, candidate['score'], dossier_id, documents, ready),
                                      score_kind='lexical', exact_match=candidate['exact_match'])
            return lexical if mode == 'exact' else fuse_ranks(dense, lexical, candidate_k)

    def search_analysis(self, dossier_id, question, top_k=5, *, candidate_k=None, mode='semantic', document_ids=None):
        if not 1 <= top_k <= 5:
            raise ValueError('Entre 1 et 5 résultats sont requis.')
        options = {} if mode == 'semantic' and document_ids is None else dict(mode=mode, document_ids=document_ids)
        candidates = self.retrieve_candidates(dossier_id, question, candidate_k or self.rerank_candidates, **options)
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
                response['retrieval'] = dict(mode=mode, document_ids=document_ids)
                return response
        client = self.llm
        if isinstance(client, OllamaClient):
            client = OllamaClient(client.config.model_copy(update={'num_predict': 2048, 'timeout_seconds': 90.0}))
        response = rerank(client, question, candidates, limit=top_k)
        response['reranking']['cached'] = False
        response['retrieval'] = dict(mode=mode, document_ids=document_ids)
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
