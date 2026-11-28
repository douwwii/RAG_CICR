"""Contrat du stockage, Qdrant local et indépendance des scripts applicatifs."""
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from pydantic import ValidationError
from qdrant_client import QdrantClient, models

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from config import VectorStoreConfig
from catalog import Catalog
from embeddings import EmbeddingCompatibilityError, EmbeddingProfile
from qdrant_store import QdrantVectorStore
from schemas import DocumentMetadata, Dossier, Person
from search import retrieve
from vector_store import VectorFilters, VectorHit, VectorRecord, VectorStoreError, open_vector_store


def make_profile():
    return EmbeddingProfile(
        schema_version=1, backend='test', model_name='test-model', revision='a' * 40,
        dimension=3, normalize_embeddings=True, max_seq_length=128,
        query_prompt='', document_prompt='', precision='float32', backend_version='1',
        transformers_version=None, torch_version=None,
    )


def make_record(identifier=1, person='P001', field='lieu_de_deces'):
    return VectorRecord(
        id=identifier, document_id=f'DOC{identifier}', person_id=person,
        field_name=field, field_label='Lieu de décès', value='  Hôpital fictif\n',
        source_kind='synthetic_form',
        embedding_text='Type de champ : Lieu de décès. Information :   Hôpital fictif\n',
        dossier_id='DOS001', source_path=str(ROOT / 'data/documents.json'), source_locator=f'id={identifier}',
    )


def make_catalog(records):
    catalog = Catalog(':memory:')
    catalog.initialize()
    catalog.register(
        persons=[Person(person_id=p, display_name=p) for p in sorted({r.person_id for r in records})],
        dossiers=[Dossier(dossier_id=d, title=d, person_ids=sorted({r.person_id for r in records if r.dossier_id == d}))
                  for d in sorted({r.dossier_id for r in records})],
        documents=[DocumentMetadata(document_id=r.document_id, dossier_id=r.dossier_id,
                                    source_kind=r.source_kind, source_path=r.source_path,
                                    source_locator=r.source_locator, person_ids=[r.person_id]) for r in records],
    )
    return catalog


