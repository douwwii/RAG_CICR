# Benchmark croisé des embeddings et de la préparation documentaire

Le benchmark utilise exclusivement des données fictives. Les scripts n’écrivent jamais dans le catalogue ou Qdrant de l’application. Chaque collection de comparaison réside en mémoire, avec filtrage par dossier avant sélection des cinq résultats.

## Protocole figé

- 59 documents : 48 champs historiques, le PDF fictif déjà indexé (deux pages), dix nouveaux documents courts ou longs.
- 60 questions : 32 historiques, huit sur le PDF, vingt nouvelles (homonymes entre dossiers, négations, dates rectifiées, attribution d’affaires personnelles, long paragraphe et anglais interrogé en français).
- Trois modèles, révisions épinglées : MiniLM multilingue L12-v2, BAAI/bge-m3 et Qwen/Qwen3-Embedding-0.6B.
- Quatre préparations : actuelle ; ajout du nom explicite dans les embeddings des champs historiques ; découpage thématique corrigé des documents ; les deux corrections ensemble.
- Deux formes de question : originale, ou reformulation Qwen V4 validée. Total : 24 configurations et 1 440 recherches.
- Aucun réglage des modèles ni des prompts après consultation de leurs classements. Les vingt nouvelles questions n’ont pas servi à ajuster les prompts ; il s’agit néanmoins d’un petit corpus construit pour diagnostiquer nos défauts, pas d’une validation représentative du CICR.

Les résultats finaux et leur interprétation sont dans [RESULTATS.md](RESULTATS.md) ; la matrice chiffrée est exportée dans `results/comparison.csv`.

La préparation « contexte » ajoute seulement la personne explicitement associée aux champs JSON. Elle n’ajoute aucun nom inféré aux passages PDF ou TXT. Tous les modèles reçoivent le même contenu dans une condition donnée ; leurs tokenizers déterminent ensuite les éventuelles subdivisions techniques.

Le découpage corrigé provient de Qwen, avec consigne de préserver les phrases et leurs réserves. Un ancrage expérimental retrouve les textes proposés en ignorant uniquement les différences d’espacement. Les frontières sont projetées dans le texte original ; les zones omises par Qwen, notamment des en-têtes, sont conservées et rattachées au passage adjacent. Les intertitres courts isolés sont rattachés au contenu suivant. Aucun texte proposé par le LLM n’est affiché à la place du texte source. Les omissions restaurées et les sorties brutes sont consignées. Cet algorithme reste expérimental et n’a pas été installé dans l’ingestion de l’application.

## Mesures

Les preuves sont annotées avant la comparaison et repérées par positions dans chaque source. La recherche d’une preuve impose des frontières de mot : « établi » ne peut pas être validé par « établie ». Les passages d’un autre document ne satisfont jamais une preuve.

- Premier résultat complet : toutes les preuves requises sont présentes dans le premier extrait.
- Couverture à cinq : l’union des positions des cinq résultats contient toutes les preuves requises du bon document.
- Rappel des preuves : fraction moyenne des preuves couvertes, avec crédit partiel pour une preuve fragmentée.
- MRR à cinq : inverse du rang du premier passage complet, zéro si absent.
- Présence du bon document, volume de texte retourné, nombre de vecteurs, latence médiane/P95 d’encodage de requête et médiane de recherche.

Les passages longs peuvent naturellement contenir davantage de preuves : le volume de texte retourné est donc rapporté et le score au premier rang ne doit pas être interprété seul. Le benchmark ne mesure ni la génération de réponses, ni l’abstention sur une question sans réponse, ni les PDF numérisés. Il utilise la recherche dense, pas les fonctionnalités sparse/multivecteurs de BGE-M3 et pas de reranker.

## Exécution

Les dépendances du projet et les modèles téléchargés en cache sont nécessaires. Les révisions et les profils réellement utilisés figurent dans chaque sortie. Les gros modèles sont chargés un par un, sur CPU, en float32, avec quatre threads et un batch de quatre documents. Le prompt de requête fourni par le modèle est utilisé lorsqu’il existe ; les résultats ne dépendent pas d’une troncature silencieuse.

Le fichier `corpus.json` versionné fige les 59 sources fictives, les deux segmentations, les questions originales/reformulées et les preuves. Il permet de relancer les comparaisons sans appeler Qwen ni disposer des imports locaux. `run.py` le copie dans `results/` si ce répertoire ne contient pas déjà un corpus.

Depuis la racine :

```bash
.venv/bin/python experiments/embedding_benchmark/download_models.py
.venv/bin/python experiments/embedding_benchmark/run.py --model minilm
.venv/bin/python experiments/embedding_benchmark/run.py --model bge-m3
.venv/bin/python experiments/embedding_benchmark/run.py --model qwen-0.6b
.venv/bin/python experiments/embedding_benchmark/summarize.py
```

Les sorties locales se trouvent dans `results/` (ignoré par Git) : corpus et preuves figés, générations brutes, caches de vecteurs liés au profil, profils/version des encodeurs, classements par question et statistiques. `prepare.py` réutilise les générations déjà obtenues ; une nouvelle série nécessite un autre cache. Les temps de téléchargement et de segmentation ne sont pas inclus dans les latences de recherche. Les latences Qwen de reformulation et le chargement à froid doivent être ajoutés au temps ressenti dans l’application.

Les tests `tests/test_embedding_benchmark.py` vérifient les unions d’intervalles, l’isolation des preuves par document et la fidélité de l’ancrage. Le socle applicatif et son encodeur ne sont pas remplacés par ces scripts.

Pour renouveler explicitement les segmentations et les reformulations, `prepare.py` utilise le tunnel Ollama, les résultats de l’évaluation précédente et l’artefact PDF de l’application présents sur ce poste. Cette préparation est distincte de la reproduction du benchmark figé.
