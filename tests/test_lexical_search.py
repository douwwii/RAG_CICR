"""Contrats lexicaux, sans modèle ni données persistantes."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from lexical_search import rank_lexical, fuse_ranks


def candidate(identifier, text):
    return dict(passage_id=str(identifier), text=text, title='', name='', document_id=str(identifier))


class LexicalTests(unittest.TestCase):
    def test_exact_names_accents_boundaries_and_order(self):
        source = [candidate(1, 'Élodie Martin est entendue.'), candidate(2, 'Martin Élodie'),
                  candidate(3, 'Élodie Martine'), candidate(4, 'Élodie et Martin')]
        self.assertEqual([c['passage_id'] for c in rank_lexical('ELODIE MARTIN', source, 30, exact=True)], ['1'])
        self.assertEqual(source[0]['text'], 'Élodie Martin est entendue.')

    def test_reference_and_non_latin_tokens(self):
        source = [candidate(1, 'PV AB-2026/0012'), candidate(2, 'PV AB-2026/00123')]
        self.assertEqual([c['passage_id'] for c in rank_lexical('AB-2026/0012', source, 30, exact=True)], ['1'])
        self.assertEqual(len(rank_lexical('محمد علي', [candidate(1, 'شهادة محمد علي')], 30, exact=True)), 1)
        self.assertEqual(rank_lexical('---', source, 30, exact=True), [])

    def test_phrase_does_not_cross_metadata_boundaries(self):
        source = [dict(candidate(1, 'Élodie'), title='Martin')]
        self.assertEqual(rank_lexical('Élodie Martin', source, 30, exact=True), [])
        self.assertEqual(len(rank_lexical('Élodie Martin', source, 30)), 1)

    def test_fusion_recovers_lexical_candidate_and_keeps_dense_and_limit(self):
        dense = [dict(candidate(i, 'Sémantique'), score=.9-i/100) for i in range(30)]
        lexical = [dict(candidate(99, 'AB-0012'), score=9000.)]
        result = fuse_ranks(dense, lexical, 30)
        self.assertEqual(len(result), 30)
        self.assertIn('99', [c['passage_id'] for c in result])
        self.assertIn('0', [c['passage_id'] for c in result])
        self.assertTrue(all(c['score_kind'] == 'rrf' for c in result))
        both = fuse_ranks(dense, [dense[12]], 30)
        self.assertEqual(both[0]['passage_id'], '12')
        self.assertEqual(len({c['passage_id'] for c in both}), len(both))
