"""Tests des relations, de la persistance et de l’import du catalogue."""
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
import unittest

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from catalog import (
    Catalog, CatalogConflictError, CatalogError, CatalogSchemaError,
    DossierNotFoundError, ImportSummary,
)
from data_loader import DataValidationError
from import_catalog import load_catalog_seed
from schemas import DocumentMetadata, Dossier, Person


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.directory = Path(self.temporary_directory.name)
        self.db_path = self.directory / 'catalogue.sqlite'
        self.catalog = Catalog(self.db_path)
        self.addCleanup(self.catalog.close)
        self.catalog.initialize()
        self.seed = load_catalog_seed(ROOT / 'data' / 'catalog_seed.json')

    def register_seed(self):
        return self.catalog.register(
            dossiers=self.seed.dossiers, persons=self.seed.persons,
            documents=self.seed.documents,
        )

    def snapshot(self):
        """Lecture SQL indépendante pour vérifier aussi les lignes sans association."""
        connection = sqlite3.connect(self.db_path)
        try:
            return {
                table: connection.execute(f'SELECT * FROM {table} ORDER BY 1, 2').fetchall()
                for table in ['dossiers', 'persons', 'dossier_persons', 'documents', 'document_persons']
            }
        finally:
            connection.close()

    def write_manifest(self, data):
        path = self.directory / 'seed.json'
        path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        return path

    def test_seed_preserves_legacy_references_and_adds_two_shared_sources(self):
        self.assertEqual(self.register_seed(), ImportSummary(2, 8, 50))
        legacy = json.loads((ROOT / 'data' / 'documents.json').read_text('utf-8'))
        imported = {d.document_id: d for d in self.seed.documents}
        for record in legacy:
            document = imported[record['document_id']]
            self.assertEqual(document.source_locator, f"id={record['id']}")
            self.assertEqual(document.person_ids, [record['person_id']])
        for dossier_id, shared_id, people in [
            ('DOS001', 'DOC-CROISE-001', ['P001', 'P002']),
            ('DOS002', 'DOC-CROISE-002', ['P005', 'P006']),
        ]:
            self.assertEqual(len(self.catalog.list_persons(dossier_id)), 4)
            self.assertEqual(len(self.catalog.list_documents(dossier_id)), 25)
            document = self.catalog.get_document(dossier_id, shared_id)
            self.assertEqual(document.person_ids, people)
            self.assertTrue(Path(document.source_path).is_file())

    def test_identical_import_is_idempotent(self):
        self.register_seed()
        before = self.snapshot()
        self.assertEqual(self.register_seed(), ImportSummary())
        self.assertEqual(self.snapshot(), before)

    def test_membership_order_does_not_cause_a_conflict(self):
        self.register_seed()
        dossier = self.seed.dossiers[0]
        document = self.seed.documents[-2]
        result = self.catalog.register(
            dossiers=[Dossier(**{**dossier.model_dump(), 'person_ids': list(reversed(dossier.person_ids))})],
            documents=[DocumentMetadata(**{
                **document.model_dump(), 'person_ids': list(reversed(document.person_ids)),
            })],
        )
        self.assertEqual(result, ImportSummary())

    def test_catalog_persists_after_reopening(self):
        self.register_seed()
        expected = self.catalog.get_document('DOS001', 'DOC-P001-lieu_de_deces')
        self.catalog.close()
        with Catalog(self.db_path) as reopened:
            reopened.initialize()
            self.assertEqual(reopened.get_document('DOS001', expected.document_id), expected)
            self.assertEqual(len(reopened.list_dossiers()), 2)

    def test_initialize_preserves_existing_data(self):
        self.register_seed()
        before = self.snapshot()
        self.catalog.initialize()
        self.assertEqual(self.snapshot(), before)

    def test_unknown_dossier_never_expands_the_scope(self):
        self.register_seed()
        for dossier_id in ['DOS999', '', "DOS001' OR 1=1 --"]:
            with self.subTest(dossier_id=dossier_id):
                with self.assertRaises(DossierNotFoundError):
                    self.catalog.list_documents(dossier_id)
                with self.assertRaises(DossierNotFoundError):
                    self.catalog.list_persons(dossier_id)
                with self.assertRaises(DossierNotFoundError):
                    self.catalog.get_document(dossier_id, 'DOC-CROISE-001')

    def test_document_queries_stay_inside_the_dossier(self):
        self.register_seed()
        self.assertEqual(self.catalog.list_documents('DOS001', 'P005'), [])
        self.assertIsNone(self.catalog.get_document('DOS001', 'DOC-CROISE-002'))
        self.assertIsNone(self.catalog.get_document('DOS001', "x' OR 1=1 --"))
        documents = self.catalog.list_documents('DOS001', 'P001')
        self.assertEqual(len(documents), 7)
        self.assertTrue(all(d.dossier_id == 'DOS001' and 'P001' in d.person_ids for d in documents))

    def test_person_can_belong_to_several_dossiers(self):
        self.register_seed()
        shared = DocumentMetadata(
            document_id='DOC-INTER', dossier_id='DOS003', source_kind='rapport_fictif',
            source_path=self.seed.documents[-1].source_path, person_ids=['P001', 'P005'],
        )
        self.catalog.register(
            dossiers=[Dossier(dossier_id='DOS003', title='Autre dossier fictif', person_ids=['P001', 'P005'])],
            documents=[shared],
        )
        self.assertEqual(len(self.snapshot()['persons']), 8)
        self.assertEqual([p.person_id for p in self.catalog.list_persons('DOS003')], ['P001', 'P005'])
        self.assertEqual(self.catalog.list_documents('DOS003', 'P001'), [shared])
        self.assertNotIn('DOC-INTER', [d.document_id for d in self.catalog.list_documents('DOS001')])

    def test_homonyms_remain_distinct_people(self):
        self.register_seed()
        self.catalog.register(
            persons=[Person(person_id='P009', display_name='Jean Dupont')],
            dossiers=[Dossier(dossier_id='DOS003', title='Homonymes', person_ids=['P001', 'P009'])],
        )
        people = self.catalog.list_persons('DOS003')
        self.assertEqual([p.person_id for p in people], ['P001', 'P009'])
        self.assertEqual([p.display_name for p in people], ['Jean Dupont', 'Jean Dupont'])

    def test_document_without_identified_person_is_allowed(self):
        document = DocumentMetadata(
            document_id='DOC-EVENT', dossier_id='DOS001', source_kind='rapport_fictif',
            source_path='rapport_evenement.txt',
        )
        self.catalog.register(dossiers=[Dossier(dossier_id='DOS001', title='Événement')], documents=[document])
        self.assertEqual(self.catalog.get_document('DOS001', 'DOC-EVENT'), document)
        self.assertEqual(self.catalog.list_persons('DOS001'), [])

    def test_unknown_person_in_dossier_rolls_back_the_entire_batch(self):
        before = self.snapshot()
        with self.assertRaises(CatalogError):
            self.catalog.register(
                persons=[Person(person_id='P009', display_name='Personne fictive')],
                dossiers=[Dossier(dossier_id='DOS003', title='Invalide', person_ids=['P010'])],
            )
        self.assertEqual(self.snapshot(), before)

    def test_document_requires_an_existing_dossier(self):
        document = DocumentMetadata(
            document_id='DOC-UNKNOWN', dossier_id='DOS999', source_kind='rapport', source_path='x.txt',
        )
        with self.assertRaises(CatalogError):
            self.catalog.register(documents=[document])
        self.assertEqual(self.snapshot()['documents'], [])

    def test_document_person_must_belong_to_its_dossier(self):
        self.register_seed()
        before = self.snapshot()
        document = DocumentMetadata(
            document_id='DOC-INVALID', dossier_id='DOS001', source_kind='rapport',
            source_path='x.txt', person_ids=['P005'],
        )
        with self.assertRaises(CatalogError):
            self.catalog.register(documents=[document])
        self.assertEqual(self.snapshot(), before)

    def test_sql_constraints_protect_document_relations(self):
        self.register_seed()
        connection = sqlite3.connect(self.db_path)
        self.addCleanup(connection.close)
        connection.execute('PRAGMA foreign_keys = ON')
        for relation in [
            ('DOC-CROISE-001', 'DOS002', 'P005'),
            ('DOC-CROISE-001', 'DOS001', 'P005'),
            ('DOC-INCONNU', 'DOS001', 'P001'),
        ]:
            with self.subTest(relation=relation):
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute('INSERT INTO document_persons VALUES (?, ?, ?)', relation)
                connection.rollback()

    def test_foreign_keys_are_enforced_after_reopening(self):
        self.register_seed()
        self.catalog.close()
        with Catalog(self.db_path) as reopened:
            reopened.initialize()
            with self.assertRaises(CatalogError):
                reopened.register(dossiers=[Dossier(
                    dossier_id='DOS999', title='Invalide', person_ids=['P999'],
                )])

    def test_conflicting_definitions_are_rejected_without_changes(self):
        self.register_seed()
        before = self.snapshot()
        person = self.seed.persons[0]
        dossier = self.seed.dossiers[0]
        document = self.seed.documents[-2]
        batches = [
            {'persons': [Person(**{**person.model_dump(), 'display_name': 'Autre nom'})]},
            {'dossiers': [Dossier(**{**dossier.model_dump(), 'title': 'Autre titre'})]},
            {'dossiers': [Dossier(**{**dossier.model_dump(), 'person_ids': ['P001']})]},
            {'documents': [DocumentMetadata(**{**document.model_dump(), 'dossier_id': 'DOS002'})]},
            {'documents': [DocumentMetadata(**{**document.model_dump(), 'source_path': 'autre.txt'})]},
            {'documents': [DocumentMetadata(**{**document.model_dump(), 'person_ids': ['P001']})]},
        ]
        for batch in batches:
            with self.subTest(batch=batch):
                with self.assertRaises(CatalogConflictError):
                    self.catalog.register(**batch)
                self.assertEqual(self.snapshot(), before)

    def test_conflict_rolls_back_entities_inserted_earlier_in_the_batch(self):
        self.register_seed()
        before = self.snapshot()
        with self.assertRaises(CatalogConflictError):
            self.catalog.register(persons=[
                Person(person_id='P009', display_name='Nouvelle personne'),
                Person(person_id='P001', display_name='Nom contradictoire'),
            ])
        self.assertEqual(self.snapshot(), before)

    def test_duplicate_person_links_are_rejected_by_contracts(self):
        with self.assertRaises(ValidationError):
            Dossier(dossier_id='DOS001', title='Doublon', person_ids=['P001', 'P001'])
        with self.assertRaises(ValidationError):
            DocumentMetadata(
                document_id='DOC001', dossier_id='DOS001', source_kind='rapport',
                source_path='x.txt', person_ids=['P001', 'P001'],
            )

    def test_use_before_initialize_is_rejected(self):
        with Catalog(':memory:') as empty:
            with self.assertRaises(CatalogSchemaError):
                empty.list_dossiers()
            with self.assertRaises(CatalogSchemaError):
                empty.register()

    def test_unknown_schema_version_is_preserved_and_rejected(self):
        self.register_seed()
        before = self.snapshot()
        connection = sqlite3.connect(self.db_path)
        connection.execute('PRAGMA user_version = 99')
        connection.close()
        with self.assertRaises(CatalogSchemaError):
            self.catalog.initialize()
        self.assertEqual(self.snapshot(), before)

    def test_foreign_unversioned_database_is_not_overwritten(self):
        path = self.directory / 'foreign.sqlite'
        connection = sqlite3.connect(path)
        connection.execute('CREATE TABLE sentinel (value TEXT)')
        connection.execute("INSERT INTO sentinel VALUES ('à conserver')")
        connection.commit()
        connection.close()
        with Catalog(path) as foreign:
            with self.assertRaises(CatalogSchemaError):
                foreign.initialize()
        connection = sqlite3.connect(path)
        try:
            self.assertEqual(connection.execute('SELECT value FROM sentinel').fetchone()[0], 'à conserver')
        finally:
            connection.close()

    def test_importer_reports_a_missing_source(self):
        data = self.seed.model_dump()
        data['documents'][0]['source_path'] = str(self.directory / 'missing.json')
        with self.assertRaises(DataValidationError) as caught:
            load_catalog_seed(self.write_manifest(data))
        self.assertIn(data['documents'][0]['document_id'], str(caught.exception))

    def test_importer_checks_json_record_provenance(self):
        for changes in [
            {'source_locator': 'id=999'},
            {'source_locator': 'id=2'},
            {'source_locator': 'page=3'},
            {'source_locator': 'id=-1'},
            {'person_ids': ['P002']},
            {'source_kind': 'type_incorrect'},
        ]:
            with self.subTest(changes=changes):
                data = self.seed.model_dump()
                data['documents'][0].update(changes)
                with self.assertRaises(DataValidationError) as caught:
                    load_catalog_seed(self.write_manifest(data))
                self.assertIn('DOC-P001-nom', str(caught.exception))

    def test_importer_validates_manifest_shape(self):
        data = self.seed.model_dump()
        data['dossiers'][0]['person_ids'] = ['P001', 'P001']
        path = self.write_manifest(data)
        with self.assertRaises(DataValidationError) as caught:
            load_catalog_seed(path)
        self.assertIn(str(path), str(caught.exception))

    def test_cli_imports_from_another_working_directory_and_is_idempotent(self):
        path = self.directory / 'cli.sqlite'
        command = [sys.executable, '-B', str(ROOT / 'src' / 'import_catalog.py'), '--db', str(path)]
        first = subprocess.run(command, cwd=self.directory, capture_output=True, text=True, check=True)
        self.assertIn('Ajoutés : 2 dossiers, 8 personnes, 50 documents', first.stdout)
        second = subprocess.run(command, cwd=self.directory, capture_output=True, text=True, check=True)
        self.assertIn('Ajoutés : 0 dossiers, 0 personnes, 0 documents', second.stdout)
        with Catalog(path) as catalog:
            catalog.initialize()
            self.assertEqual(len(catalog.list_documents('DOS001')), 25)

    def test_cli_failure_leaves_existing_catalog_unchanged(self):
        self.register_seed()
        before = self.snapshot()
        data = self.seed.model_dump()
        data['persons'][0]['display_name'] = 'Nom contradictoire'
        path = self.write_manifest(data)
        result = subprocess.run([
            sys.executable, '-B', str(ROOT / 'src' / 'import_catalog.py'),
            '--seed', str(path), '--db', str(self.db_path),
        ], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('Erreur :', result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_cli_invalid_source_does_not_create_a_database(self):
        data = self.seed.model_dump()
        data['documents'][0]['source_path'] = str(self.directory / 'missing.json')
        manifest_path = self.write_manifest(data)
        database_path = self.directory / 'not_created.sqlite'
        result = subprocess.run([
            sys.executable, '-B', str(ROOT / 'src' / 'import_catalog.py'),
            '--seed', str(manifest_path), '--db', str(database_path),
        ], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(database_path.exists())

    def test_catalog_and_importer_do_not_import_ml_or_vector_storage(self):
        script = textwrap.dedent('''
            import builtins
            import sys
            from pathlib import Path
            original_import = builtins.__import__
            def guarded_import(name, *args, **kwargs):
                if name.split('.')[0] in {
                    'torch', 'transformers', 'sentence_transformers', 'qdrant_client', 'numpy',
                }:
                    raise ImportError(name)
                return original_import(name, *args, **kwargs)
            builtins.__import__ = guarded_import
            sys.path.insert(0, sys.argv[1])
            from catalog import Catalog
            from import_catalog import load_catalog_seed
            seed = load_catalog_seed(Path(sys.argv[2]))
            with Catalog(':memory:') as catalog:
                catalog.initialize()
                result = catalog.register(
                    dossiers=seed.dossiers, persons=seed.persons, documents=seed.documents,
                )
                print(result.documents)
        ''')
        result = subprocess.run([
            sys.executable, '-B', '-c', script,
            str(ROOT / 'src'), str(ROOT / 'data' / 'catalog_seed.json'),
        ], capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.strip(), '50')


if __name__ == '__main__':
    unittest.main()
