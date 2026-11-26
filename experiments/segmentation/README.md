# Calibration du découpage — banc strict

L'ingestion BGE-M3 courante utilise l'ancrage cohérent et le prompt multilingue V4, décrits dans le [guide web](../../README-web.md#prompts-actifs).

Le script `run.py` de ce répertoire teste un contrat strict de copie intégrale. Son prompt par défaut est V1 et ses appels ne sélectionnent pas le mode cohérent : changer seulement le fichier de prompt ne transforme pas ce banc en test de l'ingestion courante.

Pour vérifier ce contrat et sa référence technique sans appel Qwen, depuis la racine :

```bash
.venv/bin/python -B -m unittest discover -s tests -p 'test_segmentation*.py'
.venv/bin/python -B experiments/segmentation/run.py --baseline-only --output experiments/segmentation/results/reference.jsonl
```

Le [protocole de calibration archivé](../../wiki/history/segmentation-calibration.md) conserve les options, les commandes distantes et les versions de consignes alors comparées. Les [premiers essais](../../wiki/history/README.md) sont historiques. Pour les reprises de documents longs et la conservation de la source, consulter les tests `test_long_documents.py` et `test_web.py`, puis les évaluations réelles indexées dans les [sources](../../wiki/Sources.md).
