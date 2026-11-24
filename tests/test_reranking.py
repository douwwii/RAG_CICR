import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from reranking import rerank, validate_proposal
from segmentation_schemas import Generation, GenerationError


def candidates(count=25):
    return [dict(passage_id=str(i),dossier_id='D',document_id='DOC'+str(i),title='Titre',text=f'Information exacte numéro {i}.',name='Source',score=1-i/100,page_start=1,page_end=1) for i in range(count)]


def proposal(items):
    return dict(selected=[dict(passage_id=p['passage_id'],label='direct',reason='Répond à la question.') for p in items],coverage='direct')


class RerankingTests(unittest.TestCase):
    def test_reorders_existing_sources_without_rewriting(self):
        source=candidates()
        chosen=list(reversed(source[-5:]))
        client=Mock();client.generate.return_value=Generation(content=json.dumps(proposal(chosen)))
        result=rerank(client,'Question originale ?',source)
        self.assertEqual(result['reranking']['status'],'applied')
        self.assertEqual([p['passage_id'] for p in result['results']],[p['passage_id'] for p in chosen])
        self.assertEqual([p['text'] for p in result['results']],[p['text'] for p in chosen])
        payload=json.loads(client.generate.call_args.args[1])
        self.assertEqual(payload['question'],'Question originale ?')
        self.assertEqual(len(payload['candidates']),25)
        self.assertNotIn('score',payload['candidates'][0])

    def test_invalid_output_falls_back_without_summary(self):
        source=candidates()
        for change in ['unknown','duplicate','quote','summary','count']:
            response=proposal(source[:5])
            if change=='unknown':response['selected'][0]['passage_id']='unknown'
            if change=='duplicate':response['selected'][1]=response['selected'][0]
            if change=='quote':response['selected'][0]['quote']='Texte inventé'
            if change=='summary':response['summary']=[{'text':'Inventé','passage_ids':['unknown']}]
            if change=='count':response['selected'].pop()
            client=Mock();client.generate.return_value=Generation(content=json.dumps(response))
            with self.subTest(change=change),self.assertLogs('reranking',level='WARNING'):
                result=rerank(client,'Question ?',source)
            self.assertEqual(result['results'],source[:5]);self.assertIsNone(result['assessment'])
            self.assertEqual(result['reranking']['status'],'fallback')

    def test_network_budget_empty_and_scope(self):
        client=Mock();client.generate.side_effect=GenerationError('timeout','Timeout')
        with self.assertLogs('reranking',level='WARNING'):
            result=rerank(client,'Question ?',candidates())
        self.assertEqual(result['reranking']['status'],'fallback')
        client.reset_mock()
        self.assertEqual(rerank(client,'Question ?',[])['reranking']['status'],'empty')
        client.generate.assert_not_called()
        with self.assertLogs('reranking',level='WARNING'):
            result=rerank(client,'Question ?',candidates(),input_budget=10)
        self.assertEqual(result['reranking']['calls'],0)
        bad=candidates();bad[0]['dossier_id']='OTHER'
        with self.assertRaises(ValueError):rerank(client,'Question ?',bad)

    def test_fewer_candidates_and_no_answer_are_honest(self):
        source=candidates(2);response=proposal(source)
        for p in response['selected']:p.update(label='unrelated')
        response.update(coverage='none')
        client=Mock();client.generate.return_value=Generation(content=json.dumps(response))
        result=rerank(client,'Question sans réponse ?',source)
        self.assertEqual(result['assessment']['coverage'],'none')
        self.assertEqual(len(result['results']),2)

    def test_displayed_assessment_never_repeats_free_factual_summary(self):
        source=candidates(2);response=proposal(source)
        response['selected'][0]['reason']='Un fait inventé et non établi par les sources.'
        client=Mock();client.generate.return_value=Generation(content=json.dumps(response))
        result=rerank(client,'Question ?',source)
        self.assertNotIn('inventé',json.dumps(result['assessment']))
        self.assertEqual(result['assessment']['summary_mode'],'relevance_only')

    def test_budget_batches_keep_whole_passages_and_reselect_five(self):
        source=candidates(20)
        known={p['passage_id']:p for p in source}
        def generate(system,text,schema):
            data=json.loads(text)
            chosen=[known[p['passage_id']] for p in data['candidates'][:5]]
            for p in data['candidates']:
                self.assertEqual(p['text'],known[p['passage_id']]['text'])
            return Generation(content=json.dumps(proposal(chosen)))
        client=Mock();client.generate.side_effect=generate
        result=rerank(client,'Question ?',source,input_budget=2200)
        self.assertEqual(result['reranking']['status'],'applied')
        self.assertEqual(result['reranking']['calls'],3)
        self.assertEqual(len(result['results']),5)

    def test_invalid_identifier_retries_with_candidate_enum(self):
        source=candidates();bad=proposal(source[:5]);bad['selected'][0]['passage_id']='inventé'
        client=Mock();client.generate.side_effect=[Generation(content=json.dumps(bad)),Generation(content=json.dumps(proposal(source[:5])))]
        result=rerank(client,'Question ?',source)
        self.assertEqual(result['reranking']['status'],'applied')
        self.assertEqual(result['reranking']['calls'],2)
        schema=client.generate.call_args.args[2]
        self.assertEqual(schema['$defs']['Choice']['properties']['passage_id']['enum'],[p['passage_id'] for p in source])
