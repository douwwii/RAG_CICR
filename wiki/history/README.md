# Historique des versions et expériences

Ces documents préservent les étapes antérieures. Pour exploiter la version BGE-M3 courante, revenir au [README](../../README.md) et au [guide web](../../README-web.md). Les commandes historiques ne constituent pas la procédure d'installation actuelle.

## Étapes conservées

| Étape | Documents et portée |
|---|---|
| Socle CLI MiniLM, champs JSON et catalogue | [Guide Retrieval V1](retrieval-v1.md) : contrats détaillés et anciennes commandes d'indexation/recherche. `src/index.py`, `src/search.py` et `src/evaluate.py` utilisent encore ce profil indépendant du manifeste web. |
| Calibration stricte | [Protocole et commandes](segmentation-calibration.md), distincts de l’ancrage cohérent de l’ingestion web. |
| Exploration de la segmentation | [Blocs numérotés](segmentation-qwen-essais-fictifs.md), [comparaison des consignes](segmentation-qwen-comparaison-prompt.md), [bornes](segmentation-qwen-par-bornes.md), [texte brut](segmentation-qwen-texte-brut.md). Essais qualitatifs sur trois textes fictifs. |
| Reformulation du 23 novembre 2026 | [Comparaison V1/V4 avec MiniLM](query-rewriting-2026-11-23.md). Ces chiffres ne mesurent pas la reformulation V5 actuelle avec BGE-M3. |
| Choix de la préparation et de l'encodeur, 23 novembre 2026 | [Protocole](embedding-benchmark-protocole.md), [résultats](embedding-benchmark-resultats.md). Comparaison MiniLM/BGE-M3/Qwen sur corpus fictif ; « actuel » désigne la préparation de départ du benchmark. |
| Reranking du 24 novembre 2026 | [Protocole](reranking-protocole-2026-11-24.md), [résultats](reranking-resultats-2026-11-24.md). Reformulation V4 et prompt de reranking V2 ; distincts des prompts multilingues V5/V3 chargés aujourd'hui. |

Les mentions d'absence de migration ou d'intégration dans les anciens rapports décrivent leur contexte de production. La version de référence intègre depuis BGE-M3 et l'ingestion cohérente.

## Conservation et reproduction

Les textes et les mesures ont été conservés ; seuls des liens ont été adaptés à leur emplacement d'archive et un avertissement de statut ajouté. Le code des expériences, les corpus, prompts et JSON n'ont pas été déplacés.

Les chemins en code et les commandes des archives sont à interpréter depuis la racine ou le répertoire d'expérience d'origine indiqué. Les scripts importent parfois les implémentations actuelles : une relance peut produire une nouvelle configuration. Utiliser les manifestes, prompts et générations de la série d'origine pour toute comparaison historique.

Les générateurs `experiments/embedding_benchmark/summarize.py` et `experiments/reranking/summarize.py` écrivent toujours un `RESULTATS.md` dans leur répertoire d'expérience. Ce fichier produit lors d'une nouvelle exécution ne remplace pas les instantanés archivés ici.
