"""Vérifier les mesures de preuve et l’ancrage avant d’interpréter le benchmark."""
from pathlib import Path
import json
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
sys.path.insert(0,str(ROOT/'experiments/embedding_benchmark'))
from alignment import recover_boundaries
from run import overlap_coverage,evaluate

class BenchmarkTests(unittest.TestCase):
    def test_union_requires_all_evidence_without_gaps(self):
        self.assertEqual(overlap_coverage([10,20],[(0,4),(10,15),(15,20)]),1)
        self.assertEqual(overlap_coverage([10,20],[(10,14),(15,20)]),.9)
        case=dict(document='A',evidence=[[0,5],[10,15]])
        hits=[dict(document='A',start=0,end=5),dict(document='A',start=10,end=15)]
        score=evaluate(hits,case)
        self.assertFalse(score['hit1']);self.assertTrue(score['coverage5'])
        self.assertFalse(evaluate([dict(document='B',start=0,end=20)],case)['coverage5'])

    def test_boundary_alignment_preserves_omitted_headers_and_line_breaks(self):
        source='En-tête\nSujet\nLe fait est\nincertain.\n\nAutre sujet\nUne autre information.\n'
        reply=json.dumps({'passages':[{'title':'Sujet','text':'Sujet Le fait est incertain.'},{'title':'Autre','text':'Autre sujet Une autre information.'}]})
        passages,gaps=recover_boundaries(source,reply)
        self.assertEqual(''.join(p['text'] for p in passages),source)
        self.assertGreater(gaps,0)
        for p in passages:self.assertEqual(source[p['start']:p['end']],p['text'])
        with self.assertRaises(ValueError):
            recover_boundaries(source,reply.replace('incertain','confirmé'))
