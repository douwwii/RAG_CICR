"""Isolation des dossiers, raccord au catalogue et annotations explicites."""
from collections import Counter
from pathlib import Path
import json
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np
from pydantic import ValidationError
from qdrant_client import QdrantClient, models

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from catalog import Catalog, CatalogSchemaError, DossierNotFoundError
from catalog_index import prepare_index_records
from common import DATA_FILE, TEXT_BUILDER_VERSION, make_text
from config import VectorStoreConfig
from data_loader import DataValidationError, load_field_records, load_scoped_evaluation_cases
from embeddings import EmbeddingCompatibilityError, EmbeddingProfile
from import_catalog import load_catalog_seed
from qdrant_store import QdrantVectorStore
from schemas import DocumentMetadata, Dossier, FieldRecord, Person
from scope import ScopeError, resolve_scope
from search import retrieve
from vector_store import VectorFilters, VectorHit, VectorRecord, VectorStoreError
import index


class ScopeTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.directory = Path(folder.name)
        self.source_path = self.directory / 'fields.json'
        self.catalog_path = self.directory / 'catalog.sqlite'
        self.fields = [FieldRecord(
            id=i, document_id=f'DOC-{i}', person_id=person,
            field_name=field, field_label=field, value=f'Information fictive {i}', source_kind='synthetic_form',
        ) for i, person, field in [(1, 'P001', 'lieu_de_deces'), (2, 'P001', 'lieu_de_deces'), (3, 'P002', 'temoignage')]]
        self.source_path.write_text(json.dumps([record.model_dump() for record in self.fields]))
        self.catalog = Catalog(self.catalog_path)
        self.addCleanup(self.catalog.close)
        self.catalog.initialize()
        documents = [DocumentMetadata(
            document_id=record.document_id, dossier_id='DOS002' if record.id == 2 else 'DOS001',
            source_kind=record.source_kind, source_path=str(self.source_path), source_locator=f'id={record.id}',
            person_ids=[record.person_id],
        ) for record in self.fields]
        report = self.directory / 'report.txt'
        report.write_text('Témoignage fictif évoquant deux personnes, sans conclusion établie.')
        documents.append(DocumentMetadata(
            document_id='SHARED', dossier_id='DOS001', source_kind='report', source_path=str(report),
            person_ids=['P001', 'P002'],
        ))
        self.catalog.register(
            persons=[Person(person_id=p, display_name='Dupont') for p in ['P001', 'P002']],
            dossiers=[Dossier(dossier_id='DOS001', title='A', person_ids=['P001', 'P002']),
                      Dossier(dossier_id='DOS002', title='B', person_ids=['P001']),
                      Dossier(dossier_id='EMPTY', title='Vide')], documents=documents,
        )
        self.records = prepare_index_records(self.fields, self.catalog, self.source_path)
        self.profile = EmbeddingProfile(
            schema_version=1, backend='test', model_name='test-model', revision='a' * 40,
            dimension=3, normalize_embeddings=True, max_seq_length=128,
            query_prompt='', document_prompt='', precision='float32', backend_version='1',
            transformers_version=None, torch_version=None,
        )
        self.definition = {'profile': self.profile, 'text_builder_version': TEXT_BUILDER_VERSION}
        self.db = QdrantClient(':memory:')
        self.store = QdrantVectorStore(VectorStoreConfig(collection_name='scoped'), client=self.db)
        self.addCleanup(self.store.close)
        self.vectors = np.array([[.8, .6, 0.], [1., 0., 0.], [0., 1., 0.]], dtype=np.float32)
        self.query = np.array([1., 0., 0.], dtype=np.float32)
        self.store.rebuild(self.records, self.vectors, **self.definition)
        self.embedder = SimpleNamespace(profile=self.profile, embed_query=Mock(return_value=self.query))

    def retrieve(self, dossier_id='DOS001', **kwargs):
        return retrieve(self.store, self.embedder, 'question', catalog=self.catalog, dossier_id=dossier_id, **kwargs)

    def write_cases(self, cases):
        path = self.directory / 'queries.json'
        path.write_text(json.dumps(cases))
        return path

    def case(self, **changes):
        return {'question': 'question', 'person_id': 'P001', 'relevant_ids': [1], 'dossier_id': 'DOS001', **changes}

    def run_cli(self, *args):
        # Toute tentative de charger le modèle ou d’ouvrir Qdrant échoue dans ce
        # sous-processus : les refus et périmètres vides doivent précéder ces étapes.
        script = textwrap.dedent('''
            import builtins, runpy, sys
            original_import = builtins.__import__
            def guarded_import(name, *args, **kwargs):
                if name.split('.')[0] in {'torch', 'sentence_transformers', 'qdrant_client'}:
                    raise ImportError('backend interdit avant validation du dossier')
                return original_import(name, *args, **kwargs)
            builtins.__import__ = guarded_import
            source = sys.argv[1]
            sys.path.insert(0, str(__import__('pathlib').Path(source).parent))
            sys.argv = [source, *sys.argv[2:]]
            runpy.run_path(source, run_name='__main__')
        ''')
        return subprocess.run([
            sys.executable, '-B', '-c', script, str(ROOT / 'src/search.py'), 'question',
            '--catalog', str(self.catalog_path), *args,
        ], capture_output=True, text=True)

    def test_index_uses_document_membership_for_a_person_in_two_dossiers(self):
        self.assertEqual([record.dossier_id for record in self.records], ['DOS001', 'DOS002', 'DOS001'])
        for field, record in zip(self.fields, self.records, strict=True):
            self.assertEqual(record.embedding_text, make_text(field.model_dump()))
            self.assertEqual(record.source_path, str(self.source_path))
            self.assertEqual(record.source_locator, f'id={field.id}')
            self.assertEqual({key: record.model_dump()[key] for key in field.model_dump()}, field.model_dump())

    def test_scope_keeps_shared_documents_and_distinct_homonyms(self):
        scope = resolve_scope(self.catalog, 'DOS001')
        self.assertEqual({d.document_id for d in scope.documents}, {'DOC-1', 'DOC-3', 'SHARED'})
        self.assertEqual({d.document_id for d in resolve_scope(self.catalog, 'DOS001', 'P001').documents}, {'DOC-1', 'SHARED'})
        self.assertEqual({d.document_id for d in resolve_scope(self.catalog, 'DOS001', 'P002').documents}, {'DOC-3', 'SHARED'})
        self.assertEqual([d.document_id for d in resolve_scope(self.catalog, 'DOS002', 'P001').documents], ['DOC-2'])

    def test_foreign_dossier_is_filtered_before_top_k(self):
        unrestricted = self.db.query_points('scoped', query=self.query.tolist(), limit=1).points
        self.assertEqual(unrestricted[0].id, 2)
        hits = self.retrieve(top_k=1)
        self.assertEqual([hit.id for hit in hits], [1])
        self.assertEqual(hits[0].payload.dossier_id, 'DOS001')

    def test_same_person_in_two_dossiers_never_merges_results(self):
        self.assertEqual([hit.id for hit in self.retrieve(person_id='P001')], [1])
        self.assertEqual([hit.id for hit in self.retrieve('DOS002', person_id='P001')], [2])

    def test_dossier_person_and_field_filters_intersect(self):
        self.assertEqual([hit.id for hit in self.retrieve(person_id='P002', field_name='temoignage')], [3])
        self.assertEqual(self.retrieve(person_id='P002', field_name='lieu_de_deces'), [])

    def test_unknown_dossier_is_rejected_before_encoding_or_querying(self):
        with patch.object(self.db, 'query_points') as query:
            with self.assertRaises(DossierNotFoundError):
                self.retrieve('UNKNOWN')
            query.assert_not_called()
        self.embedder.embed_query.assert_not_called()

    def test_empty_dossier_and_foreign_person_do_not_encode_or_query(self):
        with patch.object(self.db, 'query_points') as query:
            self.assertEqual(self.retrieve('EMPTY'), [])
            self.assertEqual(self.retrieve('DOS002', person_id='P002'), [])
            self.assertEqual(self.retrieve(person_id='UNKNOWN'), [])
            query.assert_not_called()
        self.embedder.embed_query.assert_not_called()

    def test_dossier_is_required_at_both_interfaces(self):
        with self.assertRaises(TypeError):
            retrieve(self.store, self.embedder, 'question', catalog=self.catalog)
        for dossier_id in ['', ' ', None, 1]:
            with self.subTest(dossier_id=dossier_id), self.assertRaises(VectorStoreError):
                self.retrieve(dossier_id)
        with self.assertRaises(ValidationError):
            VectorFilters()
        for filters in [None, {}, VectorFilters.model_construct()]:
            with self.subTest(filters=filters), patch.object(self.db, 'query_points') as query:
                with self.assertRaises(VectorStoreError):
                    self.store.search(self.query, filters, **self.definition)
                query.assert_not_called()

    def test_points_without_a_dossier_cannot_match(self):
        payload = self.records[0].model_dump()
        del payload['dossier_id']
        self.db.upsert('scoped', points=[models.PointStruct(id=99, vector=self.query.tolist(), payload=payload)])
        self.assertNotIn(99, [hit.id for hit in self.retrieve(top_k=10)])

    def test_alternative_backend_results_are_checked_against_the_catalog(self):
        changes = [
            {'dossier_id': 'DOS002'}, {'document_id': 'DOC-2'}, {'document_id': 'UNKNOWN'},
            {'source_path': str(self.directory / 'other.json')}, {'source_locator': 'id=999'},
            {'source_kind': 'other'}, {'person_id': 'P002'},
        ]
        for change in changes:
            record = self.records[0].model_copy(update=change)
            hits = [VectorHit(id=record.id, score=.8, payload=record)]
            with self.subTest(change=change), patch.object(self.store, 'search', return_value=hits):
                with self.assertRaises(ScopeError):
                    self.retrieve()

    def test_alternative_backend_cannot_ignore_person_or_field_filters(self):
        for changes, filters in [
            ({'person_id': 'P002'}, {'person_id': 'P001'}),
            ({'field_name': 'temoignage'}, {'field_name': 'lieu_de_deces'}),
        ]:
            record = self.records[0].model_copy(update=changes)
            with patch.object(self.store, 'search', return_value=[VectorHit(id=record.id, score=.8, payload=record)]):
                with self.assertRaises(ScopeError):
                    self.retrieve(**filters)

    def test_adapter_refuses_an_out_of_scope_backend_response(self):
        response = SimpleNamespace(points=[SimpleNamespace(id=2, score=1., payload=self.records[1].model_dump())])
        with patch.object(self.db, 'query_points', return_value=response):
            with self.assertRaises(VectorStoreError):
                self.store.search(self.query, VectorFilters(dossier_id='DOS001'), **self.definition)

    def test_old_or_malformed_payload_versions_are_refused_without_deletion(self):
        metadata = self.db.get_collection('scoped').config.metadata
        for schema_version in [None, 1, '2', 2.0]:
            with self.subTest(schema_version=schema_version):
                self.db.delete_collection('scoped')
                updated = dict(metadata)
                if schema_version is None:
                    del updated['vector_record_schema_version']
                else:
                    updated['vector_record_schema_version'] = schema_version
                self.db.create_collection('scoped', vectors_config=models.VectorParams(size=3, distance=models.Distance.COSINE), metadata=updated)
                with patch.object(self.db, 'delete_collection') as delete:
                    with self.assertRaises(EmbeddingCompatibilityError):
                        self.store.rebuild(self.records, self.vectors, **self.definition)
                    delete.assert_not_called()
                with self.assertRaises(EmbeddingCompatibilityError):
                    self.retrieve()

    def test_missing_catalog_reference_stops_preparation(self):
        with patch.object(self.catalog, 'lookup_document', return_value=None):
            with self.assertRaises(ScopeError):
                prepare_index_records(self.fields, self.catalog, self.source_path)

    def test_wrong_catalog_provenance_stops_preparation(self):
        document = self.catalog.lookup_document('DOC-1')
        for changes in [
            {'source_path': str(self.directory / 'wrong.json')}, {'source_locator': 'id=2'},
            {'source_kind': 'other'}, {'person_ids': ['P002']}, {'document_id': 'OTHER'},
        ]:
            with self.subTest(changes=changes), patch.object(self.catalog, 'lookup_document', return_value=document.model_copy(update=changes)):
                with self.assertRaises(ScopeError):
                    prepare_index_records(self.fields, self.catalog, self.source_path)

    def test_invalid_index_provenance_is_rejected_before_model_and_store(self):
        invalid_document = self.catalog.lookup_document('DOC-1').model_copy(update={'source_locator': 'id=999'})
        with patch.object(index, 'DATA_FILE', self.source_path), patch.object(index, 'CATALOG_FILE', self.catalog_path), \
             patch('catalog.Catalog.lookup_document', return_value=invalid_document), \
             patch.object(index, 'SentenceTransformerEmbedder') as encoder, patch.object(index, 'open_vector_store') as store:
            with self.assertRaises(ScopeError):
                index.main()
            encoder.assert_not_called()
            store.assert_not_called()

    def test_read_only_catalog_refuses_writes(self):
        before = self.catalog_path.read_bytes()
        with Catalog(self.catalog_path, read_only=True) as reader:
            self.assertEqual(reader.lookup_document('DOC-2').dossier_id, 'DOS002')
            with self.assertRaises(sqlite3.OperationalError):
                reader.register(dossiers=[Dossier(dossier_id='NEW', title='Nouveau')])
        self.assertEqual(self.catalog_path.read_bytes(), before)

    def test_read_only_missing_catalog_does_not_create_a_database(self):
        missing = self.directory / 'missing.sqlite'
        with self.assertRaises(sqlite3.OperationalError):
            Catalog(missing, read_only=True)
        self.assertFalse(missing.exists())

    def test_read_only_catalog_requires_the_known_schema(self):
        empty = self.directory / 'empty.sqlite'
        connection = sqlite3.connect(empty)
        connection.close()
        with self.assertRaises(CatalogSchemaError):
            Catalog(empty, read_only=True)

    def test_scoped_annotations_are_validated_by_document(self):
        cases = [self.case(), self.case(dossier_id='DOS002', relevant_ids=[2])]
        loaded = load_scoped_evaluation_cases(self.write_cases(cases), self.fields, self.catalog)
        self.assertEqual([case.model_dump() for case in loaded], cases)

    def test_invalid_scoped_annotations_are_refused(self):
        missing = self.case()
        del missing['dossier_id']
        for cases in [
            [], [missing], [self.case(dossier_id='')], [self.case(dossier_id='UNKNOWN')],
            [self.case(dossier_id='DOS002')], [self.case(person_id='P002')],
            [self.case(relevant_ids=[999])], [self.case(relevant_ids=[1, 1])],
            [self.case(relevant_ids=[1, 2])],
        ]:
            with self.subTest(cases=cases), self.assertRaises(DataValidationError):
                load_scoped_evaluation_cases(self.write_cases(cases), self.fields, self.catalog)

    def test_cli_requires_a_dossier_and_rejects_an_unknown_dossier_early(self):
        for args, message in [((), '--dossier'), (('--dossier', 'UNKNOWN'), 'Dossier inconnu')]:
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)
                self.assertNotIn('ImportError', result.stderr)

    def test_cli_foreign_person_returns_empty_without_model_or_vector_store(self):
        result = self.run_cli('--dossier', 'DOS002', '--person', 'P002')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Aucun résultat dans ce dossier', result.stdout)

    def test_cli_missing_catalog_does_not_create_a_database(self):
        missing = self.directory / 'absent.sqlite'
        result = self.run_cli('--dossier', 'DOS001', '--catalog', str(missing))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(missing.exists())
        self.assertNotIn('ImportError', result.stderr)


