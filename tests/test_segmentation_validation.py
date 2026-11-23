import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from segmentation_validation import SegmentationValidationError, validate_segmentation


def response(*texts):
    return json.dumps({'passages': [{'title': 'Sujet', 'text': text} for text in texts]})


class ValidationTests(unittest.TestCase):
    def test_exact_offsets_include_all_whitespace_and_unicode(self):
        texts = ('\tÉ👤\r\n\r\n', 'Suite\u00a0!  \n', 'Suite\u00a0!  \n')
        source = ''.join(texts)
        result = validate_segmentation(source, response(*texts))
        start = 0
        for expected, passage in zip(texts, result, strict=True):
            self.assertEqual((passage.start, passage.end), (start, start + len(expected)))
            self.assertEqual(source[passage.start:passage.end], expected)
            start = passage.end
        self.assertEqual(''.join(item.text for item in result), source)

    def test_structure_rejected(self):
        for invalid in ('{', '{"passages":[]}', '{"passages":[{"title":" ","text":"A"}]}',
                        '{"passages":[{"title":"Sujet","text":""}]}',
                        '{"passages":[{"title":"Sujet","text":"A","start":0}]}'):
            with self.subTest(invalid=invalid):
                with self.assertRaises(SegmentationValidationError) as caught:
                    validate_segmentation('A', invalid)
                self.assertEqual(caught.exception.kind, 'structure')

    def test_content_diagnostics(self):
        for kind, text, parts, offset in [
            ('coverage', 'A \nB', ('A', 'B'), 1),
            ('coverage', 'A\r\n', ('A',), 1),
            ('order', 'A. B.', ('B.', 'A. '), 0),
            ('duplication', 'AB', ('A', 'A', 'B'), 1),
            ('fidelity', 'Café', ('Cafe\u0301',), 3),
            ('fidelity', 'A\r\nB', ('A\nB',), 1),
        ]:
            with self.subTest(kind=kind, parts=parts):
                with self.assertRaises(SegmentationValidationError) as caught:
                    validate_segmentation(text, response(*parts))
                self.assertEqual((caught.exception.kind, caught.exception.offset), (kind, offset))
