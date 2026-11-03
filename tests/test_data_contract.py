"""Tests du contrat de données, sans téléchargement ni base vectorielle."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

import common
from data_loader import (
    DataValidationError,
    load_evaluation_cases,
    load_field_records,
    validate_corpus,
)
from schemas import FieldRecord


class DataContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.directory = Path(self.temporary_directory.name)
        self.documents = json.loads((ROOT / 'data' / 'documents.json').read_text('utf-8'))
        self.queries = json.loads((ROOT / 'data' / 'queries.json').read_text('utf-8'))

    def write_json(self, data, filename='documents.json'):
        path = self.directory / filename
        path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        return path

    def test_existing_corpus_round_trip(self):
        records = load_field_records(ROOT / 'data' / 'documents.json')
        self.assertEqual(len(records), 48)
        self.assertEqual([record.model_dump() for record in records], self.documents)

    def test_common_loader_preserves_legacy_payloads(self):
        self.assertEqual(common.load_documents(), self.documents)
        path = self.write_json([self.documents[1]])
        with patch.object(common, 'DATA_FILE', path):
            self.assertEqual(common.load_documents(), [self.documents[1]])

    def test_existing_evaluation_round_trip(self):
        records = load_field_records(ROOT / 'data' / 'documents.json')
        cases = load_evaluation_cases(ROOT / 'data' / 'queries.json', records)
        self.assertEqual(len(cases), 32)
        self.assertEqual([case.model_dump() for case in cases], self.queries)

    def test_missing_required_fields(self):
        for field in self.documents[0]:
            with self.subTest(field=field):
                record = dict(self.documents[0])
                del record[field]
                with self.assertRaises(DataValidationError) as caught:
                    load_field_records(self.write_json([record]))
                self.assertIn(f'0.{field}', str(caught.exception))

    def test_types_are_not_coerced(self):
        invalid_values = [
            ('id', '1'), ('id', 1.0), ('id', True),
            ('document_id', 42), ('person_id', ['P001']),
            ('field_name', None), ('field_label', False),
            ('value', 1994), ('source_kind', 1),
        ]
        for field, value in invalid_values:
            with self.subTest(field=field, value=value):
                record = {**self.documents[0], field: value}
                with self.assertRaises(DataValidationError):
                    load_field_records(self.write_json([record]))

    def test_id_bounds(self):
        for record_id in [-1, 2**64]:
            with self.subTest(invalid_id=record_id):
                with self.assertRaises(DataValidationError):
                    load_field_records(self.write_json([
                        {**self.documents[0], 'id': record_id},
                    ]))
        for record_id in [0, 2**64 - 1]:
            with self.subTest(valid_id=record_id):
                records = load_field_records(self.write_json([
                    {**self.documents[0], 'id': record_id},
                ]))
                self.assertEqual(records[0].id, record_id)

    def test_blank_text_is_rejected(self):
        for field in self.documents[0].keys() - {'id'}:
            for value in ['', ' \t\n']:
                with self.subTest(field=field, value=value):
                    with self.assertRaises(DataValidationError):
                        load_field_records(self.write_json([
                            {**self.documents[0], field: value},
                        ]))

    def test_original_text_and_embedding_text_are_preserved(self):
        original = {
            **self.documents[1],
            'field_label': ' Lieu de décès ',
            'value': '  Hôpital Édouard-Herriot — témoignage non confirmé.\n',
        }
        record = load_field_records(self.write_json([original]))[0]
        self.assertEqual(record.model_dump(), original)
        self.assertEqual(
            common.make_text(record.model_dump()),
            f"Type de champ : {original['field_label']}. Information : {original['value']}",
        )
        date = load_field_records(self.write_json([self.documents[3]]))[0]
        self.assertEqual(date.value, '21 juin 1994')
        self.assertIsInstance(date.value, str)

    def test_unknown_keys_are_rejected(self):
        path = self.write_json([{**self.documents[0], 'personn_id': 'P001'}])
        with self.assertRaises(DataValidationError) as caught:
            load_field_records(path)
        self.assertIn('personn_id', str(caught.exception))

    def test_root_must_be_a_nonempty_list(self):
        for data in [{}, None, 'texte', 1, []]:
            with self.subTest(data=data):
                path = self.write_json(data)
                with self.assertRaises(DataValidationError) as caught:
                    load_field_records(path)
                self.assertIn(str(path), str(caught.exception))

    def test_array_members_must_be_records(self):
        path = self.write_json([self.documents[0], 'pas un enregistrement'])
        with self.assertRaises(DataValidationError) as caught:
            load_field_records(path)
        self.assertIn(str(path), str(caught.exception))

    def test_invalid_json_is_localized(self):
        path = self.directory / 'broken.json'
        path.write_text('[\n  {', encoding='utf-8')
        with self.assertRaises(DataValidationError) as caught:
            load_field_records(path)
        self.assertIn(str(path), str(caught.exception))
        self.assertIn('line 2', str(caught.exception))

    def test_invalid_utf8_is_localized(self):
        path = self.directory / 'broken.json'
        path.write_bytes(b'["\xff"]')
        with self.assertRaises(DataValidationError) as caught:
            load_field_records(path)
        self.assertIn(str(path), str(caught.exception))
        self.assertIn('UTF-8', str(caught.exception))

    def test_error_identifies_record_and_field(self):
        path = self.write_json([
            self.documents[0], {**self.documents[1], 'value': 123},
        ])
        with self.assertRaises(DataValidationError) as caught:
            load_field_records(path)
        self.assertIn(str(path), str(caught.exception))
        self.assertIn('1.value', str(caught.exception))

    def test_duplicate_record_ids_are_rejected(self):
        path = self.write_json([
            self.documents[0], {**self.documents[1], 'id': self.documents[0]['id']},
        ])
        with self.assertRaises(DataValidationError) as caught:
            load_field_records(path)
        for fragment in [str(path), 'id 1', '[0]', '[1]']:
            self.assertIn(fragment, str(caught.exception))

    def test_global_validation_rejects_empty_corpus_and_duplicate_ids(self):
        record = FieldRecord.model_validate(self.documents[0])
        with self.assertRaises(DataValidationError):
            validate_corpus([])
        with self.assertRaises(DataValidationError):
            validate_corpus([record, record])

    def test_several_fields_can_reference_the_same_document(self):
        path = self.write_json([
            self.documents[0],
            {**self.documents[1], 'document_id': self.documents[0]['document_id']},
        ])
        self.assertEqual(len(load_field_records(path)), 2)

    def test_unknown_relevant_id_is_localized(self):
        records = load_field_records(ROOT / 'data' / 'documents.json')
        path = self.write_json([
            self.queries[0], {**self.queries[1], 'relevant_ids': [999]},
        ], 'queries.json')
        with self.assertRaises(DataValidationError) as caught:
            load_evaluation_cases(path, records)
        for fragment in [str(path), 'question [1].relevant_ids[0]', '999', 'inexistant']:
            self.assertIn(fragment, str(caught.exception))

    def test_references_must_belong_to_the_annotated_person(self):
        records = load_field_records(ROOT / 'data' / 'documents.json')
        path = self.write_json([
            {**self.queries[0], 'person_id': 'P002'},
        ], 'queries.json')
        with self.assertRaises(DataValidationError) as caught:
            load_evaluation_cases(path, records)
        for fragment in ['P001', 'P002', 'question [0].relevant_ids[0]']:
            self.assertIn(fragment, str(caught.exception))

    def test_evaluation_annotations_must_be_complete_and_strict(self):
        records = load_field_records(ROOT / 'data' / 'documents.json')
        invalid_cases = [
            {**self.queries[0], 'question': ' \n'},
            {**self.queries[0], 'person_id': ''},
            {**self.queries[0], 'relevant_ids': []},
            {**self.queries[0], 'relevant_ids': ['2']},
            {**self.queries[0], 'relevant_ids': [True]},
            {**self.queries[0], 'relevant_ids': [2, 2]},
            {**self.queries[0], 'extra': 'inattendu'},
            {'question': 'Où ?', 'person_id': 'P001'},
        ]
        for case in invalid_cases:
            with self.subTest(case=case):
                path = self.write_json([case], 'queries.json')
                with self.assertRaises(DataValidationError) as caught:
                    load_evaluation_cases(path, records)
                self.assertIn(str(path), str(caught.exception))

    def test_empty_evaluation_is_rejected(self):
        records = load_field_records(ROOT / 'data' / 'documents.json')
        with self.assertRaises(DataValidationError):
            load_evaluation_cases(self.write_json([], 'queries.json'), records)

    def test_evaluation_rejects_an_invalid_reference_corpus(self):
        record = FieldRecord.model_validate(self.documents[0])
        path = self.write_json(self.queries, 'queries.json')
        for records in [[], [record, record]]:
            with self.subTest(records=records):
                with self.assertRaises(DataValidationError):
                    load_evaluation_cases(path, records)

    def test_validation_does_not_import_embedding_or_storage_libraries(self):
        script = textwrap.dedent('''
            import builtins
            import sys
            original_import = builtins.__import__
            def guarded_import(name, *args, **kwargs):
                if name.split('.')[0] in {
                    'torch', 'transformers', 'sentence_transformers',
                    'qdrant_client', 'numpy',
                }:
                    raise ImportError(f'Import interdit pour ce test : {name}')
                return original_import(name, *args, **kwargs)
            builtins.__import__ = guarded_import
            sys.path.insert(0, sys.argv[1])
            from common import load_documents
            print(len(load_documents()))
        ''')
        result = subprocess.run(
            [sys.executable, '-B', '-c', script, str(ROOT / 'src')],
            check=True, capture_output=True, text=True,
        )
        self.assertEqual(result.stdout.strip(), '48')


if __name__ == '__main__':
    unittest.main()
