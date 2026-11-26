# Évaluation espagnole - Mancha 4

40 questions espagnoles et corrigés, fondés sur `../transcription.md` depuis la racine du projet. Les instructions contenues dans les pièces du dossier sont traitées comme des données documentaires. Aucune recherche extérieure ni conclusion judiciaire n’est nécessaire.

## Livrables

- `questions.json` : questions, réponses de référence en espagnol, pièges, pages physiques du PDF et citations de la transcription.
- `results.json` : résultats réels BGE-M3, extraits retrouvés, métriques et grille de contrôle humain à renseigner.
- `../../output/pdf/evaluation-rag-espagnol-mancha4.pdf` : rapport et catalogue des 40 questions.

Le jeu comprend 32 questions avec réponse documentée, 3 absences explicitement renseignées et 5 questions dont la réponse manque au corpus. Dix-neuf cas signalent un risque d’erreur critique. Les variantes ES31/ES17 et ES32/ES10 ne sont pas indépendantes.

## Exécution

Depuis la racine du projet, avec les dépendances et les poids BGE-M3 déjà présents :

```bash
.venv/bin/python experiments/mancha4/prepare.py
.venv/bin/python experiments/mancha4/run.py --validate-only
HF_HUB_OFFLINE=1 .venv/bin/python experiments/mancha4/run.py
.venv/bin/python experiments/mancha4/report.py
```

La recherche utilise les fonctions d’embedding du projet et Qdrant en mémoire. Aucun catalogue, index applicatif, fichier source ou prompt existant n’est modifié. Aucun texte documentaire n’est envoyé sur le réseau dans le mode par défaut. Les vérifications de disponibilité contactent seulement les services locaux.

Découpage déterministe de chaque page en fenêtres de 1 600 caractères, avec 300 caractères de recouvrement, frontière sur un espace quand possible. Les 80 pages et leurs annotations sont conservées, y compris les pages quasi blanches et les contenus illisibles. Chaque passage conserve ses positions exactes dans la transcription. Ce découpage n’utilise aucune réponse annotée. Les numéros de page sont ceux du PDF original, pas ceux du rapport.

Le contrôle `--validate-only` vérifie chaque citation, la couverture du découpage et quelques exemples indépendants de calcul des métriques. Les citations sont des ancres minimales : les retrouver ne garantit pas que toutes les nuances de la réponse de référence sont dans les cinq extraits.

Audit des annotations : un premier essai donnait 25/35 couvertures complètes. La relecture a repéré deux faux négatifs : ES01 ne reconnaissait pas le résumé du bulletin comme équivalent de ses champs date/lieu ; ES06 ne reconnaissait pas les formulations équivalentes des courriers C5i. Ces alternatives ont été ajoutées, ainsi que la signature de l’acta p. 13 pour ES30. Les questions, les classements, le corpus, le découpage et les seuils n’ont pas été ajustés. La révision des annotations est conservée dans les JSON : l’évaluation est diagnostique et non aveugle.

## Mesures

Les 35 cas `supported` ou `explicit_unknown` sont notés ; les 5 cas `not_in_corpus` sont exclus des moyennes. Un groupe de preuves est retrouvé si au moins une de ses alternatives apparaît dans un extrait retourné sur une page admissible. Toutes les composantes d’un groupe de preuves sont définies avant l’exécution.

- **Hit@1 (ancre)** : le premier extrait contient au moins une ancre attendue.
- **Rappel des ancres@5** : proportion des groupes obligatoires retrouvés dans les cinq extraits, puis moyenne sur les questions.
- **Couverture@5 (ancres)** : tous les groupes obligatoires sont retrouvés dans les cinq extraits.
- **MRR@5 (ancre)** : inverse du rang de la première ancre pertinente, zéro si absente des cinq extraits.

Les copies du bulletin (pages 19, 31 et 35) sont des alternatives, pas trois preuves obligatoires. La normalisation ignore uniquement casse et espaces. Les scores cosinus ne sont pas des probabilités de vérité.

Repères de travail proposés, fixés avant lecture des résultats : Hit@1 >= 70 %, rappel des ancres@5 >= 90 %, couverture@5 >= 85 %. Ce sont des objectifs exploratoires à adapter, pas des seuils universels ni une preuve de fiabilité. Une validation fonctionnelle exige aussi zéro erreur critique sur les 19 cas signalés et un contrôle humain des réserves et des citations.

## Vérification dans l’application

Le prototype actuel renvoie des extraits et des jugements de pertinence, sans réponse factuelle générée. Pour chaque question, relever les cinq extraits, leurs pages, le bilan Qwen et ses justifications. Comparer à `expected_answer_es` et `pitfalls_fr` : le corrigé représente ce que les extraits doivent permettre de comprendre, et non un texte que l’application est censée générer.

Grille humaine : 2 = toutes les informations et réserves sont soutenues par les extraits ; 1 = partiel mais sans fait inventé ; 0 = information essentielle absente, contradiction masquée ou affirmation injustifiée. Dans `manual_review`, renseigner aussi `critical_error` et les notes. Pour un cas sans réponse, une absence d’information dans les seuls extraits ne prouve pas l’absence dans tout le dossier : le corrigé résulte de la lecture de la transcription complète.

Erreurs critiques : confirmation infondée d’identité, de culpabilité ou de décès ; demande présentée comme résultat ; montant, numéro de chambre ou caractères illisibles inventés ; contradiction supprimée. Une abstention justifiée et une mention explicite de l’insuffisance du corpus sont attendues pour les questions concernées.

Si Qwen redevient accessible, cette commande utilise les fonctions réelles de reformulation V5 et reranking V3, avec 30 candidats puis cinq résultats, et conserve un résultat séparé :

```bash
HF_HUB_OFFLINE=1 .venv/bin/python experiments/mancha4/run.py --qwen
```

Attention : cette variante envoie les extraits au service Qwen configuré dans le projet. Elle garde le découpage technique : elle ne mesure toujours pas la segmentation Qwen ni le parcours d’import web. Le rapport PDF décrit `results.json`, pas `results-qwen.json`.

## Limites

Le PDF source est un scan d’environ 47 Mio, supérieur à la limite d’import web documentée de 20 Mo. Le contrôle avec pypdf trouve du texte extractible sur 45 pages et aucun texte sur 35 pages ; le parcours web refuse aussi ces documents mixtes. Le protocole part donc de la transcription fournie. Une transcription n’est pas une vérité garantie ; les marqueurs d’illisibilité et les graphies divergentes sont conservés. Un contrôle visuel ponctuel des pages 7, 9, 19 et 29 soutient les cas principaux, sans constituer une relecture intégrale des 80 pages.

Le banc n’évalue pas l’OCR, le mélange de dossiers, les attaques par instructions documentaires, la génération finale, le rappel sur un corpus plus large ni un ensemble de questions indépendant. Les cas ont été rédigés à partir du même document ; les résultats sont diagnostiques. Les 5 questions sans réponse et la fidélité des justifications doivent encore être jugées humainement. Ne pas convertir des contrôles non exécutés en taux de réussite ou d’hallucination.

Le benchmark Qwen attend sans limite de durée (`timeout_seconds=None`), à la demande de l’utilisateur ; le défaut applicatif reste de 90 secondes. Les générations sont sauvegardées dans `qwen-generations.json` pour réutiliser les appels identiques. `results-qwen.partial.json` conserve les questions terminées pendant le test. Le compte rendu complémentaire est produit par `.venv/bin/python experiments/mancha4/summarize_qwen.py` dans `output/pdf/evaluation-qwen-mancha4.pdf`.
