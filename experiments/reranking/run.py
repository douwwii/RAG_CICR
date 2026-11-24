"""Comparaison appariée cosinus/Qwen, 20/25/30 candidats, sans écrire l’index web."""
from pathlib import Path
import hashlib,json,sys,time,math
import numpy as np
import torch
from qdrant_client import QdrantClient,models
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from web.index_config import BGE_CONFIG,create_embedder
from config import OllamaConfig
from ollama_client import OllamaClient
from query_rewriting import rewrite_question
from reranking import rerank,PROMPT
from segmentation_schemas import Generation
OUT=Path(__file__).resolve().parent/'results';OUT.mkdir(exist_ok=True)
corpus=json.loads(Path(__file__).with_name('corpus.json').read_text())
cachefile=OUT/'generations.json'
cache=json.loads(cachefile.read_text()) if cachefile.exists() else {}
client=OllamaClient(OllamaConfig(num_predict=2048,timeout_seconds=90.0))
class CachedClient:
 def __init__(self,real):self.real=real;self.seconds=0.
 def generate(self,system,text,schema):
  key=hashlib.sha256((system+text+json.dumps(schema,sort_keys=True)).encode()).hexdigest()
  if key not in cache:
   start=time.monotonic();generation=self.real.generate(system,text,schema)
   cache[key]=dict(generation=generation.model_dump(),seconds=time.monotonic()-start)
   cachefile.write_text(json.dumps(cache,ensure_ascii=False,indent=2))
  self.seconds+=cache[key]['seconds']
  return Generation.model_validate(cache[key]['generation'])
proxy=CachedClient(client)
encoder=create_embedder(BGE_CONFIG)
points=corpus['points'];cases=corpus['cases']
# Un même vecteur de question pour le baseline et les trois rerankings.
qcache=OUT/'queries.json';rewrites=json.loads(qcache.read_text()) if qcache.exists() else {}
for case in cases:
 if case['id'] not in rewrites:
  rewrites[case['id']]=rewrite_question(OllamaClient(client.config.model_copy(update={'num_predict':512})),case['question'],encoder)
  qcache.write_text(json.dumps(rewrites,ensure_ascii=False,indent=2))
print('Questions préparées',len(rewrites),flush=True)
db=QdrantClient(':memory:')
vectors=encoder.embed_documents([p['text'] for p in points])
db.create_collection('benchmark',vectors_config=models.VectorParams(size=encoder.dimension,distance=models.Distance.COSINE))
db.upsert('benchmark',[models.PointStruct(id=i,vector=v.tolist(),payload=p) for i,(p,v) in enumerate(zip(points,vectors))])
from metrics import metrics
manifest=dict(corpus_sha256=hashlib.sha256(Path(__file__).with_name('corpus.json').read_bytes()).hexdigest(),prompt=PROMPT,prompt_sha256=hashlib.sha256(PROMPT.encode()).hexdigest(),profile=encoder.profile.model_dump(),ollama=client.config.model_dump(),loaded_models=client.loaded_models())
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
report=[]
selected_count=25
for case in cases:
 vector=encoder.embed_query(rewrites[case['id']])
 candidates=[dict(h.payload,score=h.score) for h in db.query_points('benchmark',query=vector.tolist(),limit=30,with_payload=True,query_filter=models.Filter(must=[models.FieldCondition(key='dossier_id',match=models.MatchValue(value=case['dossier_id']))])).points]
 assert all(p['dossier_id']==case['dossier_id'] for p in candidates)
 baseline=candidates[:5]
 row=dict(case=case,prepared_question=rewrites[case['id']],baseline=metrics(baseline,case),baseline_ids=[p['passage_id'] for p in baseline],variants={})
 counts=[20,25,30] if case['dossier_id']=='CAL-A' else [selected_count]
 for count in counts:
  start=proxy.seconds
  result=rerank(proxy,case['question'],candidates[:count])
  row['variants'][str(count)]=dict(result=result,metrics=metrics(result['results'],case),llm_seconds=proxy.seconds-start,
    candidate_coverage=bool(case['required']) and set(case['required'])<={p['passage_id'] for p in candidates[:count]})
  print(case['id'],count,result['reranking']['status'],row['baseline'],row['variants'][str(count)]['metrics'],flush=True)
 # Tester l’ordre sur un sous-ensemble fixé avant lecture des résultats.
 if case['id'].endswith(('-death','-conflict')) and case['dossier_id'] in ['CAL-A','TEST-A']:
  shuffled=list(candidates[:selected_count]);np.random.default_rng(42).shuffle(shuffled)
  result=rerank(proxy,case['question'],shuffled)
  row['shuffled_25']=dict(result=result,metrics=metrics(result['results'],case))
 report.append(row)
 if case['id']=='CAL-A-absent':
  def quality(n):
   positive=[r for r in report if r['case']['answerable']]
   return (sum(r['variants'][str(n)]['metrics']['coverage5'] for r in positive),
           sum(r['variants'][str(n)]['metrics']['ndcg5'] for r in positive),
           -sum(r['variants'][str(n)]['llm_seconds'] for r in report))
  selected_count=max([20,25,30],key=quality)
  (OUT/'selection.json').write_text(json.dumps(dict(candidate_count=selected_count,rule='coverage5 puis NDCG5 puis latence ; six cas CAL-A uniquement'),ensure_ascii=False,indent=2))
  print('Taille retenue pour validation :',selected_count,flush=True)
 (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
db.close()
print('Évaluation terminée :',len(report),'questions.',flush=True)
