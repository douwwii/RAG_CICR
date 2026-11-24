# Reranking Qwen — résultats du 24 novembre 2026

Réglage retenu sur les six cas de calibration : **30 candidats**. Il est ensuite figé pour les dix-huit autres questions, dont douze cas de réserve. Quatre dossiers fictifs, 128 passages, 24 questions, identifiants opaques.

## Choix du nombre de candidats

| Candidats | Premier utile (5 questions avec réponse) | Toutes les preuves parmi 5 | NDCG@5 | Temps Qwen médian |
| --- | ---: | ---: | ---: | ---: |
| 20 | 5/5 | 5/5 | 0.995 | 15.4 s |
| 25 | 5/5 | 5/5 | 0.995 | 17.5 s |
| 30 | 5/5 | 5/5 | 0.995 | 10.8 s |

## Comparaison avec la version actuelle

| Ensemble | Méthode | Premier utile | Toutes les preuves parmi 5 | NDCG@5 |
| --- | --- | ---: | ---: | ---: |
| Calibration | Cosinus seul | 1/5 | 1/5 | 0.210 |
| Calibration | Cosinus dédoublonné | 1/5 | 4/5 | 0.546 |
| Calibration | Qwen | 5/5 | 5/5 | 0.995 |
| Validation | Cosinus seul | 3/15 | 4/15 | 0.240 |
| Validation | Cosinus dédoublonné | 3/15 | 11/15 | 0.565 |
| Validation | Qwen | 15/15 | 15/15 | 0.987 |
| Réserve seule | Cosinus seul | 2/10 | 2/10 | 0.210 |
| Réserve seule | Cosinus dédoublonné | 2/10 | 7/10 | 0.552 |
| Réserve seule | Qwen | 10/10 | 10/10 | 0.989 |
| Total | Cosinus seul | 4/20 | 5/20 | 0.233 |
| Total | Cosinus dédoublonné | 4/20 | 15/20 | 0.560 |
| Total | Qwen | 20/20 | 20/20 | 0.989 |

## Questions sans réponse et fiabilité

- Sur les 3 questions sans réponse de validation, 3 sont signalées sans réponse explicite (`none` ou `context`).
- 0 replis sur le cosinus parmi les 24 analyses au nombre de candidats retenu.
- 1 analyse(s) nécessitent une seconde tentative structurée. Les sorties du premier appel restent dans le cache brut.
- 0/3 questions de validation avec témoignages contradictoires reçoivent le diagnostic global `contradictory`.
- Le premier résultat utile signifie un passage annoté comme réponse directe ou élément nécessaire. Ce n’est pas une affirmation de vérité des faits.
- La couverture ne compte que les questions avec réponse ; les questions sans réponse sont comptées séparément.
- Les identifiants sont contrôlés, les textes proviennent des candidats vérifiés, le dossier est filtré avant la recherche. Le bilan affiché décrit les catégories de pertinence ; il ne paraphrase pas librement les faits.

## Sensibilité à l’ordre des candidats

- CAL-A-death : couverture True → True, NDCG 0.991 → 0.991, 3/5 passages conservés.
- CAL-A-conflict : couverture True → True, NDCG 1.000 → 1.000, 4/5 passages conservés.
- TEST-A-death : couverture True → True, NDCG 0.991 → 0.991, 4/5 passages conservés.
- TEST-A-conflict : couverture True → True, NDCG 1.000 → 1.000, 3/5 passages conservés.

## Latence et limites

Temps Qwen médian au réglage retenu : 19.7 s. Ces temps incluent l’appel de classement enregistré, pas l’encodage, la reformulation ou toute l’attente HTTP de l’interface. La première recherche peut être plus lente sur la machine partagée ; le cache réutilise les analyses réussies lorsque l’entrée effective du reranker est identique.
Sur les dix-huit questions de validation : médiane 20.1 s, maximum 40.3 s, tentatives supplémentaires incluses.

Les trois tailles ont été appelées dans l’ordre 20, 25 puis 30. Le cache de préfixe du serveur peut favoriser les derniers appels. Leur qualité étant identique sur ces six cas, le départage par temps ne démontre ni un optimum universel à 30 ni un avantage intrinsèque de vitesse.

Ce corpus est volontairement adversarial : plusieurs copies proches du mauvais événement ou du mauvais homonyme peuvent occuper les premières places cosinus. Le contrôle dédoublonné mesure une alternative sans LLM. Les dossiers répètent des patrons proches ; les résultats de réserve ne constituent pas une validation indépendante sur de vrais documents CICR. Les passages sont annotés et prédécoupés pour isoler le classement, sans mesurer toute l’ingestion PDF.

Les scores de pertinence sont comparés à des annotations définies avant les essais, pas au seul avis de Qwen. Les catégories et justifications du modèle restent faillibles. La normalisation du bilan empêche les nouvelles paraphrases factuelles, mais ne rend pas le jugement de pertinence infaillible.

## Traçabilité

Les versions pilotes V1 (citations et résumé libre) et V2 à identifiants descriptifs ont servi à détecter des défauts avant la série finale : latence, perte de conditionnel, citations dont les espaces diffèrent des PDF et indices sémantiques dans les identifiants. Elles sont archivées séparément et ne sont pas mélangées aux chiffres ci-dessus. Le prompt V2 final et les UUID opaques sont figés pour la comparaison finale.

Un identifiant mal recopié sur CAL-B a motivé l’ajout d’une unique nouvelle tentative, avec les identifiants candidats énumérés dans le schéma. La politique finale a été réévaluée en rejouant les générations brutes mises en cache et en effectuant réellement les nouveaux appels de correction nécessaires. Aucun texte, classement annoté ou prompt sémantique de réserve n’a été modifié pour améliorer ces scores.

Voir `corpus.json`, `results/manifest.json`, `results/report.json`, `results/generations.json`, `results/selection.json` et `results/dedup_baseline.json`. Aucun index applicatif n’a été modifié pour produire ces mesures.
