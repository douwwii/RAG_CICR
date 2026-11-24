"""Contrôle sans LLM : retirer les doublons textuels parmi les 30 candidats."""
from pathlib import Path
import sys,json
from qdrant_client import QdrantClient,models
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from web.index_config import BGE_CONFIG,create_embedder
from metrics import metrics
folder=Path(__file__).resolve().parent;out=folder/'results'
corpus=json.loads((folder/'corpus.json').read_text());queries=json.loads((out/'queries.json').read_text())
encoder=create_embedder(BGE_CONFIG);points=corpus['points']
db=QdrantClient(':memory:')
vectors=encoder.embed_documents([p['text'] for p in points])
db.create_collection('baseline',vectors_config=models.VectorParams(size=encoder.dimension,distance=models.Distance.COSINE))
db.upsert('baseline',[models.PointStruct(id=i,vector=v.tolist(),payload=p) for i,(p,v) in enumerate(zip(points,vectors))])
rows=[]
for c in corpus['cases']:
 hits=[dict(h.payload,score=h.score) for h in db.query_points('baseline',query=encoder.embed_query(queries[c['id']]).tolist(),limit=30,with_payload=True,query_filter=models.Filter(must=[models.FieldCondition(key='dossier_id',match=models.MatchValue(value=c['dossier_id']))])).points]
 unique=[];seen=set()
 for h in hits:
  key=' '.join(h['text'].split())
  if key not in seen:unique.append(h);seen.add(key)
 rows.append(dict(case_id=c['id'],baseline=metrics(hits[:5],c),deduplicated=metrics(unique[:5],c),ids=[h['passage_id'] for h in unique[:5]]))
(out/'dedup_baseline.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
db.close();print('Comparaison cosinus dédoublonné terminée.',flush=True)
