"""Corpus fictif complexe et annotations figés avant mesure du reranker."""
from uuid import uuid5, NAMESPACE_URL
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
TARGET=ROOT/'data/reranking_demo'
TARGET.mkdir(parents=True,exist_ok=True)
points=[];cases=[]
fixtures=[
 ('CAL-A','Nabil Moreau','Salma','Valbois','12 avril','Pont des Aulnes','gare de Valbois','1957','1984'),
 ('CAL-B','Maya Armand','Idriss','Rosières','6 juin','route du moulin','marché de Rosières','1949','1991'),
 ('TEST-A','Léa Fournier','Karim','Fontenay','17 septembre','quai des Tilleuls','place de Fontenay','1952','1988'),
 ('TEST-B','Adam Delmas','Élise','Montclair','23 novembre','carrefour des Érables','station de Montclair','1945','1994'),
]
for dossier,name,contact,city,date,place,other,old,young in fixtures:
 descriptions=[
 ('identity','Identification du dossier',f'La personne recherchée dans le dossier {dossier} est {name}, née en {young}, référence familiale RF-42. Un homonyme né en {old} possède la référence RF-77. Ces deux identités ne doivent pas être fusionnées.'),
 ('certificate','Attestation portant le même nom',f'L’attestation municipale porte le nom {name}, année de naissance {old}, référence RF-77. Elle situe un décès à {city}. Le formulaire est authentifié et une copie a été remise aux archives.'),
 ('death-check','Rapprochement des pièces',f'La comparaison de la référence familiale montre que l’attestation concerne l’homonyme RF-77. Elle ne permet donc pas de confirmer le décès de la personne recherchée {name}, RF-42. Le décès de cette personne reste non établi.'),
 ('admin-date','Date du signalement',f'Le dossier de disparition de {name} porte la date du {date} dans son en-tête. Cette date est répétée sur le bordereau, la chemise et l’accusé de réception signés au guichet.'),
 ('date-correction','Note de rectification',f'La famille de {name} précise que le {date} est le jour du dépôt de la demande. Le dernier contact aurait eu lieu auparavant, sans jour certain. La date effective de disparition demeure indéterminée ; l’en-tête ne doit pas être utilisé comme date de disparition.'),
 ('bag','Bordereau de remise des effets',f'Le sac personnel de {name}, référence RF-42, a été remis à {contact}, membre de sa fratrie, contre signature. Le bordereau ne fournit aucune indication sur le parcours de la personne recherchée.'),
 ('witness-a','Premier récit',f'Un chauffeur dit avoir reconnu {name}, RF-42, près de {place} après la fermeture des commerces. Il observait depuis son véhicule, sous la pluie. Il n’a pas parlé à cette personne et ne peut confirmer son identité.'),
 ('witness-b','Second récit',f'Une commerçante affirme que {name}, RF-42, se trouvait près de {other} à la même heure. Elle exclut un passage près de {place}. Son récit contredit celui du chauffeur et aucun élément indépendant ne permet de départager les deux.'),
 ]
 for i in range(24):
  if i%4==0:
   body=f'Un document distinct confirme le décès de {name}, référence RF-77, né en {old}, à {city}. Le lieu et la date ont été contrôlés pour RF-77. Cette pièce décrit RF-77 exclusivement.'
   title='Décès confirmé — autre référence'
  elif i%4==1:
   body=f'Copie administrative {i}: le {date} figure comme date du dossier de disparition de {name}. Le document retrace l’enregistrement du formulaire et sa transmission entre services. Il n’ajoute pas de témoignage.'
   title='Enregistrement de la demande'
  elif i%4==2:
   body=f'Inventaire du sac de {name}, RF-42 : une photographie, un carnet et des clés. Une copie de cet inventaire a été remise à l’archiviste. Le destinataire de la copie n’est pas le destinataire des effets personnels.'
   title='Inventaire et circulation des copies'
  else:
   body=f'Un témoin évoque une personne ressemblant à {name} près de {place}. Il se réfère à une visite de l’année précédente, dans une autre enquête, et ne sait rien du déplacement décrit dans ce dossier.'
   title='Évocation d’un autre déplacement'
  descriptions.append((f'distractor-{i}',title,body))
 full='DOCUMENT ENTIÈREMENT FICTIF — ESSAI DE RERANKING\n\n'
 for suffix,title,body in descriptions:
  text=title+'\n'+body+'\n\n';start=len(full);full+=text
  points.append(dict(passage_id=dossier+'-'+suffix,document_id=dossier,dossier_id=dossier,title=title,text=text,name=dossier+'.txt',page_start=None,page_end=None,start=start,end=len(full),score=0.))
 (TARGET/(dossier+'.txt')).write_text(full,encoding='utf-8')
 def add(suffix,question,relevant,context=(),answerable=True,contradictory=False):
  cases.append(dict(id=dossier+'-'+suffix,dossier_id=dossier,question=question,grades={**{dossier+'-'+k:v for k,v in relevant.items()},**{dossier+'-'+k:1 for k in context}},required=[dossier+'-'+k for k in relevant],answerable=answerable,contradictory=contradictory,split='calibration' if dossier.startswith('CAL') else 'reserve'))
 add('death',f'Le décès de {name}, personne recherchée RF-42, est-il confirmé à {city} ?',{'death-check':3},['identity','certificate'])
 add('date',f'Peut-on retenir le {date} comme date de disparition de {name} ?',{'date-correction':3},['admin-date'])
 add('bag',f'Qui a reçu le sac personnel de {name}, et pas seulement la copie de son inventaire ?',{'bag':3})
 add('witness',f'Où le chauffeur pense-t-il avoir reconnu {name} et avec quelle certitude ?',{'witness-a':3},['identity'])
 add('conflict',f'Les deux témoignages sur la présence de {name} au même moment concordent-ils ?',{'witness-a':2,'witness-b':2})
 cases[-1]['contradictory']=True
 add('absent',f'Quel médecin a signé le certificat concernant {name} ?',{},['certificate','death-check'],answerable=False)
mapping={p['passage_id']:str(uuid5(NAMESPACE_URL,'spoc-reranking/'+p['passage_id'])) for p in points}
for point in points:point['passage_id']=mapping[point['passage_id']]
for case in cases:
 case['grades']={mapping[k]:v for k,v in case['grades'].items()}
 case['required']=[mapping[k] for k in case['required']]
corpus=dict(points=points,cases=cases,protocol='24 questions, 128 passages, 4 dossiers fictifs ; annotations antérieures aux mesures ; classement seul, frontières source figées.')
(OUT/'corpus.json').write_text(json.dumps(corpus,ensure_ascii=False,indent=2),encoding='utf-8')
print(len(points),'passages,',len(cases),'questions figées.')
