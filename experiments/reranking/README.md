# Banc de classement BGE-M3 et Qwen

Le corpus fictif `corpus.json` isole le classement : passages prédécoupés et annotations, Qdrant en mémoire, sans modification du catalogue ni de l'index applicatif.

## Nouvelle série

Avec les dépendances du projet, BGE-M3 en cache et le tunnel Qwen opérationnel, depuis la racine :

```bash
.venv/bin/python experiments/reranking/run.py
.venv/bin/python experiments/reranking/baseline.py
.venv/bin/python experiments/reranking/summarize.py
```

`run.py` importe les implémentations courantes de reformulation et reranking, soit V5 et V3 lors de la revue. Le manifeste des sorties fait foi. Les réponses sont mises en cache par empreinte de l'entrée ; les sorties sont dans `results/`, ignoré par Git. Conserver les sorties d'une série avant d'en lancer une nouvelle.

`baseline.py` mesure le contrôle avec dédoublonnage exact. `prepare.py` permet de recréer le corpus déterministe si nécessaire ; il n'est pas requis pour utiliser le corpus versionné. `summarize.py` écrit un nouveau `RESULTATS.md` dans ce répertoire.

## Mesures archivées

Le [protocole](../../wiki/history/reranking-protocole-2026-11-24.md) et les [résultats du 24 novembre](../../wiki/history/reranking-resultats-2026-11-24.md) utilisaient la reformulation V4 et le reranker V2. Ils ont motivé le réglage à 30 candidats, mais ne mesurent pas les prompts multilingues actuels.

Les petits corpus adversariaux et les justifications Qwen ne démontrent pas une fiabilité générale. Les limites détaillées et la distinction calibration/validation restent dans le rapport archivé.