class ScopedFixtureTests(unittest.TestCase):
    def test_explicit_fixture_preserves_the_32_historical_questions(self):
        with Catalog(':memory:') as catalog:
            catalog.initialize()
            seed = load_catalog_seed(ROOT / 'data/catalog_seed.json')
            catalog.register(dossiers=seed.dossiers, persons=seed.persons, documents=seed.documents)
            fields = load_field_records(DATA_FILE)
            cases = load_scoped_evaluation_cases(ROOT / 'data/scoped_queries.json', fields, catalog)
            legacy = json.loads((ROOT / 'data/queries.json').read_text())
            self.assertEqual([{k: v for k, v in c.model_dump().items() if k != 'dossier_id'} for c in cases], legacy)
            self.assertEqual(Counter(c.dossier_id for c in cases), {'DOS001': 16, 'DOS002': 16})

    def test_scope_imports_without_numpy_or_model_and_vector_libraries(self):
        script = textwrap.dedent('''
            import builtins, sys
            original_import = builtins.__import__
            def guarded_import(name, *args, **kwargs):
                if name.split('.')[0] in {'numpy', 'torch', 'transformers', 'sentence_transformers', 'qdrant_client'}:
                    raise ImportError(name)
                return original_import(name, *args, **kwargs)
            builtins.__import__ = guarded_import
            sys.path.insert(0, sys.argv[1])
            import scope
            from data_loader import load_scoped_evaluation_cases
            print('independent')
        ''')
        result = subprocess.run([sys.executable, '-B', '-c', script, str(ROOT / 'src')], check=True, capture_output=True, text=True)
        self.assertEqual(result.stdout.strip(), 'independent')


if __name__ == '__main__':
    unittest.main()
