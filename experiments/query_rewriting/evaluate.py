"""Comparer original/reformulation/fusion sur les données réellement indexées, sans les modifier."""
from pathlib import Path
import sys, json, time, hashlib, argparse
import numpy as np
from qdrant_client import QdrantClient, models
from urllib.request import urlopen
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from common import make_text
from embeddings import SentenceTransformerEmbedder
from config import OllamaConfig
from ollama_client import OllamaClient
from query_rewriting import PROMPT, SearchQuery, validate_rewrite

parser=argparse.ArgumentParser()
parser.add_argument('--prompt', type=Path)
parser.add_argument('--split', choices=['calibration','reserve'])
parser.add_argument('--output', type=Path, required=True)
args=parser.parse_args()
prompt=args.prompt.read_text() if args.prompt else PROMPT
args.output.mkdir(parents=True,exist_ok=True)
cache_path=args.output/'generations.json'
cache=json.loads(cache_path.read_text()) if cache_path.exists() else {}
records=json.loads((ROOT/'data/documents.json').read_text())
points=[dict(id=str(r['id']),document=r['document_id'],dossier='DOS001' if int(r['person_id'][1:])<=4 else 'DOS002',text=r['value'],embedding=make_text(r)) for r in records]
with urlopen('http://127.0.0.1:8000/api/dossiers/DOS001/documents') as response:
    documents=json.load(response)
for doc in documents:
    if not doc['has_pdf'] or doc['status']!='done': continue
    artifact=json.loads((ROOT/'web_data'/(doc['document_id']+'.json')).read_text())
    points += [dict(id=p['passage_id'],document=p['document_id'],dossier=p['dossier_id'],text=p['text'],embedding=p['text']) for p in artifact['passages']]
cases=json.loads((ROOT/'data/scoped_queries.json').read_text())
for i,c in enumerate(cases):
    c['expected_ids']=[str(x) for x in c.pop('relevant_ids')]
    c['split']='calibration' if i<16 else 'reserve'
pdf=next(d['document_id'] for d in documents if d['has_pdf'] and d['status']=='done')
for i,(q,fragments) in enumerate([
('Qui a récupéré le sac de Sami ?',['sœur Nora']),
('Pourquoi le registre ne suffit-il pas à exclure un passage de Lina ?',['dernier feuillet manque','ne permet pas de conclure']),
('Le décès de Lina à Port-Lys est-il confirmé ?',['Port-Lys','homonyme','n’est pas établi']),
('Quand a lieu le prochain entretien ?',['jeudi à 14 h']),
('Sami a-t-il disparu le 8 mai ?',['8 mai','dernier appel','n’est pas établie']),
('Où un voisin pense-t-il avoir aperçu Lina, et son identité a-t-elle été confirmée ?',['hangar','n’a pas pu confirmer']),
('Où trouver une copie de l’attestation ?',['mairie de Belle-Rive']),
('Je cherche qui a eu les affaires de Sami, notamment son sac.',['sœur Nora']),
]):
    cases.append(dict(question=q,dossier_id='DOS001',document=pdf,fragments=fragments,split='calibration' if i<4 else 'reserve'))
if args.split: cases=[c for c in cases if c['split']==args.split]
encoder=SentenceTransformerEmbedder()
client=OllamaClient(OllamaConfig(num_predict=512,timeout_seconds=45.0))
(args.output/'manifest.json').write_text(json.dumps(dict(
    prompt=prompt, prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
    ollama=client.config.model_dump(), embedding_profile=encoder.profile.model_dump(),
    corpus_sha256=hashlib.sha256(json.dumps(points,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
    cases=cases, top_k=5,
),ensure_ascii=False,indent=2))
db=QdrantClient(':memory:')
vectors=encoder.embed_documents([p['embedding'] for p in points])
db.create_collection('evaluation',vectors_config=models.VectorParams(size=encoder.dimension,distance=models.Distance.COSINE))
db.upsert('evaluation',[models.PointStruct(id=i,vector=v.tolist(),payload=p) for i,(v,p) in enumerate(zip(vectors,points))])
def search(q,dossier):
    return [dict(**h.payload,score=h.score) for h in db.query_points('evaluation',query=encoder.embed_query(q).tolist(),limit=5,with_payload=True,query_filter=models.Filter(must=[models.FieldCondition(key='dossier',match=models.MatchValue(value=dossier))])).points]
def metrics(hits,c):
    if 'expected_ids' in c:
        relevant=set(c['expected_ids'])
        return dict(hit1=hits[0]['id'] in relevant,coverage5=bool(relevant.intersection(h['id'] for h in hits)))
    def text(items):return ' '.join(' '.join(h['text'].split()) for h in items if h['document']==c['document'])
    return dict(hit1=all(f in text(hits[:1]) for f in c['fragments']),coverage5=all(f in text(hits) for f in c['fragments']))
report=[]
for i,c in enumerate(cases):
    key=hashlib.sha256((prompt+c['question']).encode()).hexdigest()
    if key not in cache:
        start=time.monotonic()
        try:
            generation=client.generate(prompt,c['question'],SearchQuery.model_json_schema())
            query=SearchQuery.model_validate_json(generation.content).query.strip()
            encoder.embed_query(query)
            cache[key]=dict(query=query,seconds=time.monotonic()-start,raw=generation.content)
        except Exception as exc:
            cache[key]=dict(query=c['question'],seconds=time.monotonic()-start,error=str(exc))
        cache_path.write_text(json.dumps(cache,ensure_ascii=False,indent=2))
    rewrite=dict(cache[key])
    if args.prompt and args.prompt.name == 'v4.txt':
        try: validate_rewrite(c['question'],rewrite['query'])
        except ValueError as exc: rewrite.update(query=c['question'],rejected=str(exc))
    original=search(c['question'],c['dossier_id'])
    rewritten=search(rewrite['query'],c['dossier_id'])
    scores={};by_id={}
    for hits in [original,rewritten]:
        for rank,h in enumerate(hits,1):
            scores[h['id']]=scores.get(h['id'],0)+1/(60+rank)
            by_id[h['id']]=h
    fused=sorted(by_id.values(),key=lambda h:scores[h['id']],reverse=True)[:5]
    row=dict(**c,rewrite=rewrite,original=metrics(original,c),rewritten=metrics(rewritten,c),fused=metrics(fused,c),hits_original=original,hits_rewritten=rewritten)
    report.append(row)
    print(i+1,c['question'],'=>',rewrite['query'],row['original'],row['rewritten'],flush=True)
    (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
for split in ['calibration','reserve','all']:
    rows=[r for r in report if split=='all' or r['split']==split]
    print(split,len(rows),{m:{k:sum(r[m][k] for r in rows) for k in ['hit1','coverage5']} for m in ['original','rewritten','fused']},flush=True)
db.close()
