"""Conservation, chevauchement, reprise et ingestion PDF longue sans LLM distant."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from qdrant_client import QdrantClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from passage_index import PassageIndex
from long_segmentation import segment_long_document
from schemas import DocumentMetadata
from segmentation_schemas import Generation, GenerationError
from ingestion import ingest_pdf
from pdf_extraction import extract_pdf
from test_web import pdf_bytes, TestModel
from test_embeddings import make_embedder


class Client:
    def __init__(self, fail=None):
        self.inputs = []
        self.fail = fail

    def generate(self, prompt, text, schema):
        self.inputs.append(text)
        if len(self.inputs) == self.fail:
            raise GenerationError('connection', 'Coupure simulée')
        return Generation(content=json.dumps({'passages': [
            {'title': 'Sujet', 'text': line} for line in text.splitlines(keepends=True) if line]}))


class LongDocumentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = DocumentMetadata(document_id='LONG', dossier_id='A', source_kind='pdf', source_path='test.pdf')
        self.text = ''.join(f'Information {i} : identité incertaine, pas de confirmation.\n' for i in range(700))

    def run_document(self, client, text=None, prompt='Découper'):
        return segment_long_document(text or self.text, self.source, client, prompt=prompt,
            prompt_version='test', checkpoint_dir=self.root/'checkpoints', progress=lambda _: None)

    def assert_exact(self, run, text):
        self.assertEqual(''.join(p.text for p in run.document.passages), text)
        for p in run.document.passages:
            self.assertEqual(p.text, text[p.start:p.end])
        self.assertTrue(all(a.end == b.start for a,b in zip(run.document.passages,run.document.passages[1:])))

    def test_overlap_complete_coverage_and_cache_invalidation(self):
        client = Client()
        run = self.run_document(client)
        self.assert_exact(run, self.text)
        self.assertGreater(len(client.inputs), 4)
        self.assertTrue(all(len(t) <= 8000 for t in client.inputs))
        self.assertIn(client.inputs[0][-500:], client.inputs[1])
        cached = Client()
        self.assert_exact(self.run_document(cached), self.text)
        self.assertEqual(cached.inputs, [])
        changed = Client()
        self.run_document(changed, prompt='Autre prompt')
        self.assertGreater(len(changed.inputs), 4)

    def test_resume_after_transport_failure_and_corrupt_checkpoint(self):
        client = Client(fail=3)
        with self.assertRaisesRegex(ValueError, 'reprendre'):
            self.run_document(client)
        resumed = Client()
        self.assert_exact(self.run_document(resumed), self.text)
        self.assertNotIn(client.inputs[0], resumed.inputs)
        checkpoint = next((self.root/'checkpoints').rglob('0.json'))
        checkpoint.write_text('invalide')
        repaired = Client()
        self.assert_exact(self.run_document(repaired), self.text)
        self.assertEqual(len(repaired.inputs), 1)

    def test_no_sentence_separator_or_multilingual_text_is_lost(self):
        for text in ['字'*28000, ('مرحبا. Identité non confirmée。\n'*1200)]:
            self.assert_exact(self.run_document(Client(), text), text)

    def test_long_pdf_ingestion_retains_pages_and_token_safe_spans(self):
        path = self.root/'long.pdf'
        path.write_bytes(pdf_bytes(*[('Page %s. ' % i) + 'Identite incertaine. '*20 for i in range(120)]))
        extracted = extract_pdf(path)
        self.assertGreater(len(extracted.text), 24000)
        encoder, _ = make_embedder(model=TestModel())
        database = QdrantClient(':memory:')
        self.addCleanup(database.close)
        store = PassageIndex(database)
        batches = []
        original_encode = encoder.embed_documents
        def encode(texts):
            batches.append(len(texts))
            return original_encode(texts)
        encoder.embed_documents = encode
        class Index:
            def add(_, passages, embedder):
                for p in passages:
                    self.assertEqual(p.text, extracted.text[p.start:p.end])
                    self.assertEqual((p.page_start,p.page_end), extracted.page_range(p.start,p.end))
                    embedder._check_texts([p.text], embedder.profile.document_prompt)
                store.add(passages, embedder)
        artifact = self.root/'artifact.json'
        pages, count, warning = ingest_pdf(path, self.source, Client(), encoder, Index(), artifact, lambda _:None, coherent=True)
        self.assertEqual(pages, 120)
        self.assertGreater(count, 100)
        self.assertEqual(database.count(store.collection).count, count)
        self.assertGreater(len(batches), 1)
        self.assertLessEqual(max(batches), 16)
        saved = json.loads(artifact.read_text())
        self.assertEqual(saved['text'], extracted.text)
        self.assertEqual(''.join(p['text'] for p in saved['segmentation']['document']['passages']), extracted.text)
        with self.assertRaises(ValueError):
            extract_pdf(path, max_pages=100)
        with self.assertRaises(ValueError):
            extract_pdf(path, max_characters=24000)
