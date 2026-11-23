"""Publier les résultats réellement produits, sans extrapoler les configurations absentes."""
from pathlib import Path
import json,csv
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent/'results'
files=[OUT/(model+'.json') for model in ['minilm','bge-m3','qwen-0.6b']]
if not all(p.exists() for p in files):raise SystemExit('Les trois modèles doivent avoir terminé.')
reports=[json.loads(p.read_text()) for p in files]
assert len({r['corpus_sha256'] for r in reports})==1,'Les corpus comparés diffèrent.'
rows=[]
for report in reports:
 for r in report['results']:
  stats=r['summary']['all']
  rows.append(dict(model=r['model'],preparation=r['variant'],question=r['query_mode'],n=stats['n'],
                   hit1=round(stats['hit1']*stats['n']),coverage5=round(stats['coverage5']*stats['n']),
                   recall=stats['evidence_recall5'],mrr=stats['mrr5'],chars=stats['returned_characters'],
                   points=r['indexed_points'],query_p50_ms=report['query_encode_ms_p50'],query_p95_ms=report['query_encode_ms_p95'],
                   peak_ram_mib=report['peak_process_ram_mib']))
with (OUT/'comparison.csv').open('w') as f:
 writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
lines=['# Résultats du benchmark croisé — 23 novembre 2026','',
 '60 questions fictives, cinq résultats maximum, 24 configurations. Les résultats décrivent ce corpus, sans garantie de généralisation. Aucun changement n’a été appliqué à l’index de l’interface.','',
 '| Modèle | Préparation | Question | Premier complet | Couverture à cinq | Caractères retournés moyens |',
 '| --- | --- | --- | ---: | ---: | ---: |']
for r in rows:
 lines.append(f"| {r['model']} | {r['preparation']} | {r['question']} | {r['hit1']}/60 | {r['coverage5']}/60 | {r['chars']:.0f} |")
lines+=['','## Ressources observées','',
 '| Modèle | Chargement (s) | Requête médiane/P95 (ms) | Pic RAM processus (Mio) |',
 '| --- | ---: | ---: | ---: |']
for report in reports:
 lines.append(f"| {report['model_name']} | {report['load_seconds']:.1f} | {report['query_encode_ms_p50']:.1f} / {report['query_encode_ms_p95']:.1f} | {report['peak_process_ram_mib']:.0f} |")
lines+=['','Mesures CPU float32, quatre threads, batch de quatre. Le pic RAM concerne le processus de benchmark, pas tout le poste. Les encodages de requête sont mesurés à chaud ; ajouter le coût réseau/Qwen pour les requêtes reformulées. Le téléchargement des modèles est exclu.','',
 '## Détail avec contexte et passages cohérents','',
 '| Modèle, avec reformulation | Champs (32) | PDF (8) | Nouveaux cas (20) | Premier complet (60) |',
 '| --- | ---: | ---: | ---: | ---: |']
selected=[]
for report in reports:
 r=next(r for r in report['results'] if r['variant']=='contexte_coherent' and r['query_mode']=='qwen');selected.append(r)
 values=[f"{round(r['summary'][g]['coverage5']*r['summary'][g]['n'])}/{r['summary'][g]['n']}" for g in ['historical','pdf','novel']]
 lines.append(f"| {r['model']} | {' | '.join(values)} | {round(r['summary']['all']['hit1']*60)}/60 |")
lines+=['','## Incertitude des différences','',
 'Bootstrap apparié exploratoire sur les 60 questions (5 000 tirages, graine 42), différence de couverture à cinq par rapport à MiniLM, avec contexte, passages cohérents et reformulation :']
rng=np.random.default_rng(42)
base=np.array([r['metrics']['coverage5'] for r in selected[0]['details']],dtype=float)
for r in selected[1:]:
 assert [d['case_id'] for d in r['details']]==[d['case_id'] for d in selected[0]['details']]
 difference=np.array([d['metrics']['coverage5'] for d in r['details']],dtype=float)-base
 samples=difference[rng.integers(0,len(base),size=(5000,len(base)))].mean(axis=1)
 low,high=np.percentile(samples,[2.5,97.5])*100
 lines.append(f"- {r['model']} : {difference.mean()*100:+.1f} points ; intervalle indicatif [{low:+.1f} ; {high:+.1f}].")
lines+=['','Les patrons de questions répétés et les faits du même document ne sont pas indépendants : cet intervalle n’est pas une garantie statistique sur un corpus réel. Les sorties longues sont avantagées par les métriques de couverture ; comparer aussi les volumes de texte et les exemples d’erreurs.','',
 'Les paramètres, révisions, instructions de requête et profils effectifs sont conservés dans les JSON de chaque modèle. Le corpus, les preuves, les segmentations et leurs sorties Qwen sont conservés séparément. Voir README.md pour le protocole et les limites.']
Path(__file__).with_name('RESULTATS.md').write_text('\n'.join(lines)+'\n')
print('\n'.join(lines),flush=True)
