"""Rapport des essais terminés ; aucune extrapolation à des PDF réels."""
from pathlib import Path
import json
folder=Path(__file__).resolve().parent
r=json.loads((folder/'results.json').read_text())
assert len(r['cases'])==8,'Essai incomplet'
assert all(c['status']=='applied' and c['source_exact'] for c in r['cases'])
lines=['# Essais multilingues — 25 novembre 2026','',
'Essai réel avec BGE-M3, Qdrant en mémoire et `qwen3.8:27b-mlx` sur le serveur distant. Quatre textes fictifs, douze passages annotés et huit questions. Les textes décrivent une remise de sac, un décès non confirmé lié à un homonyme, et une date administrative distincte de la disparition. Aucun document réel ni index applicatif n’a été modifié.','',
'## Résultats','',
'| Question | Source | Premier passage cosinus correct | Premier passage Qwen correct | Texte source exact |',
'| --- | --- | --- | --- | --- |']
for c in r['cases']:
 lines.append(f"| {c['question_language']} | {c['source_language']} | {c['cosine_first']==c['expected']} | {c['reranked_first']==c['expected']} | {c['source_exact']} |")
lines+=['', 'Le passage attendu est premier dans 8/8 cas, avec le cosinus comme avec Qwen. Les quatre questions entre langues réussissent aussi. Ce corpus simple ne montre donc pas de gain supplémentaire du reranker. Les huit reformulations sont identiques aux questions initiales, déjà claires. Aucun gain de reformulation n’est démontré.','',
'## Découpage','']
for lang,v in r['segmentation'].items():lines.append(f"- {lang} : statut `{v['status']}`, {v['count']} passages, couverture exacte : {v['exact']}.")
lines+=['','La recherche utilise des frontières annotées fixées avant les essais pour isoler le retrieval. La segmentation est évaluée séparément ; ce n’est pas une mesure de bout en bout sur des PDF. Les trois thèmes attendus sont conservés dans chacune des quatre langues.','',
'## Limites observées','',
'- Les raisons libres de Qwen restent en français sur deux cas entre langues malgré la consigne : question anglaise sur source arabe, et question arabe sur source française. Les menus et bilans fixes sont traduits indépendamment ; la langue de ces justifications n’est pas garantie.',
'- Les douze candidats sont tous fournis au reranker. Ces huit cas courts ne mesurent ni le rappel dans un grand dossier, ni les performances à 30 candidats sur documents multilingues longs.',
'- Les négations et homonymes sont présents, mais le corpus est petit et répétitif. Les noms utilisent volontairement des ancres latines ; les variantes de translittération ne sont pas validées.',
'- L’extraction de PDF arabes réels, les mises en page complexes et les scans ne sont pas évalués ici. Les scans restent hors périmètre, sans OCR.',
'- Les traductions d’interface doivent idéalement être relues par des locuteurs, en particulier pour l’arabe.',
'', '## Interface et vérification','',
'Français, anglais, espagnol et arabe, préférence locale persistante, direction RTL en arabe, direction automatique des extraits et question. Vérification navigateur des quatre langues, rechargement avec conservation de la langue arabe et dialogue d’import arabe. Les noms et contenus source restent dans leur langue originale. 145 libellés possèdent les trois traductions. Les erreurs serveur détaillées non répertoriées peuvent rester en français.','',
'## Reproduction','',
'```bash\n.venv/bin/python experiments/multilingual/run.py\n.venv/bin/python experiments/multilingual/summarize.py\nnode frontend/scripts/check-i18n.cjs\n```',
'', 'Les générations réellement obtenues sont mises en cache dans `raw.json` (ignoré par Git), avec leurs durées. Le script réutilise uniquement les réponses ayant exactement la même empreinte prompt/entrée/schéma. `manifest.json` contient les prompts et le profil effectifs ; `corpus.json` les textes et questions ; `results.json` les résultats détaillés et justifications. Aucun modèle simulé n’est utilisé dans cet essai.']
(folder/'RESULTATS.md').write_text('\n'.join(lines)+'\n')
print('Rapport généré : 8 questions, 4 langues, résultats complets.')
