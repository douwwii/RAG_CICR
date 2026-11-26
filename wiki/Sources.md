# Sources et parcours de lecture

Révisé le 25 novembre 2026. Cet index sépare les contrats actuels, les mesures datées et les étapes archivées. Une configuration observée sur ce poste ne garantit pas celle d'un autre checkout.

## Documentation courante

| Question | Source de référence |
|---|---|
| Quel est le projet et par où commencer ? | [README](../README.md), [consignes agents](../AGENTS.md) |
| Comment installer, lancer et exploiter BGE-M3 ? | [Guide web](../README-web.md) |
| Quels composants et contrats préserver ? | [Architecture](Architecture.md) et ses renvois ciblés vers le code |
| Quel profil une session charge-t-elle ? | Manifeste local `web_data/active_index.json`, puis `GET /api/health` |
| Quelles consignes LLM sont actives ? | Tableau des [prompts courants](../README-web.md#prompts-actifs) et fichiers qu'il référence |
| Que vérifient les tests ? | [Vérifications du README](../README.md#vérifications), puis le test du composant concerné |

En cas de contradiction, confronter la documentation au code, au manifeste de la session et aux instructions de l'utilisateur. Corriger ou signaler la différence ; ne pas choisir silencieusement une archive comme règle actuelle.

## Évaluations et portée

| Expérience | Statut, source et limites |
|---|---|
| Recherche BGE-M3 multilingue | [Résultats du 25 novembre](../experiments/multilingual/RESULTATS.md) : quatre textes fictifs, huit questions ; segmentation et recherche isolées. Ne valide pas l'extraction de PDF arabes ou les scans. |
| Mancha 4 | [Protocole local](../experiments/mancha4/README.md) : transcription espagnole de 80 pages, recherche BGE-M3 ; variante avec reformulation V5 et reranking V3. Le découpage technique ne teste pas toute l'ingestion web. |
| Préparation documentaire et embeddings | [Banc de comparaison](../experiments/embedding_benchmark/README.md) ; protocole et mesures du 23 novembre dans l'historique. A motivé le choix BGE-M3 et de la préparation contexte + cohérent. |
| Reranking | [Banc de classement](../experiments/reranking/README.md) ; mesures historiques du 24 novembre avec un prompt antérieur. Une nouvelle série doit isoler ses sorties, notamment le cache de reformulations non versionné par prompt ; voir les précautions du banc. |
| Reformulation | [Périmètre du banc](../experiments/query_rewriting/README.md) ; anciennes mesures archivées. Ce script ne mesure pas le pipeline BGE-M3 actuel. |
| Segmentation | [Calibration](../experiments/segmentation/README.md) ; banc strict et anciens essais distincts de l'ingestion cohérente actuelle. |

Les corpus annotés JSON, manifestes et scripts restent dans leurs répertoires d'expérience. Un résultat daté conserve sa configuration : ne pas remplacer le nom d'un modèle ou d'un prompt dans une ancienne mesure pour l'aligner sur l'application courante.

## Historique et decisions

L'[index historique](history/README.md) conserve les guides précédents, les protocoles de comparaison et les sorties commentées de segmentation. Les expressions « actuel » ou « non intégré » dans ces documents renvoient à l'état de l'expérience à sa date.

Les guides courants décrivent le fonctionnement de la version utilisée. Les anciennes configurations et mesures restent dans l'historique. Les détails techniques appartiennent au guide ou au contrat concerné ; les consignes agents servent à orienter la lecture sans les recopier.

## Sources locales et inconnues

- Le catalogue, les générations d'index, PDF reçus et caches sont locaux et généralement ignorés par Git. Un clone ne reproduit pas automatiquement la session du poste.
- Lors de la revue, `experiments/mancha4/` et `output/` étaient non suivis par Git. Leur conservation/versionnement relève d'une décision séparée ; ne pas les supprimer ni les ajouter automatiquement.
- Mancha 4 attend `../transcription.md`, depuis la racine du projet. Cette source extérieure était présente sur le poste ; sa disponibilité ailleurs et ses droits de diffusion ne sont pas établis ici. Le rapport PDF est généré dans `output/pdf/`.
- Les générations et mesures détaillées de plusieurs expériences sont dans des sorties ignorées par Git. Vérifier leur disponibilité avant de promettre une reproduction exacte.
- Les révisions de modèles sont épinglées ; les dépendances Python sont déclarées par plages. Le profil inclut les versions logicielles : un changement d'environnement peut nécessiter une nouvelle génération d'index.
- La qualité sur de grands corpus, les translittérations, les PDF complexes et les documents longs réels n'est pas démontrée par les tests avec modèles simulés ni par les petits corpus fictifs.
