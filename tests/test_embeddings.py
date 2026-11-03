"""Contrats d’embedding et raccord Qdrant, sans charger de modèle réel."""
import contextlib
import io
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest
from unittest.mock import patch

import numpy as np
from pydantic import ValidationError
from qdrant_client import QdrantClient, models

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from common import COLLECTION, TEXT_BUILDER_VERSION
from config import EmbeddingConfig
from embeddings import (
    EmbeddingCompatibilityError, EmbeddingError, EmbeddingProfile,
    SentenceTransformerEmbedder, ensure_embedding_compatible,
)
from index_metadata import ensure_collection_compatible, make_index_metadata
import index
import search


class FakeModel:
    """Encodeur déterministe : les tests vérifient le contrat, pas sa sémantique."""

    def __init__(self):
        self.max_seq_length = 8
        self.prompts = {}
        self.default_prompt_name = None
        self.document_calls = []
        self.query_calls = []
        self.tokenizer_calls = []
        self.document_output = None
        self.query_output = np.array([1., 0., 0.], dtype=np.float32)

    def get_embedding_dimension(self):
        return 3

    def get_sentence_embedding_dimension(self):
        raise AssertionError('La méthode dépréciée ne doit pas être appelée ici.')

    def tokenizer(self, texts, **kwargs):
        self.tokenizer_calls.append((list(texts), kwargs))
        return {'input_ids': [[0] * (len(text.split()) + 2) for text in texts]}

    def encode_document(self, texts, **kwargs):
        self.document_calls.append((list(texts), kwargs))
        if self.document_output is not None:
            return self.document_output
        return np.tile(np.array([1., 0., 0.], dtype=np.float32), (len(texts), 1))

    def encode_query(self, text, **kwargs):
        self.query_calls.append((text, kwargs))
        return self.query_output


def make_embedder(config=None, model=None):
    model = model if model is not None else FakeModel()
    with patch('embeddings._load_model', return_value=model), patch('embeddings.version', return_value='test-version'):
        return SentenceTransformerEmbedder(config or EmbeddingConfig()), model


