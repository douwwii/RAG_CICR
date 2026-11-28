"""OCR simulé : reprise, absence de publication prématurée et provenance."""
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from config import OllamaConfig
from ocr import transcribe, save, sidecar, extracted
import test_web
from test_web import pdf_bytes

class FakeInkling:
    config = OllamaConfig(model_name='inkling-test')
    def __init__(self, fail=None):
        self.calls = 0
        self.fail = fail
    def installed_models(self):
        return {'inkling-test': 'sha256-test'}
    def _request(self, path, payload):
        self.calls += 1
        if self.calls == self.fail:
            raise TimeoutError()
        page = payload['messages'][1]['content']
        return dict(done=True, done_reason='stop', message=dict(content=json.dumps(dict(
            transcription='Lina au hangar. ' + page, observations='Description non indexable.'))))

class OCRTests(unittest.TestCase):
    def test_checkpoint_resume_and_approved_pages(self):
        with tempfile.TemporaryDirectory() as directory:
            pdf = Path(directory) / 'scan.pdf'
            pdf.write_bytes(pdf_bytes('one','two','three'))
            save(sidecar(pdf), dict(pages=[], revisions=[], approved=None))
            failing = FakeInkling(fail=2)
            with self.assertRaises(TimeoutError):
                transcribe(pdf, lambda _: None, transport=failing, renderer=lambda *_: b'image')
            self.assertEqual(len(json.loads(sidecar(pdf).read_text())['pages']), 1)
            resumed = FakeInkling()
            state = transcribe(pdf, lambda _: None, transport=resumed, renderer=lambda *_: b'image')
            self.assertEqual(resumed.calls, 2)
            with self.assertRaises(ValueError): extracted(pdf)
            state['approved'] = state['pages']; save(sidecar(pdf), state)
            result = extracted(pdf)
            self.assertEqual(result.page_range(result.pages[2].start, result.pages[2].end), (3, 3))
            self.assertNotIn('Description', result.text)
            state['retry_page'] = 2; state['approved'] = None; save(sidecar(pdf), state)
            before = resumed.calls
            state = transcribe(pdf, lambda _: None, transport=resumed, renderer=lambda *_: b'image')
            self.assertEqual(resumed.calls - before, 1)
            self.assertEqual(len(state['pages']), 3)
            self.assertEqual(len(state['revisions']), 1)

    def test_truncated_output_never_checkpoints_or_publishes(self):
        with tempfile.TemporaryDirectory() as directory:
            pdf = Path(directory) / 'scan.pdf'; pdf.write_bytes(pdf_bytes('one'))
            save(sidecar(pdf), dict(pages=[], revisions=[], approved=None))
            llm = FakeInkling()
            with patch.object(llm, '_request', return_value={'done': True, 'done_reason': 'length'}):
                with self.assertRaises(ValueError):
                    transcribe(pdf, lambda _: None, transport=llm, renderer=lambda *_: b'image')
            self.assertEqual(json.loads(sidecar(pdf).read_text())['pages'], [])


class OCRWebTests(unittest.TestCase):
    setUp = test_web.WebTests.setUp
    tearDown = test_web.WebTests.tearDown
    wait = test_web.WebTests.wait
    def test_review_edit_publish_and_scope(self):
        real = transcribe
        def fake(pdf, progress):
            return real(pdf, progress, transport=FakeInkling(), renderer=lambda *_: b'image')
        with patch('ocr.transcribe', fake):
            refused=self.client.post('/api/dossiers/A/ocr-imports',files={'file':('scan.pdf',pdf_bytes('one'),'application/pdf')})
            self.assertEqual(refused.status_code,400)
            self.assertEqual(self.client.get('/api/dossiers/A/documents').json(),[])
            response = self.client.post('/api/dossiers/__ocr_workspace__/ocr-imports', files={
                'file': ('scan.pdf', pdf_bytes('one', 'two'), 'application/pdf')})
            self.assertEqual(response.status_code, 202)
            job = response.json()['job']; doc = job['document_id']
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                current = self.service.jobs.get(job['job_id'])
                if current['status'] in {'review', 'error'}: break
                time.sleep(.01)
            self.assertEqual(current['status'], 'review')
            self.assertEqual(self.service.retrieve_candidates('A', 'Lina'), [])
            route = f'/api/dossiers/__ocr_workspace__/documents/{doc}/ocr'
            self.assertEqual(self.client.get(route.replace('/__ocr_workspace__/', '/B/')).status_code, 404)
            state = self.client.get(route).json()
            texts = [p['transcription'] for p in state['pages']]
            self.assertEqual(self.client.put(route, json={'pages':texts, 'publish':True}).status_code, 400)
            self.assertEqual(self.client.get('/api/dossiers/A/documents').json(),[])
            self.assertNotIn('__ocr_workspace__',[d['dossier_id'] for d in self.client.get('/api/dossiers').json()])
            self.assertEqual(self.client.put(route, json={'pages':texts, 'publish':True,'destination':'A'}).status_code, 200)
            route=f'/api/dossiers/A/documents/{doc}/ocr'
            self.assertEqual(self.wait(job)['status'], 'done')
            artifact = self.service.artifact('A', doc)
            self.assertEqual(artifact['extraction_kind'], 'ocr')
            self.assertNotIn('Description', artifact['text'])
            texts[0] = 'Texte corrigé.'
            self.assertEqual(self.client.put(route, json={'pages':texts}).status_code, 200)
            self.assertEqual(self.service.jobs.get(job['job_id'])['status'], 'review')
            self.assertEqual(self.service.retrieve_candidates('A', 'Lina'), [])
