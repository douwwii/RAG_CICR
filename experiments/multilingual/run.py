"""Essai réel BGE-M3/Qwen, données fictives, sans modifier l’index applicatif."""
from pathlib import Path
import sys,json,time
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
from web.index_config import BGE_CONFIG,create_embedder
from config import OllamaConfig
from ollama_client import OllamaClient
from query_rewriting import rewrite_question
from reranking import rerank
from segmentation import segment_document
from schemas import DocumentMetadata
from qdrant_client import QdrantClient,models
folder=Path(__file__).resolve().parent
sources={
'fr':['Le sac personnel de Sami a été remis à Nora, sa sœur. Une copie de l’inventaire a été remise à Paul, archiviste.','Une attestation annonce le décès d’un homonyme de Sami. Elle ne confirme pas le décès de la personne recherchée.','Le 12 avril est la date du signalement, pas celle de la disparition. La date de disparition reste inconnue.'],
'en':['The personal bag belonging to Lina was handed to Mary, her sister. A copy of the inventory was given to John, the archivist.','A certificate reports the death of someone with the same name as Lina. It does not confirm the death of the person being sought.','April 12 is the reporting date, not the disappearance date. The disappearance date remains unknown.'],
'es':['El bolso personal de Karim fue entregado a Sara, su hermana. Una copia del inventario fue entregada a Pedro, el archivero.','Un certificado informa de la muerte de un homónimo de Karim. No confirma la muerte de la persona buscada.','El 12 de abril es la fecha de la denuncia, no de la desaparición. La fecha de desaparición sigue siendo desconocida.'],
'ar':['سُلّمت الحقيبة الشخصية الخاصة بـ Adam إلى أخته Salma. وسُلّمت نسخة من الجرد إلى أمين الأرشيف Omar.','تذكر شهادة وفاة شخص يحمل الاسم نفسه Adam. ولا تؤكد وفاة الشخص المبحوث عنه.','يوم 12 أبريل هو تاريخ تقديم البلاغ وليس تاريخ الاختفاء. لا يزال تاريخ الاختفاء غير معروف.']}
cases=[('fr','fr','À qui le sac personnel de Sami a-t-il été remis ?',0),('en','en','Is the death of Lina confirmed?',1),('es','es','¿A quién se entregó el bolso personal de Karim?',0),('ar','ar','هل تم تأكيد وفاة Adam؟',1),('fr','es','À qui a été remis le sac personnel de Karim, et non la copie de l’inventaire ?',0),('en','ar','Is the death of Adam confirmed?',1),('es','en','¿Se ha confirmado la muerte de Lina?',1),('ar','fr','إلى من سُلّمت الحقيبة الشخصية الخاصة بـ Sami؟',0)]
(folder/'corpus.json').write_text(json.dumps(dict(sources=sources,cases=cases),ensure_ascii=False,indent=2))
client=OllamaClient(OllamaConfig(num_predict=2048,timeout_seconds=180.0));encoder=create_embedder(BGE_CONFIG)
cache_path=folder/'raw.json';cache=json.loads(cache_path.read_text()) if cache_path.exists() else {}
class Cached:
 def generate(self,p,t,s):
  import hashlib
  from segmentation_schemas import Generation
  key=hashlib.sha256((p+t+json.dumps(s,sort_keys=True)).encode()).hexdigest()
  if key not in cache:
   started=time.monotonic();g=client.generate(p,t,s);cache[key]=dict(g=g.model_dump(),seconds=time.monotonic()-started);cache_path.write_text(json.dumps(cache,ensure_ascii=False,indent=2))
  return Generation.model_validate(cache[key]['g'])
proxy=Cached();points=[];segments={}
(folder/'manifest.json').write_text(json.dumps(dict(model=client.config.model_name,loaded=client.loaded_models(),embedding=encoder.profile.model_dump(),query_prompt=Path('prompts/query_rewriting/v5-multilingual.txt').read_text(),segmentation_prompt=Path('prompts/segmentation/v4-multilingual.txt').read_text(),reranking_prompt=Path('prompts/reranking/v3-multilingual.txt').read_text()),ensure_ascii=False,indent=2))
for lang,texts in sources.items():
 text='\n\n'.join(texts);source=DocumentMetadata(document_id=lang,dossier_id='MULTI',source_kind='pdf',source_path='synthetic-'+lang)
 run=segment_document(text,source,proxy,prompt=Path('prompts/segmentation/v4-multilingual.txt').read_text(),prompt_version='multilingual',coherent=True)
 segments[lang]=dict(status=run.document.status,exact=''.join(p.text for p in run.document.passages)==text,count=len(run.document.passages))
 # Frontières annotées fixées pour isoler la recherche de la segmentation.
 for i,t in enumerate(texts):points.append(dict(passage_id=lang+'-'+str(i),dossier_id='MULTI',document_id=lang,title='',text=t,name=lang+'.txt'))
db=QdrantClient(':memory:');db.create_collection('multi',vectors_config=models.VectorParams(size=encoder.dimension,distance=models.Distance.COSINE))
vectors=encoder.embed_documents([p['text'] for p in points]);db.upsert('multi',[models.PointStruct(id=i,vector=v.tolist(),payload=p) for i,(p,v) in enumerate(zip(points,vectors))])
rows=[]
for qlang,slang,q,i in cases:
 rewritten=rewrite_question(proxy,q,encoder);v=encoder.embed_query(rewritten)
 candidates=[dict(h.payload,score=h.score) for h in db.query_points('multi',query=v.tolist(),limit=12).points]
 result=rerank(proxy,q,candidates);expected=slang+'-'+str(i)
 row=dict(question=q,question_language=qlang,source_language=slang,reformulation=rewritten,expected=expected,cosine_first=candidates[0]['passage_id'],reranked_first=result['results'][0]['passage_id'],found5=expected in [p['passage_id'] for p in result['results']],status=result['reranking']['status'],assessment=result['assessment'],first_reason=result['results'][0].get('relevance_reason'),source_exact=all(p['text']==next(c['text'] for c in candidates if c['passage_id']==p['passage_id']) for p in result['results']))
 rows.append(row);(folder/'results.json').write_text(json.dumps(dict(segmentation=segments,cases=rows),ensure_ascii=False,indent=2));print(qlang,slang,row['cosine_first']==expected,row['reranked_first']==expected,row['status'],flush=True)
db.close()