class EmbeddingTests(unittest.TestCase):
    def test_shapes_dtype_and_document_order(self):
        embedder, model = make_embedder()
        model.document_output = np.array([[0., 1., 0.], [1., 0., 0.]])
        documents = embedder.embed_documents(['premier', 'deuxième'])
        query = embedder.embed_query('question')
        self.assertEqual(documents.shape, (2, 3))
        self.assertEqual(query.shape, (3,))
        self.assertEqual(documents.dtype, np.float32)
        self.assertEqual(query.dtype, np.float32)
        np.testing.assert_array_equal(documents, model.document_output)
        self.assertEqual(model.document_calls[0][0], ['premier', 'deuxième'])
        self.assertEqual(len(model.query_calls), 1)

    def test_empty_documents_do_not_call_the_backend(self):
        embedder, model = make_embedder()
        result = embedder.embed_documents([])
        self.assertEqual(result.shape, (0, 3))
        self.assertEqual(result.dtype, np.float32)
        self.assertEqual(model.document_calls, [])
        self.assertEqual(model.tokenizer_calls, [])

    def test_model_is_loaded_only_once_per_service(self):
        with patch('embeddings._load_model', return_value=FakeModel()) as loader:
            embedder = SentenceTransformerEmbedder()
            embedder.embed_documents(['document'])
            embedder.embed_query('question')
            embedder.embed_query('autre question')
        loader.assert_called_once()

    def test_invalid_text_inputs_are_rejected_before_encoding(self):
        embedder, model = make_embedder()
        for texts in ['texte', b'texte', None, [1], [''], [' \n'], ['valide', None]]:
            with self.subTest(texts=texts):
                with self.assertRaises(EmbeddingError):
                    embedder.embed_documents(texts)
        for question in ['', ' \t', None, 42, ['question']]:
            with self.subTest(question=question):
                with self.assertRaises(EmbeddingError):
                    embedder.embed_query(question)
        self.assertEqual(model.document_calls, [])
        self.assertEqual(model.query_calls, [])

    def test_token_limit_includes_special_tokens(self):
        embedder, model = make_embedder()
        embedder.embed_query('un deux trois quatre cinq six')
        with self.assertRaises(EmbeddingError) as caught:
            embedder.embed_query('un deux trois quatre cinq six sept')
        self.assertIn('9 tokens', str(caught.exception))
        self.assertIn('limite 8', str(caught.exception))
        self.assertEqual(len(model.query_calls), 1)
        self.assertFalse(model.tokenizer_calls[-1][1]['truncation'])
        self.assertTrue(model.tokenizer_calls[-1][1]['add_special_tokens'])

    def test_prompts_are_included_in_length_checks(self):
        embedder, model = make_embedder(EmbeddingConfig(query_prompt='query: ', document_prompt='passage: '))
        long_text = 'un deux trois quatre cinq six'
        with self.assertRaises(EmbeddingError):
            embedder.embed_query(long_text)
        with self.assertRaises(EmbeddingError):
            embedder.embed_documents(['court', long_text])
        self.assertEqual(model.query_calls, [])
        self.assertEqual(model.document_calls, [])
        self.assertEqual(model.tokenizer_calls[0][0], ['query: ' + long_text])

    def test_long_document_error_identifies_position_across_batches(self):
        embedder, model = make_embedder(EmbeddingConfig(batch_size=1))
        with self.assertRaises(EmbeddingError) as caught:
            embedder.embed_documents(['court', 'un deux trois quatre cinq six sept'])
        self.assertIn('Texte [1]', str(caught.exception))
        self.assertEqual(model.document_calls, [])

    def test_effective_prompts_follow_model_defaults_and_explicit_overrides(self):
        model = FakeModel()
        model.prompts = {'query': 'Q: ', 'document': 'D: ', 'passage': 'P: ', 'other': 'O: '}
        model.default_prompt_name = 'other'
        embedder, _ = make_embedder(model=model)
        self.assertEqual(embedder.profile.query_prompt, 'Q: ')
        self.assertEqual(embedder.profile.document_prompt, 'D: ')
        embedder.embed_query('question')
        embedder.embed_documents(['document'])
        self.assertEqual(model.query_calls[-1][1]['prompt'], 'Q: ')
        self.assertEqual(model.document_calls[-1][1]['prompt'], 'D: ')
        explicit, _ = make_embedder(EmbeddingConfig(query_prompt='', document_prompt='custom: '), model)
        self.assertEqual(explicit.profile.query_prompt, '')
        self.assertEqual(explicit.profile.document_prompt, 'custom: ')

    def test_passage_and_fallback_prompts_are_resolved(self):
        model = FakeModel()
        model.prompts = {'passage': 'P: ', 'corpus': 'C: ', 'other': 'O: '}
        model.default_prompt_name = 'other'
        embedder, _ = make_embedder(model=model)
        self.assertEqual(embedder.profile.query_prompt, 'O: ')
        self.assertEqual(embedder.profile.document_prompt, 'P: ')

    def test_wrong_shapes_and_non_numeric_outputs_are_rejected(self):
        embedder, model = make_embedder()
        for output in [np.ones((1, 3)), np.ones((2, 4)), ['a', 'b'], [[1.], [1., 2.]]]:
            with self.subTest(output=output):
                model.document_output = output
                with self.assertRaises(EmbeddingError):
                    embedder.embed_documents(['un', 'deux'])
        model.query_output = np.ones((1, 3))
        with self.assertRaises(EmbeddingError):
            embedder.embed_query('question')

    def test_non_finite_zero_integer_and_unnormalized_vectors_are_rejected(self):
        embedder, model = make_embedder()
        for output in [
            np.array([np.nan, 0., 0.]), np.array([np.inf, 0., 0.]),
            np.array([-np.inf, 0., 0.]), np.array([1e300, 0., 0.]),
            np.zeros(3), np.array([1, 0, 0]), np.ones(3),
        ]:
            with self.subTest(output=output):
                model.query_output = output
                with self.assertRaises(EmbeddingError):
                    embedder.embed_query('question')

    def test_normalization_can_be_disabled_and_changes_the_profile(self):
        normalized, _ = make_embedder()
        embedder, model = make_embedder(EmbeddingConfig(normalize_embeddings=False))
        model.query_output = np.array([2., 0., 0.])
        np.testing.assert_array_equal(embedder.embed_query('question'), [2., 0., 0.])
        self.assertFalse(model.query_calls[0][1]['normalize_embeddings'])
        self.assertNotEqual(embedder.profile.fingerprint, normalized.profile.fingerprint)

    def test_profile_excludes_device_batch_size_and_cache_policy(self):
        first, _ = make_embedder()
        second, _ = make_embedder(EmbeddingConfig(batch_size=1, device='cpu', local_files_only=False))
        self.assertEqual(first.profile, second.profile)
        self.assertEqual(first.profile.fingerprint, second.profile.fingerprint)

    def test_config_is_strict_frozen_and_uses_an_immutable_revision(self):
        for changes in [
            {'revision': 'main'}, {'revision': ''}, {'batch_size': 0},
            {'batch_size': True}, {'normalize_embeddings': 'true'},
            {'local_files_only': 1}, {'device': ''}, {'model_name': ' '},
        ]:
            with self.subTest(changes=changes):
                with self.assertRaises(ValidationError):
                    EmbeddingConfig(**changes)
        config = EmbeddingConfig()
        with self.assertRaises(ValidationError):
            config.batch_size = 1

    def test_incomplete_and_different_profiles_are_rejected(self):
        embedder, _ = make_embedder()
        expected = embedder.profile
        ensure_embedding_compatible(expected.model_dump(), expected)
        for stored in [None, {}, {**expected.model_dump(), 'unknown': 'value'}]:
            with self.subTest(stored=stored):
                with self.assertRaises(EmbeddingCompatibilityError):
                    ensure_embedding_compatible(stored, expected)
        for key in expected.model_dump():
            stored = expected.model_dump()
            del stored[key]
            with self.subTest(missing=key):
                with self.assertRaises(EmbeddingCompatibilityError):
                    ensure_embedding_compatible(stored, expected)
        for key, value in [
            ('model_name', 'autre-modele'), ('revision', 'a' * 40),
            ('dimension', 4), ('normalize_embeddings', False),
            ('max_seq_length', 9), ('query_prompt', 'query: '),
            ('document_prompt', 'passage: '), ('torch_version', 'other-version'),
        ]:
            stored = {**expected.model_dump(), key: value}
            with self.subTest(difference=key):
                with self.assertRaises(EmbeddingCompatibilityError) as caught:
                    ensure_embedding_compatible(stored, expected)
                self.assertIn(key, str(caught.exception))

    def test_invalid_model_capabilities_and_load_failures_are_explicit(self):
        for changes in [
            {'get_embedding_dimension': lambda: None},
            {'max_seq_length': None}, {'tokenizer': None},
        ]:
            model = FakeModel()
            for name, value in changes.items():
                setattr(model, name, value)
            with self.subTest(changes=changes):
                with self.assertRaises(EmbeddingError):
                    make_embedder(model=model)
        with patch('embeddings._load_model', side_effect=OSError('modèle absent du cache')):
            with self.assertRaises(EmbeddingError) as caught:
                SentenceTransformerEmbedder()
        self.assertIn('local_files_only=True', str(caught.exception))

    def test_dimension_getter_supports_sentence_transformers_5(self):
        model = FakeModel()
        model.get_embedding_dimension = None
        model.get_sentence_embedding_dimension = lambda: 3
        embedder, _ = make_embedder(model=model)
        self.assertEqual(embedder.dimension, 3)

    def test_service_module_does_not_import_model_or_storage_libraries(self):
        script = textwrap.dedent('''
            import builtins
            import sys
            original_import = builtins.__import__
            def guarded_import(name, *args, **kwargs):
                if name.split('.')[0] in {'torch', 'sentence_transformers', 'qdrant_client'}:
                    raise ImportError(name)
                return original_import(name, *args, **kwargs)
            builtins.__import__ = guarded_import
            sys.path.insert(0, sys.argv[1])
            import embeddings
            print('independent')
        ''')
        result = subprocess.run([
            sys.executable, '-B', '-c', script, str(ROOT / 'src'),
        ], check=True, capture_output=True, text=True)
        self.assertEqual(result.stdout.strip(), 'independent')


