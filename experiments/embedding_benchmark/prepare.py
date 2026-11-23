"""Figer corpus, preuves et segmentations avant de comparer les encodeurs."""
from pathlib import Path
import json,sys,re,hashlib
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from common import make_text
from config import OllamaConfig
from ollama_client import OllamaClient
from schemas import DocumentMetadata
from segmentation import segment_document
from query_rewriting import PROMPT,SearchQuery,validate_rewrite
from alignment import recover_boundaries
OUT=ROOT/'experiments/embedding_benchmark/results'
OUT.mkdir(parents=True,exist_ok=True)
# Consignes identiques pour tous les encodeurs, sans accès aux questions d'évaluation.
COHERENT='''Découpe le texte brut en passages thématiques cohérents et retourne uniquement {"passages":[{"title":"titre neutre","text":"texte exact"}]}.
Recopie tout le texte dans l'ordre, sans omission ni reformulation, séparateurs compris.
Les retours à la ligne peuvent venir de la mise en page PDF : ils ne délimitent PAS les sujets.
Ne coupe JAMAIS une phrase au milieu, même à un retour à la ligne. Conserve dans le même passage une information et ses réserves, son identité, ses négations, ses corrections ou son degré de certitude.
Regroupe plusieurs phrases sur le même sujet. Un titre ou intertitre doit rester avec le contenu qu'il annonce, jamais isolé. Les éléments de pagination peuvent accompagner le passage adjacent.
Ne crée pas de faits ; les titres sont descriptifs. Ne mélange pas des sujets distincts pour réduire artificiellement le nombre de passages.
'''
(OUT/'coherent_prompt.txt').write_text(COHERENT)
novel=[
('N01','DOS001','Marwa Sahel', 'Déplacement et vérification\nUn chauffeur pense avoir aperçu Marwa Sahel près du pont des Aulnes le 3 mars. Il faisait nuit et il ne reconnaît pas son visage avec certitude. Une passagère conteste cette identification.\n\nRegistre\nLe registre du foyer ne mentionne pas Marwa. Deux pages du registre sont manquantes.', [('Où le chauffeur situe-t-il Marwa et avec quelle certitude ?',['pont des Aulnes','ne reconnaît pas son visage avec certitude']),('Pourquoi l’absence de Marwa dans le registre ne suffit-elle pas à conclure ?',['ne mentionne pas Marwa','Deux pages du registre sont manquantes'])]),
('N02','DOS002','Marwa Sahel','Identité vérifiée\nMarwa Sahel a été reçue au dispensaire de Valbois le 11 avril. Son identité a été vérifiée avec une pièce officielle. Ce dossier est distinct de celui du pont des Aulnes.\n\nRendez-vous\nUne consultation de suivi est prévue lundi à 10 h.', [('Où Marwa a-t-elle été reçue et comment son identité a-t-elle été contrôlée ?',['dispensaire de Valbois','pièce officielle']),('Quand est prévu le suivi médical de Marwa ?',['lundi à 10 h'])]),
('N03','DOS001','Théo Leroux','Rectification de date\nLa fiche de Théo Leroux mentionne une disparition le 16 août. Selon sa mère, le 16 août correspond uniquement à la réception d’une lettre. La date de disparition demeure inconnue.\n\nAffaires\nLe manteau de Théo a été confié à son cousin Idriss.', [('Le 16 août est-il la date de disparition confirmée de Théo ?',['réception d’une lettre','date de disparition demeure inconnue']),('À qui le manteau de Théo a-t-il été remis ?',['son cousin Idriss'])]),
('N04','DOS002','Aïcha Benali','Pièce médicale\nUn certificat d’hospitalisation concerne une personne nommée Aïcha Benali à Montclair. L’âge inscrit diffère de celui de la personne recherchée. Le lien entre le certificat et la personne recherchée n’est pas établi.\n\nConservation\nL’original est conservé aux archives du dispensaire.', [('Le certificat permet-il de confirmer l’hospitalisation d’Aïcha recherchée ?',['L’âge inscrit diffère','n’est pas établi']),('Où se trouve l’original du certificat ?',['archives du dispensaire'])]),
('N05','DOS001','Paul Morel','Informations contradictoires\nUn ancien gardien affirme que Paul Morel était au centre de Rosières. La direction du centre déclare ne pas disposer de son nom dans ses listes. Aucun document indépendant ne permet de trancher entre ces déclarations.\n\nEntretien\nLa sœur de Paul sera entendue vendredi à 9 h.', [('La présence de Paul au centre de Rosières est-elle établie ?',['gardien affirme','ne pas disposer de son nom','ne permet de trancher']),('Quand aura lieu l’audition de la sœur de Paul ?',['vendredi à 9 h'])]),
('N06','DOS002','Nora Diallo','Contacts familiaux\nNora Diallo est la tante de la personne recherchée. Elle est joignable par courrier au bureau de Belrive. Elle n’est pas elle-même signalée disparue.\n\nDépôt\nNora a remis trois photographies sans date au bureau.', [('Nora est-elle la personne disparue ou un contact familial ?',['la tante','n’est pas elle-même signalée disparue']),('Quels documents Nora a-t-elle déposés ?',['trois photographies sans date'])]),
('N07','DOS001','Lucien Roux','Chronologie\nLe rapport sur Lucien Roux a été rédigé le 20 janvier. Le témoin situe sa dernière rencontre avec Lucien durant la semaine précédente, sans jour précis. La date de rédaction ne correspond donc pas à une date de disparition établie.\n\nSource\nLe témoignage a été recueilli par téléphone.', [('Le 20 janvier permet-il de dater la disparition de Lucien ?',['date de rédaction','pas à une date de disparition établie']),('Comment le témoignage sur Lucien a-t-il été recueilli ?',['par téléphone'])]),
('N08','DOS002','Mina Sorel','Attestation\nUne attestation de décès sans photographie porte le nom Mina Sorel. La famille précise que deux personnes du village portent ce nom. Aucune pièce ne permet actuellement de déterminer laquelle est concernée.\n\nCopie\nUne copie est disponible à la mairie de Fontenay.', [('L’attestation de Mina permet-elle d’identifier la personne décédée ?',['deux personnes du village','déterminer laquelle est concernée']),('Où consulter une copie de cette attestation ?',['mairie de Fontenay'])]),
('N09','DOS001','Solène Armand','Vérification de la dernière présence\nSolène Armand travaillait dans un atelier de réparation à Villehaute. Son responsable a d’abord déclaré qu’elle avait quitté cet atelier le 12 novembre. Lors du premier entretien, il a expliqué se souvenir de cette date parce qu’une livraison de matériel avait eu lieu ce jour-là. Les enquêteurs ont ensuite demandé à consulter le carnet des livraisons et les feuilles de présence de la même période. Le carnet confirme la livraison, mais ne contient aucune indication sur les personnes présentes. Les feuilles de présence ont été conservées dans un autre bâtiment et plusieurs d’entre elles ont été abîmées par une fuite d’eau. Une collègue indique avoir croisé Solène près de la porte de l’atelier après cette livraison, sans pouvoir préciser si cela s’est produit le jour même ou durant la semaine suivante. Le responsable a finalement rectifié son premier récit : le 12 novembre est la date de la livraison, pas une date certaine de dernière présence de Solène. La dernière présence de Solène et sa date de disparition restent indéterminées.\n\nPièce disponible\nLe carnet des livraisons peut être consulté au dépôt municipal.', [('Pourquoi le 12 novembre ne permet-il pas de dater la disparition de Solène ?',['date de la livraison','pas une date certaine','restent indéterminées']),('Où consulter le carnet des livraisons ?',['dépôt municipal'])]),
('N10','DOS002','Adam Vasseur','Witness statement\nA passenger believes he saw Adam Vasseur near the railway station in Oakford. The passenger did not speak to him and could not confirm his identity. The report does not establish that Adam was at the station.\n\nPersonal belongings\nAdam’s notebook was handed to his brother Marc.', [('Où un passager pense-t-il avoir aperçu Adam et est-ce confirmé ?',['railway station in Oakford','could not confirm his identity']),('Qui a reçu le carnet d’Adam ?',['his brother Marc'])]),
]
fields=json.loads((ROOT/'data/documents.json').read_text())
people={p['person_id']:p['display_name'] for p in json.loads((ROOT/'data/catalog_seed.json').read_text())['persons']}
docs={}
for r in fields:
 docs[r['document_id']]=dict(id=r['document_id'],dossier='DOS001' if int(r['person_id'][1:])<=4 else 'DOS002',text=r['value'],kind='field',field_id=str(r['id']),embedding=make_text(r),context=f"Personne : {people[r['person_id']]}. {make_text(r)}")
