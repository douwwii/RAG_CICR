import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from config import OllamaConfig
from ollama_client import OllamaClient
from schemas import DocumentMetadata
from segmentation import segment_document
from segmentation_schemas import Generation, GenerationError, SegmentationRun


SOURCE = DocumentMetadata(
    dossier_id='DOS-TEST', document_id='TEST', source_kind='text', source_path='fixture.txt',
)
TEXT = 'Observation incertaine.\nDeuxième sujet.\t\n'


def proposal(text):
    return Generation(content=json.dumps({'passages': [{'title': 'Sujet', 'text': text}]}))


class ServiceTests(unittest.TestCase):
    def run_with(self, client, **kwargs):
        return segment_document(TEXT, SOURCE, client, prompt='Découpe', prompt_version='v1', **kwargs)

    def test_good_output_and_document_round_trip(self):
        client = Mock()
        client.generate.return_value = proposal(TEXT)
        result = self.run_with(client)
        self.assertEqual(result.document.status, 'validated')
        self.assertEqual(result.document.source, SOURCE)
        self.assertEqual(result.document.passages[0].text, TEXT)
        self.assertEqual(SegmentationRun.model_validate_json(result.model_dump_json()), result)
        self.assertEqual(client.generate.call_count, 1)

    def test_retry_preserves_input_and_records_first_failure(self):
        client = Mock()
        client.generate.side_effect = [proposal(TEXT.rstrip()), proposal(TEXT)]
        result = self.run_with(client)
        self.assertEqual(result.document.status, 'validated')
        self.assertEqual([attempt.error for attempt in result.attempts], ['coverage', None])
        first, second = (call.args for call in client.generate.call_args_list)
        self.assertEqual(first[1:], second[1:])
        self.assertIn('coverage', second[0])

    def test_invalid_attempts_return_unmodified_fallback(self):
        client = Mock()
        client.generate.return_value = Generation(content='{"passages":[]}')
        result = self.run_with(client)
        self.assertEqual([attempt.error for attempt in result.attempts], ['structure', 'structure'])
        self.assertEqual(result.document.status, 'fallback')
        item, = result.document.passages
        self.assertEqual((item.text, item.start, item.end), (TEXT, 0, len(TEXT)))

    def test_transport_timeout_does_not_submit_another_request(self):
        client = Mock()
        client.generate.side_effect = GenerationError('timeout', 'Délai dépassé.')
        result = self.run_with(client)
        self.assertEqual(result.document.status, 'fallback')
        self.assertEqual(result.attempts[0].error, 'timeout')
        self.assertEqual(client.generate.call_count, 1)


class OllamaClientTests(unittest.TestCase):
    def test_unlimited_timeout_is_forwarded_to_http(self):
        self.assertEqual(OllamaConfig().timeout_seconds, 90.0)
        with patch('ollama_client.urlopen', return_value=io.BytesIO(b'{}')) as request:
            OllamaClient(OllamaConfig(timeout_seconds=None))._request('/api/tags')
        self.assertIsNone(request.call_args.kwargs['timeout'])

    def test_http_request_preserves_raw_text_and_config(self):
        config = OllamaConfig(model_name='autre-modele', think=None, timeout_seconds=5.0)
        schema = {'type': 'object'}
        response = io.BytesIO(json.dumps({
            'message': {'content': '{}'}, 'done': True, 'total_duration': 2_000_000_000,
            'eval_duration': 1_000_000_000, 'eval_count': 12,
        }).encode())
        with patch('ollama_client.urlopen', return_value=response) as request:
            result = OllamaClient(config).generate('Consigne', TEXT, schema)
        payload = json.loads(request.call_args.args[0].data)
        self.assertEqual(payload['messages'][1]['content'], TEXT)
        self.assertEqual(payload['model'], 'autre-modele')
        self.assertEqual(payload['format'], schema)
        self.assertNotIn('think', payload)
        self.assertEqual(request.call_args.kwargs['timeout'], 5.0)
        self.assertEqual((result.server_seconds, result.generation_seconds, result.output_tokens), (2, 1, 12))

    def test_truncated_attempt_keeps_partial_model_response(self):
        client = OllamaClient(OllamaConfig())
        with patch.object(client, '_request', return_value={
            'message': {'content': '{"passages":'}, 'done': True, 'done_reason': 'length',
        }):
            result = segment_document(TEXT, SOURCE, client, prompt='Découpe', prompt_version='v1')
        self.assertEqual(result.document.status, 'fallback')
        self.assertEqual(result.attempts[0].error, 'truncated')
        self.assertEqual(result.attempts[0].generation.content, '{"passages":')

    def test_distinguishes_network_and_protocol_errors(self):
        client = OllamaClient(OllamaConfig())
        for error, kind in [
            (URLError(TimeoutError()), 'timeout'),
            (URLError(ConnectionRefusedError()), 'connection'),
            (HTTPError('http://localhost', 503, 'busy', {}, None), 'http'),
        ]:
            with self.subTest(kind=kind), patch('ollama_client.urlopen', side_effect=error):
                with self.assertRaises(GenerationError) as caught:
                    client.generate('Prompt', TEXT, {})
                self.assertEqual(caught.exception.kind, kind)
        with patch('ollama_client.urlopen', return_value=io.BytesIO(b'not json')):
            with self.assertRaises(GenerationError) as caught:
                client.generate('Prompt', TEXT, {})
            self.assertEqual(caught.exception.kind, 'protocol')
