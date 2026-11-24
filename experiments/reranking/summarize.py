"""Rapport final à partir des essais réellement terminés, avec validation séparée."""
from pathlib import Path
import json,csv,statistics
folder=Path(__file__).resolve().parent;out=folder/'results'
rows=json.loads((out/'report.json').read_text())
if len(rows)!=24:raise SystemExit(f'Benchmark incomplet : {len(rows)}/24 questions.')
selection=json.loads((out/'selection.json').read_text());count=str(selection['candidate_count'])
dedup={r['case_id']:r for r in json.loads((out/'dedup_baseline.json').read_text())}
for r in rows:
 assert r['baseline']==dedup[r['case']['id']]['baseline'],'Baseline différente après recalcul.'
cal=[r for r in rows if r['case']['dossier_id']=='CAL-A']
validation=[r for r in rows if r['case']['dossier_id']!='CAL-A']
reserve=[r for r in rows if r['case']['split']=='reserve']

def summarize(items,get_metrics):
 positive=[r for r in items if r['case']['answerable']]
 values=[get_metrics(r) for r in positive]
 return dict(n=len(positive),hit1=sum(v['hit1'] for v in values),coverage5=sum(v['coverage5'] for v in values),
             ndcg5=statistics.mean(v['ndcg5'] for v in values))
lines=['# Reranking Qwen — résultats du 24 novembre 2026','',
 f'Réglage retenu sur les six cas de calibration : **{count} candidats**. Il est ensuite figé pour les dix-huit autres questions, dont douze cas de réserve. Quatre dossiers fictifs, 128 passages, 24 questions, identifiants opaques.','',
 '## Choix du nombre de candidats','',
 '| Candidats | Premier utile (5 questions avec réponse) | Toutes les preuves parmi 5 | NDCG@5 | Temps Qwen médian |',
 '| --- | ---: | ---: | ---: | ---: |']
for n in ['20','25','30']:
 stats=summarize(cal,lambda r:r['variants'][n]['metrics']);times=[r['variants'][n]['llm_seconds'] for r in cal]
 lines.append(f"| {n} | {stats['hit1']}/{stats['n']} | {stats['coverage5']}/{stats['n']} | {stats['ndcg5']:.3f} | {statistics.median(times):.1f} s |")
lines+=['','## Comparaison avec la version actuelle','',
 '| Ensemble | Méthode | Premier utile | Toutes les preuves parmi 5 | NDCG@5 |',
 '| --- | --- | ---: | ---: | ---: |']
for name,items in [('Calibration',cal),('Validation',validation),('Réserve seule',reserve),('Total',rows)]:
 for method,get in [('Cosinus seul',lambda r:r['baseline']),('Cosinus dédoublonné',lambda r:dedup[r['case']['id']]['deduplicated']),('Qwen',lambda r:r['variants'][count]['metrics'])]:
  stats=summarize(items,get)
  lines.append(f"| {name} | {method} | {stats['hit1']}/{stats['n']} | {stats['coverage5']}/{stats['n']} | {stats['ndcg5']:.3f} |")
negative=[r for r in validation if not r['case']['answerable']]
honest=sum((r['variants'][count]['result']['assessment'] or {}).get('coverage') in {'none','context'} for r in negative)
outputs=[r['variants'][count] for r in rows]
fallbacks=sum(v['result']['reranking']['status']!='applied' for v in outputs)
retries=sum(v['result']['reranking']['calls']>1 for v in outputs)
contradictions=[r for r in validation if r['case'].get('contradictory')]
flagged=sum((r['variants'][count]['result']['assessment'] or {}).get('coverage')=='contradictory' for r in contradictions)
lines+=['','## Questions sans réponse et fiabilité','',
 f'- Sur les {len(negative)} questions sans réponse de validation, {honest} sont signalées sans réponse explicite (`none` ou `context`).',
 f'- {fallbacks} replis sur le cosinus parmi les {len(outputs)} analyses au nombre de candidats retenu.',
 f'- {retries} analyse(s) nécessitent une seconde tentative structurée. Les sorties du premier appel restent dans le cache brut.',
 f'- {flagged}/{len(contradictions)} questions de validation avec témoignages contradictoires reçoivent le diagnostic global `contradictory`.',
 '- Le premier résultat utile signifie un passage annoté comme réponse directe ou élément nécessaire. Ce n’est pas une affirmation de vérité des faits.',
 '- La couverture ne compte que les questions avec réponse ; les questions sans réponse sont comptées séparément.',
 '- Les identifiants sont contrôlés, les textes proviennent des candidats vérifiés, le dossier est filtré avant la recherche. Le bilan affiché décrit les catégories de pertinence ; il ne paraphrase pas librement les faits.']