class QdrantStoreTests(unittest.TestCase):
    def setUp(self):
        self.profile = make_profile()
        self.definition = {'profile': self.profile, 'text_builder_version': 'field_label_value_v1'}
        self.config = VectorStoreConfig(collection_name='store_test')
        self.db = QdrantClient(':memory:')
        self.store = QdrantVectorStore(self.config, client=self.db)
        self.addCleanup(self.store.close)
        self.records = [
            make_record(1), make_record(2, field='temoignage'),
            make_record(3, person='P002'), make_record(4, person='P002', field='temoignage'),
        ]
        self.vectors = np.array([[1., 0., 0.], [.8, .6, 0.], [0., 1., 0.], [0., 0., 1.]], dtype=np.float32)
        self.query = np.array([1., 0., 0.], dtype=np.float32)
        self.store.rebuild(self.records, self.vectors, **self.definition)

    def search(self, vector=None, filters=None, top_k=5):
        filters = VectorFilters(dossier_id='DOS001') if filters is None else filters
        return self.store.search(self.query if vector is None else vector, filters, top_k, **self.definition)

    def test_round_trip_preserves_payload_text_and_source(self):
        hit = self.search(top_k=1)[0]
        self.assertIsInstance(hit, VectorHit)
        self.assertEqual(hit.id, 1)
        self.assertEqual(hit.payload, self.records[0])
        self.assertEqual(hit.payload.value, '  Hôpital fictif\n')
        self.assertAlmostEqual(hit.score, 1., places=6)
        metadata = self.db.get_collection('store_test').config.metadata
        self.assertEqual(metadata, {
            'embedding_profile': self.profile.model_dump(), 'text_builder_version': 'field_label_value_v1',
            'vector_record_schema_version': 2,
        })

    def test_ranking_and_scores_match_direct_qdrant(self):
        query = np.array([.6, .8, 0.], dtype=np.float32)
        direct = self.db.query_points('store_test', query=query.tolist(), limit=4).points
        hits = self.search(query, top_k=4)
        self.assertEqual([h.id for h in hits], [h.id for h in direct])
        np.testing.assert_allclose([h.score for h in hits], [h.score for h in direct], atol=1e-7)
        self.assertEqual([h.id for h in hits], [2, 3, 1, 4])

    def test_filters_intersect_and_unknown_values_return_no_results(self):
        cases = [
            (VectorFilters(dossier_id='DOS001'), {1, 2, 3, 4}),
            (VectorFilters(dossier_id='DOS001', document_ids=['DOC3']), {3}),
            (VectorFilters(dossier_id='DOS001', document_ids=[]), set()),
            (VectorFilters(dossier_id='DOS001', person_id='P001'), {1, 2}),
            (VectorFilters(dossier_id='DOS001', field_name='lieu_de_deces'), {1, 3}),
            (VectorFilters(dossier_id='DOS001', person_id='P002', field_name='temoignage'), {4}),
            (VectorFilters(dossier_id='DOS001', person_id='absent'), set()),
            (VectorFilters(dossier_id='DOS001', field_name='absent'), set()),
        ]
        for filters, expected in cases:
            with self.subTest(filters=filters):
                self.assertEqual({h.id for h in self.search(filters=filters)}, expected)

    def test_top_k_limits_results(self):
        self.assertEqual(len(self.search(top_k=2)), 2)
        self.assertEqual(len(self.search(top_k=20)), 4)

    def test_rebuild_replaces_only_its_collection(self):
        self.db.create_collection('other', vectors_config=models.VectorParams(size=3, distance=models.Distance.COSINE))
        self.db.upsert('other', points=[models.PointStruct(id=999, vector=[1., 0., 0.])])
        self.store.rebuild([make_record(9)], self.vectors[:1], **self.definition)
        self.assertEqual([h.id for h in self.search()], [9])
        self.assertEqual(self.db.retrieve('other', ids=[999])[0].id, 999)

    def test_invalid_rebuild_inputs_preserve_the_existing_index(self):
        invalid = [
            ([], np.empty((0, 3))),
            ('bad', self.vectors),
            ([{}], self.vectors[:1]),
            ([self.records[0], self.records[0]], self.vectors[:2]),
            ([make_record().model_copy(update={'value': ' '})], self.vectors[:1]),
            (self.records, self.vectors[:3]),
            (self.records, np.ones((4, 4), dtype=np.float32)),
            (self.records, np.ones((4, 3), dtype=np.int64)),
            (self.records, np.zeros((4, 3), dtype=np.float32)),
            (self.records, np.ones((4, 3), dtype=np.float32)),
            (self.records, np.full((4, 3), np.nan)),
            (self.records, np.full((4, 3), np.inf)),
            (self.records, np.full((4, 3), 1e300)),
            (self.records, [[1.], [1., 2.]]),
        ]
        for records, vectors in invalid:
            with self.subTest(records=repr(records)[:90], shape=np.shape(vectors) if isinstance(vectors, np.ndarray) else 'other'):
                with patch.object(self.db, 'delete_collection') as delete:
                    with self.assertRaises(VectorStoreError):
                        self.store.rebuild(records, vectors, **self.definition)
                delete.assert_not_called()
                self.assertEqual({h.id for h in self.search()}, {1, 2, 3, 4})

    def test_invalid_definition_cannot_destroy_the_index(self):
        for definition in [
            {**self.definition, 'profile': None},
            {**self.definition, 'profile': self.profile.model_copy(update={'dimension': 0})},
            {**self.definition, 'text_builder_version': ''},
        ]:
            with self.subTest(definition=definition), patch.object(self.db, 'delete_collection') as delete:
                with self.assertRaises(VectorStoreError):
                    self.store.rebuild(self.records, self.vectors, **definition)
                delete.assert_not_called()

    def test_standalone_search_rejects_a_different_model(self):
        profile = self.profile.model_copy(update={'model_name': 'different'})
        with patch.object(self.db, 'query_points') as query:
            with self.assertRaises(EmbeddingCompatibilityError):
                self.store.search(self.query, VectorFilters(dossier_id='DOS001'), profile=profile, text_builder_version='field_label_value_v1')
            query.assert_not_called()

    def test_search_rejects_invalid_vectors_and_options_before_querying(self):
        cases = [
            {'vector': np.ones((1, 3))}, {'vector': np.ones(4)},
            {'vector': np.zeros(3)}, {'vector': np.array([1, 0, 0])},
            {'vector': np.array([np.inf, 0., 0.])}, {'vector': np.ones(3)},
            {'top_k': 0}, {'top_k': -1}, {'top_k': True}, {'top_k': 1.5},
            {'filters': {'person_id': 'P001'}},
            {'filters': VectorFilters(dossier_id='DOS001').model_copy(update={'person_id': ''})},
        ]
        for options in cases:
            with self.subTest(options=options), patch.object(self.db, 'query_points') as query:
                with self.assertRaises(VectorStoreError):
                    self.search(**options)
                query.assert_not_called()

    def test_normalization_can_be_disabled_explicitly(self):
        config = VectorStoreConfig(collection_name='unnormalized')
        profile = self.profile.model_copy(update={'normalize_embeddings': False})
        # Même client, fermé uniquement par self.store dans ce test.
        store = QdrantVectorStore(config, client=self.db)
        store.rebuild([make_record()], np.array([[2., 0., 0.]]), profile=profile, text_builder_version='v1')
        hit = store.search(np.array([3., 0., 0.]), VectorFilters(dossier_id='DOS001'), profile=profile, text_builder_version='v1')[0]
        self.assertAlmostEqual(hit.score, 1., places=6)

    def test_corrupt_payloads_are_rejected_as_storage_errors(self):
        for payload in [
            {'dossier_id': 'DOS001'}, {**self.records[0].model_dump(), 'id': 9},
            {**self.records[0].model_dump(), 'document_id': ''},
        ]:
            with self.subTest(payload=payload):
                self.db.upsert('store_test', points=[models.PointStruct(id=1, vector=self.query.tolist(), payload=payload)])
                with self.assertRaises(VectorStoreError):
                    self.search(top_k=1)

    def test_backend_query_failures_keep_the_original_cause(self):
        with patch.object(self.db, 'query_points', side_effect=RuntimeError('simulated')):
            with self.assertRaises(VectorStoreError) as caught:
                self.search()
        self.assertIsInstance(caught.exception.__cause__, RuntimeError)

    def test_partial_write_never_publishes_a_valid_profile(self):
        upsert = self.db.upsert

        def partial_write(**kwargs):
            upsert(collection_name=kwargs['collection_name'], points=kwargs['points'][:1])
            raise RuntimeError('interruption simulée')

        with patch.object(self.db, 'upsert', side_effect=partial_write):
            with self.assertRaises(VectorStoreError):
                self.store.rebuild(self.records, self.vectors, **self.definition)
        self.assertEqual(self.db.count('store_test').count, 1)
        self.assertIsNone(self.db.get_collection('store_test').config.metadata)
        with self.assertRaises(EmbeddingCompatibilityError):
            self.search()
        with self.assertRaises(EmbeddingCompatibilityError):
            self.store.rebuild(self.records, self.vectors, **self.definition)

    def test_incomplete_acknowledged_and_failed_publication_are_refused(self):
        failures = [
            ('upsert', {'return_value': models.UpdateResult(operation_id=0, status=models.UpdateStatus.ACKNOWLEDGED)}),
            ('count', {'return_value': models.CountResult(count=0)}),
            ('update_collection', {'return_value': False}),
        ]
        for method, kwargs in failures:
            with self.subTest(method=method):
                # Les essais suivants partent explicitement d’une collection absente.
                self.db.delete_collection('store_test')
                with patch.object(self.db, method, **kwargs):
                    with self.assertRaises(VectorStoreError):
                        self.store.rebuild(self.records, self.vectors, **self.definition)
                self.assertIsNone(self.db.get_collection('store_test').config.metadata)
                with self.assertRaises(EmbeddingCompatibilityError):
                    self.search()


