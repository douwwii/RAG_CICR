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
