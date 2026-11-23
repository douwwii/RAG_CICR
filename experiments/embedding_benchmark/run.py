"""24 configurations, Qdrant isolé en mémoire ; aucun accès en écriture à l’index applicatif."""
from pathlib import Path
import argparse,json,sys,time,hashlib,resource,platform,statistics
import numpy as np
import torch
from qdrant_client import QdrantClient,models
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from embeddings import SentenceTransformerEmbedder
from config import EmbeddingConfig
MODELS={
 'minilm':('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2','e8f8c211226b894fcb81acc59f3b34ba3efd5f42'),
 'bge-m3':('BAAI/bge-m3','5617a9f61b028005a4858fdac845db406aefb181'),
 'qwen-0.6b':('Qwen/Qwen3-Embedding-0.6B','97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3'),
}
VARIANTS={'actuel':(False,'current'),'contexte':(True,'current'),'coherent':(False,'coherent'),'contexte_coherent':(True,'coherent')}

def overlap_coverage(interval,spans):
 a,b=interval; cursor=a; covered=0
 for left,right in sorted(spans):
  left=max(a,left,cursor);right=min(b,right)
  if right>left:
   covered+=right-left;cursor=right
 return covered/(b-a)

def evaluate(hits,case):
 def coverage(items):
  spans=[(h['start'],h['end']) for h in items if h['document']==case['document']]
  return [overlap_coverage(interval,spans) for interval in case['evidence']]
 first=coverage(hits[:1]);top=coverage(hits)
 rank=next((i for i,h in enumerate(hits,1) if all(x>=1 for x in coverage([h]))),None)
 return dict(hit1=all(x>=1 for x in first),coverage5=all(x>=1 for x in top),
             evidence_recall5=float(np.mean(top)),mrr5=1/rank if rank else 0.,
             document_hit5=any(h['document']==case['document'] for h in hits),
             returned_characters=sum(h['end']-h['start'] for h in hits))

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--model',choices=MODELS,required=True)
 args=parser.parse_args();out=ROOT/'experiments/embedding_benchmark/results'
 out.mkdir(parents=True,exist_ok=True)
 if not (out/'corpus.json').exists():
  (out/'corpus.json').write_bytes(Path(__file__).with_name('corpus.json').read_bytes())
 corpus=json.loads((out/'corpus.json').read_text());cases=corpus['cases']
 torch.set_num_threads(4)
 name,revision=MODELS[args.model];start=time.monotonic()
 encoder=SentenceTransformerEmbedder(EmbeddingConfig(model_name=name,revision=revision,batch_size=4,device='cpu'))
 # Qwen stocke ses poids en bfloat16 : imposer aussi le calcul en float32,
 # pas seulement le format du vecteur retourné, pour cette comparaison CPU.
 encoder._model.float()
 weight_dtype=str(next(encoder._model.parameters()).dtype)
 load_seconds=time.monotonic()-start
 print('Modèle chargé',name,'dimension',encoder.dimension,'limite',encoder.profile.max_seq_length,flush=True)
 path=out/(args.model+'-vectors.npz')
 cached=dict(np.load(path)) if path.exists() else {}
 timings=[];encoding_seconds=0.;encoded_documents=0
 def key(kind,text):return kind+hashlib.sha256((encoder.profile.fingerprint+weight_dtype+text).encode()).hexdigest()
 def documents(texts):
  nonlocal encoding_seconds,encoded_documents
  missing=list(dict.fromkeys(t for t in texts if key('d',t) not in cached))
  if missing:
   started=time.monotonic();vectors=encoder.embed_documents(missing);encoding_seconds+=time.monotonic()-started;encoded_documents+=len(missing)
   for text,v in zip(missing,vectors,strict=True):cached[key('d',text)]=v
   np.savez_compressed(path,**cached)
  return np.stack([cached[key('d',t)] for t in texts])
 query_vectors={};query_effective={}
 for mode in ['original','qwen']:
  for c in cases:
   text=c['question'] if mode=='original' else c['rewrite']
   try:encoder.validate_query(text)
   except ValueError:text=c['question']
   k=key('q',text)
   if k not in query_vectors:
    started=time.monotonic();query_vectors[k]=encoder.embed_query(text);timings.append(time.monotonic()-started)
   query_effective[(mode,c['id'])]=(k,text)
 print('Questions encodées',len(query_vectors),flush=True)
 results=[]
 with_client=QdrantClient(':memory:')
 try:
  for variant,(context,segmentation) in VARIANTS.items():
   points=[]
   for d in corpus['documents']:
    if d['kind']=='field':
     points.append(dict(document=d['id'],dossier=d['dossier'],start=0,end=len(d['text']),text=d['text'],title=d['id'],embedding=d['context'] if context else d['embedding']))
    else:
     for parent in d[segmentation]:
      for left,right in encoder.document_spans(parent['text']):
       start=parent['start']+left;end=parent['start']+right
       assert d['text'][start:end]==parent['text'][left:right]
       points.append(dict(document=d['id'],dossier=d['dossier'],start=start,end=end,text=d['text'][start:end],title=parent['title'],embedding=d['text'][start:end]))
   vectors=documents([p['embedding'] for p in points]);db=with_client
   db.create_collection(variant,vectors_config=models.VectorParams(size=encoder.dimension,distance=models.Distance.COSINE))
   db.upsert(variant,[models.PointStruct(id=i,vector=v.tolist(),payload={k:x for k,x in p.items() if k!='embedding'}) for i,(p,v) in enumerate(zip(points,vectors,strict=True))],wait=True)
   for mode in ['original','qwen']:
    details=[];search_times=[]
    for c in cases:
     k,effective=query_effective[(mode,c['id'])];started=time.monotonic()
     hits=db.query_points(variant,query=query_vectors[k].tolist(),limit=5,with_payload=True,
                         query_filter=models.Filter(must=[models.FieldCondition(key='dossier',match=models.MatchValue(value=c['dossier']))])).points
     search_times.append(time.monotonic()-started)
     assert len(hits)<=5 and all(h.payload['dossier']==c['dossier'] for h in hits)
     payloads=[dict(**h.payload,score=h.score) for h in hits]
     details.append(dict(case_id=c['id'],group=c['group'],question=c['question'],effective_query=effective,
                         metrics=evaluate(payloads,c),hits=payloads))
    summary={}
    for group in ['historical','pdf','novel','all']:
     selected=[r for r in details if group=='all' or r['group']==group]
     summary[group]=dict(n=len(selected),**{metric:float(np.mean([r['metrics'][metric] for r in selected])) for metric in selected[0]['metrics']})
    results.append(dict(model=args.model,variant=variant,query_mode=mode,indexed_points=len(points),summary=summary,search_ms_p50=statistics.median(search_times)*1000,details=details))
    print(args.model,variant,mode,summary['all'],flush=True)
   (out/(args.model+'.json')).write_text(json.dumps(dict(model_name=name,revision=revision,profile=encoder.profile.model_dump(),corpus_sha256=hashlib.sha256((out/'corpus.json').read_bytes()).hexdigest(),
    hardware=dict(platform=platform.platform(),cpu_threads=4,precision='float32',weight_dtype=weight_dtype),load_seconds=load_seconds,document_encode_seconds=encoding_seconds,unique_documents_encoded=encoded_documents,
    query_encode_ms_p50=statistics.median(timings)*1000,query_encode_ms_p95=float(np.percentile(timings,95))*1000,
    peak_process_ram_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,results=results),ensure_ascii=False,indent=2))
 finally:with_client.close()

if __name__=='__main__':main()
