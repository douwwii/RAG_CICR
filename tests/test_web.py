"""Intégration HTTP réelle avec SQLite/Qdrant temporaires ; modèles simulés explicitement."""
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

from fastapi.testclient import TestClient
from qdrant_client import QdrantClient
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from catalog import Catalog
from pdf_extraction import extract_pdf
from schemas import Dossier
from segmentation_schemas import Generation
from unittest.mock import patch
from segmentation_validation import validate_source_alignment, SegmentationValidationError
from web.app import create_app
from web.service import WebService
from test_embeddings import FakeModel, make_embedder


def pdf_bytes(*pages):
    output = BytesIO()
    pdf = canvas.Canvas(output, invariant=1)
    for text in pages:
        pdf.drawString(50, 780, text)
        pdf.showPage()
    pdf.save()
    return output.getvalue()


class TestModel(FakeModel):
    def tokenizer(self, texts, **kwargs):
        def ids(text):
            return [0] * (len(text.split()) + 2)
        return {'input_ids': ids(texts) if isinstance(texts, str) else [ids(t) for t in texts]}


class ExactLLM:
    def generate(self, system_prompt, text, schema):
        return Generation(content=json.dumps({'passages': [{'title': 'Information du document', 'text': text.strip()}]}))


class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.catalog = self.root / 'catalog.sqlite'
        with Catalog(self.catalog) as catalog:
            catalog.initialize()
            catalog.register(dossiers=[Dossier(dossier_id='A', title='Dossier A'), Dossier(dossier_id='B', title='Dossier B')])
        self.encoder, _ = make_embedder(model=TestModel())
        self.service = WebService(catalog_path=self.catalog, data_path=self.root / 'files',
                                  embedder=self.encoder, llm=ExactLLM(), qdrant=QdrantClient(':memory:'))
        self.client_context = TestClient(create_app(lambda: self.service))
        self.client = self.client_context.__enter__()

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        self.temp.cleanup()

    def upload(self, dossier='A', content=None):
        return self.client.post(f'/api/dossiers/{dossier}/imports', files={'file': ('rapport.pdf', content or pdf_bytes('Lina a ete vue pres du hangar.'), 'application/pdf')})

    def wait(self, job):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            job = self.client.get('/api/jobs/' + job['job_id']).json()
            if job['status'] in {'done', 'error'}:
                return job
            time.sleep(.02)
        self.fail('Import non terminé dans le délai de test.')

    def test_move_person_references_and_rollback_do_not_leak_associations(self):
        from schemas import Person, DocumentMetadata
        job=self.wait(self.upload().json()['job'])
        text=self.service.data_path/'note.txt';text.write_text('Note sur une personne.')
        with Catalog(self.catalog) as catalog:
            catalog.register(persons=[Person(person_id='P-X',display_name='Personne test')])
            catalog._connection.execute('INSERT INTO dossier_persons VALUES (?,?)',('A','P-X'))
            catalog.register(documents=[DocumentMetadata(document_id='NOTE',dossier_id='A',source_kind='txt',source_path=str(text),person_ids=['P-X'])])
        original=self.service.client.set_payload
        calls=[]
        def fail_once(*args,**kwargs):
            calls.append(1)
            if len(calls)==1:raise ValueError('Panne simulée')
            return original(*args,**kwargs)
        with patch.object(self.service.client,'set_payload',side_effect=fail_once):
            self.assertEqual(self.client.post('/api/dossiers/A/documents/NOTE/move',json={'destination':'B'}).status_code,400)
        with Catalog(self.catalog,read_only=True) as catalog:
            self.assertEqual(catalog.list_persons('B'),[])
            self.assertEqual(catalog.get_document('A','NOTE').person_ids,['P-X'])
        self.assertEqual(self.client.post('/api/dossiers/A/documents/NOTE/move',json={'destination':'B'}).status_code,200)
        with Catalog(self.catalog,read_only=True) as catalog:
            self.assertEqual(catalog.get_document('B','NOTE').person_ids,['P-X'])
            self.assertEqual(catalog.list_persons('B')[0].person_id,'P-X')

    def test_delete_document_requires_confirmation_and_removes_search_and_files(self):
        job=self.wait(self.upload().json()['job']);doc=job['document_id']
        url=f'/api/dossiers/A/documents/{doc}'
        self.assertEqual(self.client.delete(url).status_code,400)
        self.assertEqual(self.client.get(url+'/file').status_code,200)
        self.assertEqual(self.client.delete(f'/api/dossiers/B/documents/{doc}?confirmed=true').status_code,404)
        self.assertEqual(self.client.delete(url+'?confirmed=true').status_code,200)
        self.assertEqual(self.client.get(url+'/file').status_code,404)
        self.assertFalse((self.service.data_path/(doc+'.pdf')).exists())
        self.assertFalse((self.service.artifact_path/(doc+'.json')).exists())
        self.assertEqual(self.client.post('/api/dossiers/A/search',json={'question':'Lina'}).json()['results'],[])
        self.assertIsNone(self.service.jobs.get(job['job_id']))
        self.assertEqual(self.client.get('/api/dossiers/A/documents').status_code,200)

    def test_delete_dossier_includes_documents_and_rejects_busy_import(self):
        job=self.wait(self.upload().json()['job']);doc=job['document_id']
        self.assertEqual(self.client.delete('/api/dossiers/A').status_code,400)
        self.service.jobs.update(job['job_id'],status='running')
        response=self.client.delete('/api/dossiers/A?confirmed=true')
        self.assertEqual(response.status_code,409)
        self.assertIn('traitement de document',response.json()['detail'])
        self.service.jobs.update(job['job_id'],status='done')
        self.assertEqual(self.client.delete('/api/dossiers/A?confirmed=true').status_code,200)
        self.assertEqual(self.client.get('/api/dossiers/A/documents').status_code,404)
        self.assertEqual(self.client.get('/api/dossiers/B/documents').status_code,200)
        self.assertFalse((self.service.data_path/(doc+'.pdf')).exists())

    def test_delete_interruption_can_be_recovered(self):
        job=self.wait(self.upload().json()['job']);doc=job['document_id']
        with patch.object(self.service.client,'delete',side_effect=ValueError('Panne simulée')):
            self.assertEqual(self.client.delete(f'/api/dossiers/A/documents/{doc}?confirmed=true').status_code,400)
        self.assertTrue((self.service.data_path/'document-delete.json').exists())
        self.service.recover_delete()
        self.assertFalse((self.service.data_path/'document-delete.json').exists())
        self.assertEqual(self.client.get(f'/api/dossiers/A/documents/{doc}/file').status_code,404)

    def test_retry_import_uses_original_pdf_without_upload(self):
        job=self.wait(self.upload().json()['job']);self.service.jobs.update(job['job_id'],status='error')
        doc=job['document_id']
        response=self.client.post(f'/api/dossiers/A/documents/{doc}/retry')
        self.assertEqual(response.status_code,202)
        self.assertEqual(response.json()['job']['document_id'],doc)
        self.assertEqual(self.wait(response.json()['job'])['status'],'done')
        self.assertEqual(self.client.post(f'/api/dossiers/B/documents/{doc}/retry').status_code,404)

    def test_manage_dossiers_create_rename_archive_restore(self):
        for title in ['', '  ', 'x'*161]:
            self.assertEqual(self.client.post('/api/dossiers', json={'title':title}).status_code, 422)
        response = self.client.post('/api/dossiers', json={'title':' Nouvelle enquête '})
        self.assertEqual(response.status_code,201)
        dossier = response.json()['dossier_id']
        self.assertEqual(response.json()['title'],'Nouvelle enquête')
        self.assertEqual(self.client.patch('/api/dossiers/'+dossier,json={'title':'Renommé'}).status_code,200)
        self.assertEqual(self.client.patch('/api/dossiers/'+dossier,json={'archived':True}).status_code,200)
        row=next(d for d in self.client.get('/api/dossiers').json() if d['dossier_id']==dossier)
        self.assertEqual(row['title'],'Renommé');self.assertTrue(row['archived'])
        self.assertEqual(self.client.post('/api/dossiers/'+dossier+'/search',json={'question':'Où ?'}).status_code,400)
        self.assertEqual(self.client.patch('/api/dossiers/'+dossier,json={'archived':False}).status_code,200)
        self.assertEqual(self.client.post('/api/dossiers/'+dossier+'/search',json={'question':'Où ?'}).status_code,200)

    def test_move_pdf_updates_index_source_jobs_and_duplicate_detection(self):
        content=pdf_bytes('Lina reste au centre. Son identite est incertaine.')
        job=self.wait(self.upload(content=content).json()['job']);self.assertEqual(job['status'],'done')
        doc=job['document_id'];path=f'/api/dossiers/A/documents/{doc}/move'
        self.assertEqual(self.client.post(path,json={'destination':'B'}).status_code,200)
        self.assertEqual(self.client.get(f'/api/dossiers/A/documents/{doc}/file').status_code,404)
        self.assertEqual(self.client.get(f'/api/dossiers/B/documents/{doc}/file').content,content)
        self.assertEqual(self.client.post('/api/dossiers/A/search',json={'question':'Lina'}).json()['results'],[])
        hits=self.client.post('/api/dossiers/B/search',json={'question':'Lina'}).json()['results']
        self.assertTrue(hits);self.assertTrue(all(h['dossier_id']=='B' for h in hits))
        self.assertTrue(self.upload(dossier='B',content=content).json()['duplicate'])
        self.assertEqual(self.service.artifact('B',doc)['segmentation']['document']['source']['dossier_id'],'B')
        self.assertFalse((self.service.data_path/'document-move.json').exists())
        self.assertEqual(self.client.post(path,json={'destination':'B'}).status_code,404)

    def test_move_failure_restores_original_scope(self):
        job=self.wait(self.upload().json()['job']);doc=job['document_id']
        original=self.service.client.set_payload
        calls=[]
        def fail_once(*args,**kwargs):
            calls.append(1)
            if len(calls)==1:raise ValueError('Panne simulée')
            return original(*args,**kwargs)
        with patch.object(self.service.client,'set_payload',side_effect=fail_once):
            self.assertEqual(self.client.post(f'/api/dossiers/A/documents/{doc}/move',json={'destination':'B'}).status_code,400)
        self.assertEqual(self.client.get(f'/api/dossiers/A/documents/{doc}/file').status_code,200)
        self.assertEqual(self.service.artifact('A',doc)['passages'][0]['dossier_id'],'A')
        self.assertFalse((self.service.data_path/'document-move.json').exists())

    def test_recover_interrupted_move_and_forbid_busy_move(self):
        job=self.wait(self.upload().json()['job']);doc=job['document_id']
        self.service.jobs.update(job['job_id'],status='running')
        self.assertEqual(self.client.post(f'/api/dossiers/A/documents/{doc}/move',json={'destination':'B'}).status_code,400)
        self.assertEqual(self.client.patch('/api/dossiers/A',json={'archived':True}).status_code,400)
        self.service.jobs.update(job['job_id'],status='done')
        artifact=self.service.artifact('A',doc)
        journal=self.service.data_path/'document-move.json'
        journal.write_text(json.dumps(dict(document_id=doc,origin='A',artifact=artifact)))
        self.service._set_document_scope(doc,'B',artifact)
        self.service.recover_move()
        self.assertEqual(self.client.get(f'/api/dossiers/A/documents/{doc}/file').status_code,200)
        self.assertEqual(self.service.artifact('A',doc)['passages'][0]['dossier_id'],'A')

    def test_import_search_source_duplicate_and_dossier_isolation(self):
        data = pdf_bytes('Lina a ete vue pres du hangar.', 'Son identite reste incertaine.')
        response = self.upload(content=data)
        self.assertEqual(response.status_code, 202, response.text)
        job = self.wait(response.json()['job'])
        self.assertEqual(job['status'], 'done', job)
        self.assertEqual(job['page_count'], 2)
        document_id = job['document_id']
        hits = self.client.post('/api/dossiers/A/search', json={'question': 'Ou est Lina ?'}).json()['results']
        self.assertTrue(hits)
        self.assertTrue(all(h['dossier_id'] == 'A' and h['document_id'] == document_id for h in hits))
        artifact = self.service.artifact('A', document_id)
        for hit in hits:
            saved = next(p for p in artifact['passages'] if p['passage_id'] == hit['passage_id'])
            self.assertEqual(hit['text'], artifact['text'][saved['start']:saved['end']])
        self.assertEqual(self.client.post('/api/dossiers/B/search', json={'question': 'Lina'}).json()['results'], [])
        self.assertEqual(self.client.get(f'/api/dossiers/B/documents/{document_id}/file').status_code, 404)
        source = self.client.get(f'/api/dossiers/A/documents/{document_id}/file')
        self.assertEqual(source.content, data)
        self.assertEqual(source.headers['content-type'], 'application/pdf')
        duplicate = self.upload(content=data)
        self.assertTrue(duplicate.json()['duplicate'])
        self.assertEqual(duplicate.json()['job']['document_id'], document_id)
        # Le même PDF dans un autre dossier reçoit sa propre référence, jamais un rattachement implicite.
        other = self.wait(self.upload('B', data).json()['job'])
        self.assertEqual(other['status'], 'done')
        self.assertNotEqual(other['document_id'], document_id)
        self.assertNotIn(str(self.root), json.dumps(self.client.get('/api/dossiers/A/documents').json()))

    def test_exact_and_hybrid_use_original_terms_and_document_scope(self):
        from test_reranking import proposal
        first = self.wait(self.upload(content=pdf_bytes('Elodie Martin reference AB-2026/0012.')).json()['job'])
        second = self.wait(self.upload(content=pdf_bytes('Un autre temoignage sur le hangar.')).json()['job'])
        foreign = self.wait(self.upload('B', pdf_bytes('Elodie Martin reference AB-2026/0012.')).json()['job'])
        selected = first['document_id']
        with patch('web.service.rewrite_question') as rewrite, patch.object(self.service, 'encoder') as encoder:
            hits = self.service.retrieve_candidates('A', 'AB-2026/0012', mode='exact')
            self.assertEqual({c['document_id'] for c in hits}, {selected})
            rewrite.assert_not_called()
            encoder.assert_not_called()
        with patch('web.service.rewrite_question', return_value='Le hangar') as rewrite:
            hits = self.service.retrieve_candidates('A', 'AB-2026/0012', mode='hybrid', candidate_k=2)
            self.assertIn(selected, {c['document_id'] for c in hits})
            self.assertTrue(all(c['score_kind'] == 'rrf' for c in hits))
        self.assertEqual(self.service.retrieve_candidates('A', 'AB-2026/0012', mode='exact',
                                                         document_ids=[second['document_id']]), [])
        self.assertEqual(self.service.retrieve_candidates('A', 'AB-2026/0012', mode='exact', document_ids=[]), [])
        for mode in ('semantic', 'hybrid', 'exact'):
            with self.subTest(mode=mode):
                source = self.service.retrieve_candidates('A', 'hangar', mode=mode, document_ids=[second['document_id']])
                self.assertEqual({c['document_id'] for c in source}, {second['document_id']})
                bad = self.client.post('/api/dossiers/A/search', json=dict(question='AB-2026/0012',
                                       mode=mode, document_ids=[foreign['document_id']]))
                self.assertEqual(bad.status_code, 400)
        # Qwen reçoit uniquement les candidats lexicaux vérifiés et la question originale.
        def generate(system, text, schema):
            payload = json.loads(text)
            self.assertEqual(payload['question'], 'AB-2026/0012')
            self.assertEqual(len(payload['candidates']), 1)
            return Generation(content=json.dumps(proposal(payload['candidates'])))
        with patch.object(self.service.llm, 'generate', side_effect=generate):
            response = self.client.post('/api/dossiers/A/search', json=dict(question='AB-2026/0012', mode='exact'))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['retrieval']['mode'], 'exact')
        self.assertEqual(response.json()['reranking']['status'], 'applied')
        self.assertEqual(self.client.post('/api/dossiers/A/search', json=dict(question='a', mode='other')).status_code, 422)

    def test_lexical_fields_preserve_person_context_and_scope(self):
        from test_vector_store import make_record
        from schemas import Person, DocumentMetadata
        record = make_record().model_copy(update={'dossier_id': 'C', 'value': 'Reference ZX-0012', 'embedding_text': 'Reference ZX-0012'})
        with Catalog(self.catalog) as catalog:
            catalog.register(dossiers=[Dossier(dossier_id='C', title='Dossier C', person_ids=[record.person_id])],
                             persons=[Person(person_id=record.person_id, display_name='Élodie Martin')],
                             documents=[DocumentMetadata(document_id=record.document_id, dossier_id='C',
                                        source_kind=record.source_kind, source_path=record.source_path,
                                        source_locator=record.source_locator, person_ids=[record.person_id])])
        self.service.legacy.rebuild([record], self.encoder.embed_documents([record.embedding_text]),
                                   profile=self.encoder.profile,
                                   text_builder_version=self.service.index_config.text_builder_version)
        for question in ('ZX-0012', 'ELODIE MARTIN', record.document_id):
            hits = self.service.retrieve_candidates('C', question, mode='exact')
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0]['text'], record.value)
            self.assertEqual(hits[0]['passage_id'], str(record.id))
        self.assertEqual(self.service.retrieve_candidates('B', 'ZX-0012', mode='exact'), [])
        # Le filtre s'applique également au stockage dense avant sa limite.
        hits = self.service.retrieve_candidates('C', 'Reference', mode='hybrid', document_ids=[record.document_id])
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]['score_kind'], 'rrf')

    def test_lexical_excludes_unpublished_and_checks_source_before_reranking(self):
        job = self.wait(self.upload(content=pdf_bytes('Reference AB-0012.')).json()['job'])
        path = self.service.artifact_path / (job['document_id'] + '.json')
        artifact = json.loads(path.read_text())
        artifact['text'] = 'Texte remplace.'
        path.write_text(json.dumps(artifact))
        with patch.object(self.service.llm, 'generate') as generate:
            with self.assertRaisesRegex(ValueError, 'texte source'):
                self.service.search_analysis('A', 'AB-0012', mode='exact')
            generate.assert_not_called()
        path.unlink()
        self.assertEqual(self.service.retrieve_candidates('A', 'AB-0012', mode='exact'), [])
        self.service.jobs.update(job['job_id'], status='review')
        path.write_text(json.dumps(artifact))
        self.assertEqual(self.service.retrieve_candidates('A', 'AB-0012', mode='exact'), [])

    def test_http_returns_qwen_ranking_and_assessment(self):
        from test_reranking import candidates, proposal
        from reranking import PROMPT
        source=candidates()
        for item in source:item['dossier_id']='A'
        chosen=list(reversed(source[-5:]))
        self.service.llm.generate=lambda system,text,schema: Generation(content=json.dumps(proposal(chosen)))
        with patch.object(self.service,'retrieve_candidates',return_value=source) as retrieve:
            response=self.client.post('/api/dossiers/A/search',json={'question':'Question originale ?'})
        self.assertEqual(response.status_code,200,response.text)
        body=response.json()
        self.assertEqual(body['reranking']['status'],'applied')
        self.assertEqual(body['reranking']['candidate_count'],25)
        self.assertEqual(len(body['results']),5)
        self.assertEqual(body['results'][0]['passage_id'],'24')
        self.assertIsNotNone(body['assessment'])
        retrieve.assert_called_once_with('A','Question originale ?',self.service.rerank_candidates)

    def test_reranking_cache_requires_identical_verified_candidates(self):
        from test_reranking import candidates, proposal
        source=candidates()
        for item in source:item['dossier_id']='A'
        with patch.object(self.service,'retrieve_candidates',return_value=source), patch.object(self.service.llm,'generate',return_value=Generation(content=json.dumps(proposal(source[:5])))) as generate:
            first=self.service.search_analysis('A','Question ?')
            source[0]['score']-=.01
            second=self.service.search_analysis('A','Question ?')
            self.assertFalse(first['reranking']['cached'])
            self.assertTrue(second['reranking']['cached'])
            self.assertEqual(second['results'][0]['score'],source[0]['score'])
            self.assertEqual(generate.call_count,1)
            source[0]['text']+=' Source modifiée.'
            self.service.search_analysis('A','Question ?')
            self.assertEqual(generate.call_count,2)

    def test_upload_validation_and_no_text_pdf(self):
        bad = self.client.post('/api/dossiers/A/imports', files={'file': ('bad.pdf', b'not a pdf')})
        self.assertEqual(bad.status_code, 415)
        missing = self.upload('UNKNOWN')
        self.assertEqual(missing.status_code, 404)
        with self.assertLogs('web.service', level='ERROR'):
            blank = self.wait(self.upload(content=pdf_bytes('')).json()['job'])
        self.assertEqual(blank['status'], 'error')
        self.assertIn('sans texte', blank['error'])
        self.assertEqual(self.client.post('/api/dossiers/A/search', json={'question': 'Lina'}).json()['results'], [])
        self.assertEqual(self.client.post('/api/dossiers/A/search', json={'question': '  '}).status_code, 422)
        self.assertEqual(self.client.post('/api/dossiers/A/search', json={'question': 'x'}, headers={'Origin': 'https://example.org'}).status_code, 403)
        self.assertEqual(self.client.get('/api/dossiers/A/documents/..%2F..%2Fetc%2Fpasswd/file').status_code, 404)

    def test_interrupted_tasks_survive_restart_and_can_retry(self):
        self.service.jobs.create('interrupted', 'doc-unused', 'A', 'digest-unused', 'test.pdf')
        from web.jobs import JobRepository
        repository = JobRepository(self.service.jobs.path)
        self.assertEqual(repository.get('interrupted')['status'], 'error')

    def test_document_absent_from_active_generation_can_be_reimported(self):
        job = self.wait(self.upload().json()['job'])
        artifact = self.service.artifact_path / (job['document_id'] + '.json')
        artifact.rename(artifact.with_suffix('.backup'))
        document = self.client.get('/api/dossiers/A/documents').json()[0]
        self.assertEqual(document['status'], 'not_indexed')
        self.assertEqual(self.client.post('/api/dossiers/A/search', json={'question': 'Lina'}).json()['results'], [])
        retried = self.wait(self.upload().json()['job'])
        self.assertEqual(retried['document_id'], job['document_id'])
        self.assertEqual(retried['status'], 'done')

    def test_partial_index_never_becomes_searchable(self):
        add = self.service.passages.add
        def fail_after_write(passages, encoder):
            add(passages, encoder)
            raise ValueError('Publication interrompue.')
        with patch.object(self.service.passages, 'add', side_effect=fail_after_write):
            with self.assertLogs('web.service', level='ERROR'):
                job = self.wait(self.upload().json()['job'])
        self.assertEqual(job['status'], 'error')
        self.assertEqual(self.client.post('/api/dossiers/A/search', json={'question': 'Lina'}).json()['results'], [])
        retried = self.wait(self.upload().json()['job'])
        self.assertEqual(retried['job_id'], job['job_id'])
        self.assertEqual(retried['document_id'], job['document_id'])
        self.assertEqual(retried['status'], 'done')

    def test_persistent_passages_survive_service_restart(self):
        options = dict(catalog_path=self.catalog, data_path=self.root / 'persistent',
                       vector_path=self.root / 'vectors', embedder=self.encoder, llm=ExactLLM())
        service = WebService(**options)
        try:
            job = service.submit('A', 'persistant.pdf', pdf_bytes('Texte conserve apres redemarrage.'))['job']
            service.executor.shutdown(wait=True)
            self.assertEqual(service.jobs.get(job['job_id'])['status'], 'done')
        finally:
            service.close()
        service = WebService(**options)
        try:
            hits = service.search('A', 'Texte conserve', 5)
            self.assertTrue(hits)
            self.assertEqual(hits[0]['document_id'], job['document_id'])
            self.assertEqual(service.jobs.get(job['job_id'])['status'], 'done')
        finally:
            service.close()

    def test_invalid_segmentation_has_visible_exact_fallback(self):
        with patch.object(self.service.llm, 'generate', return_value=Generation(content='{"passages":[{"title":"Inventé","text":"Ce texte ne vient pas de la source."}]}')):
            job = self.wait(self.upload().json()['job'])
        self.assertEqual(job['status'], 'done')
        self.assertIn('indisponible', job['warning'])
        artifact = self.service.artifact('A', job['document_id'])
        self.assertEqual(artifact['segmentation']['document']['status'], 'fallback')
        for p in artifact['passages']:
            self.assertEqual(p['text'], artifact['text'][p['start']:p['end']])

    def test_page_provenance_and_token_splitting(self):
        path = self.root / 'pages.pdf'
        path.write_bytes(pdf_bytes('Premier temoignage.', 'Rectification de la date.'))
        extracted = extract_pdf(path)
        second = extracted.text.index('Rectification')
        self.assertEqual(extracted.page_range(second, len(extracted.text)), (2, 2))
        self.assertEqual(extracted.page_range(second - 2, len(extracted.text)), (2, 2))
        self.assertEqual(extracted.page_range(0, len(extracted.text)), (1, 2))
        text = ' '.join(['mot'] * 35)
        spans = self.encoder.document_spans(text)
        self.assertGreater(len(spans), 1)
        self.assertEqual(''.join(text[a:b] for a, b in spans), text)
        self.encoder.embed_documents([text[a:b] for a, b in spans])

    def test_source_alignment_restores_separators_but_never_rewrites(self):
        source = 'Titre\nTexte original.\n\nAutre sujet.\n'
        response = json.dumps({'passages': [{'title': 'Sujet', 'text': 'Titre\nTexte original.'}, {'title': 'Autre', 'text': 'Autre sujet.'}]})
        passages = validate_source_alignment(source, response)
        self.assertEqual(''.join(p.text for p in passages), source)
        for text in ['Texte inventé.', 'Titre\nTexte original.']:
            with self.assertRaises(SegmentationValidationError):
                validate_source_alignment(source, json.dumps({'passages': [{'title': 'Sujet', 'text': text}]}))


if __name__ == '__main__':
    unittest.main()