old=json.loads((ROOT/'experiments/query_rewriting/results/v4/report.json').read_text())
cases=[]
for i,r in enumerate(old):
 if 'expected_ids' in r:
  doc=next(d for d in docs.values() if d['field_id']==r['expected_ids'][0]);fragments=[doc['text']]
 else:
  doc={'id':r['document']};fragments=r['fragments']
 cases.append(dict(id=f'E{i+1:02}',question=r['question'],dossier=r['dossier_id'],document=doc['id'],fragments=fragments,group='historical' if 'expected_ids' in r else 'pdf',rewrite=r['rewrite']['query']))
artifact_path=ROOT/'web_data'/f"{cases[-1]['document']}.json"
a=json.loads(artifact_path.read_text())
docs[cases[-1]['document']]=dict(id=cases[-1]['document'],dossier='DOS001',text=a['text'],kind='pdf',current=a['segmentation']['document']['passages'])
for id,dossier,name,text,questions in novel:
 docs[id]=dict(id=id,dossier=dossier,text=text,kind='text')
 for n,(q,f) in enumerate(questions):cases.append(dict(id=f'{id}-{n}',question=q,dossier=dossier,document=id,fragments=f,group='novel'))
client=OllamaClient(OllamaConfig(timeout_seconds=90.0,num_predict=8192))
cache_path=OUT/'preparation_cache.json'
cache=json.loads(cache_path.read_text()) if cache_path.exists() else {}
def save():cache_path.write_text(json.dumps(cache,ensure_ascii=False,indent=2))
for d in docs.values():
 if d['kind']=='field':continue
 for mode,prompt in [('current',(ROOT/'prompts/segmentation/v2-exemples.txt').read_text()),('coherent',COHERENT)]:
  if mode in d:continue
  key=hashlib.sha256((prompt+d['text']).encode()).hexdigest()
  if key not in cache:
   run=segment_document(d['text'],DocumentMetadata(document_id=d['id'],dossier_id=d['dossier'],source_kind=d['kind'],source_path='benchmark'),client,prompt=prompt,prompt_version=mode,restore_separators=True)
   cache[key]=run.model_dump();save()
  run=cache[key];d[mode]=run['document']['passages'];d[mode+'_status']=run['document']['status']
  if mode=='coherent':
   for attempt in reversed(run['attempts']):
    if not attempt.get('generation'): continue
    try:
     recovered,gaps=recover_boundaries(d['text'],attempt['generation']['content'])
     d[mode]=recovered;d[mode+'_status']='source_anchored';d['restored_gap_characters']=gaps
     break
    except ValueError: pass
  assert ''.join(p['text'] for p in d[mode])==d['text']
  print(d['id'],mode,len(d[mode]),d[mode+'_status'],flush=True)
for c in cases:
 source=docs[c['document']]['text'];spans=[]
 for fragment in c['fragments']:
  match=re.search(r'(?<!\w)' + r'\s+'.join(re.escape(w) for w in fragment.split()) + r'(?!\w)',source)
  if not match:raise ValueError((c['id'],fragment))
  spans.append([match.start(),match.end()])
 c['evidence']=spans
 if 'rewrite' not in c:
  key=hashlib.sha256((PROMPT+c['question']).encode()).hexdigest()
  if key not in cache:
   try:
    generation=client.generate(PROMPT,c['question'],SearchQuery.model_json_schema())
    q=SearchQuery.model_validate_json(generation.content).query.strip();validate_rewrite(c['question'],q)
    cache[key]={'query':q,'raw':generation.content}
   except Exception as exc:cache[key]={'query':c['question'],'error':str(exc)}
   save()
  c['rewrite']=cache[key]['query']
corpus=dict(documents=list(docs.values()),cases=cases,coherent_prompt=COHERENT,models={n:r for n,r in client.loaded_models().items()})
(OUT/'corpus.json').write_text(json.dumps(corpus,ensure_ascii=False,indent=2))
print('Corpus figé :',len(docs),'documents,',len(cases),'questions.',flush=True)