shuffled=[r for r in rows if 'shuffled_25' in r]
lines+=['','## Sensibilité à l’ordre des candidats','']
for r in shuffled:
 n='25' if r['case']['dossier_id']=='CAL-A' else count
 before=r['variants'][n]['metrics'];after=r['shuffled_25']['metrics']
 a={p['passage_id'] for p in r['variants'][n]['result']['results']};b={p['passage_id'] for p in r['shuffled_25']['result']['results']}
 lines.append(f"- {r['case']['id']} : couverture {before['coverage5']} → {after['coverage5']}, NDCG {before['ndcg5']:.3f} → {after['ndcg5']:.3f}, {len(a&b)}/5 passages conservés.")
lines+=['','## Latence et limites','',
 f"Temps Qwen médian au réglage retenu : {statistics.median(v['llm_seconds'] for v in outputs):.1f} s. Ces temps incluent l’appel de classement enregistré, pas l’encodage, la reformulation ou toute l’attente HTTP de l’interface. La première recherche peut être plus lente sur la machine partagée ; le cache réutilise les analyses réussies lorsque l’entrée effective du reranker est identique.",
 f"Sur les dix-huit questions de validation : médiane {statistics.median(r['variants'][count]['llm_seconds'] for r in validation):.1f} s, maximum {max(r['variants'][count]['llm_seconds'] for r in validation):.1f} s, tentatives supplémentaires incluses.",
 '',
 'Les trois tailles ont été appelées dans l’ordre 20, 25 puis 30. Le cache de préfixe du serveur peut favoriser les derniers appels. Leur qualité étant identique sur ces six cas, le départage par temps ne démontre ni un optimum universel à 30 ni un avantage intrinsèque de vitesse.',
 '',
 'Ce corpus est volontairement adversarial : plusieurs copies proches du mauvais événement ou du mauvais homonyme peuvent occuper les premières places cosinus. Le contrôle dédoublonné mesure une alternative sans LLM. Les dossiers répètent des patrons proches ; les résultats de réserve ne constituent pas une validation indépendante sur de vrais documents CICR. Les passages sont annotés et prédécoupés pour isoler le classement, sans mesurer toute l’ingestion PDF.',
 '',
 'Les scores de pertinence sont comparés à des annotations définies avant les essais, pas au seul avis de Qwen. Les catégories et justifications du modèle restent faillibles. La normalisation du bilan empêche les nouvelles paraphrases factuelles, mais ne rend pas le jugement de pertinence infaillible.',
 '',
 '## Traçabilité','',
 'Les versions pilotes V1 (citations et résumé libre) et V2 à identifiants descriptifs ont servi à détecter des défauts avant la série finale : latence, perte de conditionnel, citations dont les espaces diffèrent des PDF et indices sémantiques dans les identifiants. Elles sont archivées séparément et ne sont pas mélangées aux chiffres ci-dessus. Le prompt V2 final et les UUID opaques sont figés pour la comparaison finale.',
 '',
 'Un identifiant mal recopié sur CAL-B a motivé l’ajout d’une unique nouvelle tentative, avec les identifiants candidats énumérés dans le schéma. La politique finale a été réévaluée en rejouant les générations brutes mises en cache et en effectuant réellement les nouveaux appels de correction nécessaires. Aucun texte, classement annoté ou prompt sémantique de réserve n’a été modifié pour améliorer ces scores.',
 '',
 'Voir `corpus.json`, `results/manifest.json`, `results/report.json`, `results/generations.json`, `results/selection.json` et `results/dedup_baseline.json`. Aucun index applicatif n’a été modifié pour produire ces mesures.']
(folder/'RESULTATS.md').write_text('\n'.join(lines)+'\n')
with (out/'comparison.csv').open('w') as f:
 writer=csv.DictWriter(f,fieldnames=['case_id','phase','answerable','method','hit1','coverage5','ndcg5','seconds'])
 writer.writeheader()
 for r in rows:
  for method,m,seconds in [('cosine',r['baseline'],0),('dedup',dedup[r['case']['id']]['deduplicated'],0),('qwen',r['variants'][count]['metrics'],r['variants'][count]['llm_seconds'])]:
   writer.writerow(dict(case_id=r['case']['id'],phase='calibration' if r in cal else 'validation',answerable=r['case']['answerable'],method=method,hit1=m['hit1'],coverage5=m['coverage5'],ndcg5=m['ndcg5'],seconds=seconds))
print('\n'.join(lines),flush=True)
