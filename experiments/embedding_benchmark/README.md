# Banc de comparaison des embeddings

Ce banc isolé sert à comparer les préparations et modèles sur un corpus fictif figé. La référence de l'application est **BGE-M3 avec contexte + cohérent** ; le banc ne reconstruit pas son index.

## Évaluation BGE-M3

Depuis la racine, avec les dépendances et les poids BGE-M3 présents :

```bash
.venv/bin/python experiments/embedding_benchmark/run.py --model bge-m3
```

Le corpus versionné `corpus.json` permet d'exécuter la recherche sans recontacter Qwen. Les collections de comparaison sont en mémoire et les sorties dans `results/`, ignoré par Git. Les quatre préparations et les questions déjà reformulées du corpus sont celles du protocole figé ; ce n'est pas une évaluation de bout en bout des prompts actuels.

Les révisions, profils et limites de la série sont dans le [protocole historique](../../wiki/history/embedding-benchmark-protocole.md), et les mesures du 23 novembre dans les [résultats archivés](../../wiki/history/embedding-benchmark-resultats.md). Les variantes appelées `actuel` dans le script désignent la préparation de départ de cette ancienne comparaison.

`download_models.py` télécharge plusieurs modèles de comparaison. Pour installer seulement le modèle applicatif, suivre le [guide BGE-M3](../../README-web.md#installation). `summarize.py` attend les sorties de la comparaison complète et régénère un `RESULTATS.md` ; ne pas présenter ce fichier comme une validation de la version courante sans examiner son manifeste.