class VectorStoreContractTests(unittest.TestCase):
    def test_opening_failure_is_reported_as_a_storage_error(self):
        with patch('qdrant_store.QdrantClient', side_effect=RuntimeError('stockage verrouillé')):
            with self.assertRaises(VectorStoreError) as caught:
                open_vector_store()
        self.assertIsInstance(caught.exception.__cause__, RuntimeError)

    def test_configuration_and_filters_are_strict(self):
        for changes in [{'backend': 'unknown'}, {'collection_name': ' '}, {'path': '/tmp/store'}]:
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                VectorStoreConfig(**changes)
        for changes in [{'person_id': ''}, {'field_name': 4}, {'dossier_id': None}, {'unknown': 'x'}]:
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                VectorFilters(**{'dossier_id': 'DOS001', **changes})
        with self.assertRaises(ValidationError):
            VectorStoreConfig().collection_name = 'changed'

    def test_hit_rejects_non_finite_scores_and_inconsistent_ids(self):
        for changes in [{'score': float('nan')}, {'score': float('inf')}, {'id': 9}]:
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                VectorHit(**{'id': 1, 'score': 1., 'payload': make_record(), **changes})

    def test_real_local_store_survives_close_and_reopen(self):
        profile = make_profile()
        definition = {'profile': profile, 'text_builder_version': 'v1'}
        with tempfile.TemporaryDirectory() as folder:
            config = VectorStoreConfig(path=Path(folder), collection_name='persistent')
            store = open_vector_store(config)
            try:
                store.rebuild([make_record()], np.array([[1., 0., 0.]], dtype=np.float32), **definition)
            finally:
                store.close()
            reopened = open_vector_store(config)
            try:
                hits = reopened.search(np.array([1., 0., 0.], dtype=np.float32), VectorFilters(dossier_id='DOS001'), **definition)
                self.assertEqual(hits[0].payload, make_record())
            finally:
                reopened.close()

    def test_retrieve_uses_an_alternative_store_and_checks_before_encoding(self):
        profile = make_profile()
        expected = [VectorHit(id=1, score=.9, payload=make_record())]
        catalog = make_catalog([expected[0].payload])
        self.addCleanup(catalog.close)
        events = []

        class AlternativeStore:
            def check_compatibility(self, actual, text_builder_version):
                events.append('check')
                self.definition = (actual, text_builder_version)

            def search(self, vector, filters, top_k, **definition):
                events.append('search')
                np.testing.assert_array_equal(vector, [1., 0., 0.])
                self.query = (filters, top_k, definition)
                return expected

        def encode(question):
            events.append('encode')
            self.assertEqual(question, 'question')
            return np.array([1., 0., 0.], dtype=np.float32)

        store = AlternativeStore()
        embedder = SimpleNamespace(profile=profile, embed_query=encode)
        self.assertIs(retrieve(store, embedder, 'question', catalog=catalog, dossier_id='DOS001',
                               person_id='P001', field_name='lieu_de_deces', top_k=3), expected)
        self.assertEqual(events, ['check', 'encode', 'search'])
        self.assertEqual(store.query[:2], (VectorFilters(dossier_id='DOS001', person_id='P001', field_name='lieu_de_deces'), 3))
        self.assertEqual(store.query[2], {'profile': profile, 'text_builder_version': store.definition[1]})

    def test_bad_filters_and_top_k_are_rejected_before_encoding(self):
        store = SimpleNamespace()
        embedder = SimpleNamespace()
        for kwargs in [{'person_id': ''}, {'field_name': ' '}, {'top_k': 0}]:
            with self.subTest(kwargs=kwargs), self.assertRaises(VectorStoreError):
                retrieve(store, embedder, 'question', catalog=None, dossier_id='DOS001', **kwargs)

    def test_contracts_and_scripts_import_without_qdrant_or_a_model_backend(self):
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
            import vector_store
            import index
            import search
            import evaluate
            print('independent')
        ''')
        result = subprocess.run([
            sys.executable, '-B', '-c', script, str(ROOT / 'src'),
        ], check=True, capture_output=True, text=True)
        self.assertEqual(result.stdout.strip(), 'independent')


if __name__ == '__main__':
    unittest.main()