class FakeEmbeddingService:
    """Implémentation de l’interface sans Sentence Transformers."""

    def __init__(self, profile):
        self.profile = profile
        self.dimension = profile.dimension
        self.query_calls = 0

    def embed_documents(self, texts):
        return np.tile(np.array([1., 0., 0.], dtype=np.float32), (len(texts), 1))

    def embed_query(self, question):
        self.query_calls += 1
        return np.array([1., 0., 0.], dtype=np.float32)


class EmbeddingIndexTests(unittest.TestCase):
    def setUp(self):
        embedder, _ = make_embedder()
        self.profile = embedder.profile
        self.service = FakeEmbeddingService(self.profile)
        self.db = QdrantClient(':memory:')
        self.addCleanup(self.db.close)
        self.create_collection()

    def create_collection(self, *, dimension=3, distance=models.Distance.COSINE, metadata=None):
        if self.db.collection_exists(COLLECTION):
            self.db.delete_collection(COLLECTION)
        self.db.create_collection(
            COLLECTION, vectors_config=models.VectorParams(size=dimension, distance=distance),
            metadata=metadata if metadata is not None else make_index_metadata(self.profile, TEXT_BUILDER_VERSION),
        )

    def test_retrieval_accepts_an_alternative_service(self):
        self.db.upsert(COLLECTION, points=[
            models.PointStruct(id=2, vector=[1., 0., 0.], payload={'person_id': 'P001', 'field_name': 'lieu_de_deces'}),
            models.PointStruct(id=8, vector=[1., 0., 0.], payload={'person_id': 'P002', 'field_name': 'lieu_de_deces'}),
        ])
        hits = search.retrieve(self.db, self.service, 'question', 'P001', 'lieu_de_deces')
        self.assertEqual([hit.id for hit in hits], [2])
        self.assertEqual(self.service.query_calls, 1)

    def test_same_dimension_different_model_is_rejected_before_query_encoding(self):
        metadata = make_index_metadata(self.profile, TEXT_BUILDER_VERSION)
        metadata['embedding_profile']['model_name'] = 'autre-modele'
        self.create_collection(metadata=metadata)
        with patch.object(self.db, 'query_points') as query:
            with self.assertRaises(EmbeddingCompatibilityError):
                search.retrieve(self.db, self.service, 'question')
        query.assert_not_called()
        self.assertEqual(self.service.query_calls, 0)

    def test_missing_profile_and_text_preparation_versions_are_rejected(self):
        for metadata in [
            {}, {'text_builder_version': TEXT_BUILDER_VERSION},
            {'embedding_profile': self.profile.model_dump()},
            make_index_metadata(self.profile, 'other-text-builder'),
        ]:
            with self.subTest(metadata=metadata):
                self.create_collection(metadata=metadata)
                with self.assertRaises(EmbeddingCompatibilityError):
                    search.retrieve(self.db, self.service, 'question')

    def test_incompatible_dimensions_distance_and_named_vectors_are_rejected(self):
        for dimension, distance in [(4, models.Distance.COSINE), (3, models.Distance.DOT)]:
            with self.subTest(dimension=dimension, distance=distance):
                self.create_collection(dimension=dimension, distance=distance)
                with self.assertRaises(EmbeddingCompatibilityError):
                    search.retrieve(self.db, self.service, 'question')
        self.db.delete_collection(COLLECTION)
        self.db.create_collection(COLLECTION, vectors_config={'named': models.VectorParams(size=3, distance=models.Distance.COSINE)})
        with self.assertRaises(EmbeddingCompatibilityError):
            search.retrieve(self.db, self.service, 'question')

    def test_missing_collection_is_explicit(self):
        self.db.delete_collection(COLLECTION)
        with self.assertRaises(EmbeddingCompatibilityError) as caught:
            ensure_collection_compatible(self.db, COLLECTION, self.profile, TEXT_BUILDER_VERSION)
        self.assertIn('Collection absente', str(caught.exception))

    def test_indexing_stores_profile_after_success_and_preserves_legacy_collection(self):
        legacy_name = 'cicr_synthetic_minilm_v1'
        self.db.create_collection(legacy_name, vectors_config=models.VectorParams(size=3, distance=models.Distance.COSINE))
        self.db.upsert(legacy_name, points=[models.PointStruct(id=999, vector=[1., 0., 0.])])
        with patch.object(index, 'SentenceTransformerEmbedder', return_value=self.service), patch.object(index, 'client', return_value=self.db), patch.object(self.db, 'close'), contextlib.redirect_stdout(io.StringIO()):
            index.main()
        self.assertEqual(self.db.count(COLLECTION).count, 48)
        self.assertEqual(self.db.retrieve(legacy_name, ids=[999])[0].id, 999)
        metadata = self.db.get_collection(COLLECTION).config.metadata
        self.assertEqual(metadata, make_index_metadata(self.profile, TEXT_BUILDER_VERSION))

    def test_indexing_refuses_to_delete_an_incompatible_collection(self):
        metadata = make_index_metadata(self.profile, TEXT_BUILDER_VERSION)
        metadata['embedding_profile']['revision'] = 'a' * 40
        self.create_collection(metadata=metadata)
        self.db.upsert(COLLECTION, points=[models.PointStruct(id=999, vector=[1., 0., 0.])])
        with patch.object(index, 'SentenceTransformerEmbedder', return_value=self.service), patch.object(index, 'client', return_value=self.db), patch.object(self.db, 'close'):
            with self.assertRaises(EmbeddingCompatibilityError):
                index.main()
        self.assertEqual(self.db.count(COLLECTION).count, 1)
        self.assertEqual(self.db.retrieve(COLLECTION, ids=[999])[0].id, 999)

    def test_failed_indexing_does_not_publish_a_profile(self):
        with patch.object(index, 'SentenceTransformerEmbedder', return_value=self.service), patch.object(index, 'client', return_value=self.db), patch.object(self.db, 'close'), patch.object(self.db, 'upsert', side_effect=RuntimeError('échec simulé')):
            with self.assertRaises(RuntimeError):
                index.main()
        self.assertIsNone(self.db.get_collection(COLLECTION).config.metadata)
        with self.assertRaises(EmbeddingCompatibilityError):
            search.retrieve(self.db, self.service, 'question')


if __name__ == '__main__':
    unittest.main()
