> Archive documentaire conservée le 25 novembre 2026. Décrit une étape passée ; utiliser le [guide actuel](../../README.md) pour exploiter BGE-M3. Les commandes et chemins en code se lisent depuis la racine du projet.

# Évaluation de la reformulation — 23 novembre 2026

Comparaison réelle avec Qwen `qwen3.8:27b-mlx`, MiniLM multilingue et Qdrant en mémoire. L’index applicatif n’est pas modifié : reconstruction temporaire des 48 champs historiques et des 23 passages du PDF effectivement indexé dans DOS001, avec les mêmes textes d’embedding, filtres de dossier et cinq résultats maximum.

40 questions : les 32 questions annotées du corpus historique, plus huit questions sur le PDF fictif. Pour les champs, réussite = identifiant annoté retrouvé ; pour le PDF, tous les fragments de preuve prédéfinis doivent apparaître dans les extraits du bon document, après normalisation des espaces pour la mesure uniquement. Premier résultat = tous les éléments attendus dans ce seul résultat ; couverture à cinq = tous les éléments dans l’ensemble des cinq. La restitution applicative conserve le texte exact.

| Variante | Premier résultat complet | Éléments attendus dans les cinq |
| --- | ---: | ---: |
| Question originale | 8/40 | 19/40 |
| Prompt initial V1 | 10/40 | 22/40 |
| Prompt corrigé V4 + garde-fous | 10/40 | 23/40 |

V1 : cinq améliorations et deux régressions de couverture par rapport à l’original. V4 : quatre améliorations, aucune régression de couverture observée. Ces résultats ne garantissent pas l’absence de régression sur de nouvelles questions.

La fusion des deux classements par Reciprocal Rank Fusion (constante 60), également testée, obtient 20/40 en couverture avec V4 : elle n’est pas intégrée à l’application. Les scores affichés restent des similarités cosinus.

## Fidélité et corrections

V1 transformait « Sami a-t-il disparu le 8 mai ? » en « Disparition de Sami le 8 mai. », et « Le décès de Lina à Port-Lys est-il confirmé ? » en « Confirmation du décès de Lina à Port-Lys. ». Ces formulations effacent la nature interrogative de la vérification.

V4 conserve les questions de confirmation, autorise les formulations nominales pour les demandes factuelles simples et interdit les déductions de contexte ou de genre. Exemple réellement obtenu : « Quels éléments permettent de vérifier si Sami a disparu le 8 mai ? ».

Contrôles Python : JSON strict, longueur, budget du tokenizer réel, conservation des nombres/mois/négations, ancres capitalisées et certains marqueurs d’incertitude. Repli sur la question originale si rejet ou panne réseau. Les ancres capitalisées sont une heuristique prudente, pas une reconnaissance d’entités ni une preuve d’équivalence sémantique. Aucun rejet par ces garde-fous n’a été nécessaire sur les 40 sorties V4 mesurées ; les rejets sont vérifiés par des tests automatisés dédiés.

La vérification du budget n’effectue plus d’embedding inutile. Le tokenizer reste protégé par le verrou du backend. Temps moyen Qwen observé, modèle déjà chargé : environ 0,69 s en V1 et 0,87 s en V4 ; mesure indicative, hors recherche vectorielle et chargement à froid.

## Limites

Petit corpus fictif, nombreuses questions construites sur le même patron. Deux sous-ensembles de 20 sont consignés, mais le résultat global est exploratoire : les questions existaient déjà et le résultat initial a été consulté avant les ajustements. Il ne s’agit pas d’une évaluation indépendante à l’aveugle.

Le gain de couverture provient des champs historiques. Sur les huit questions PDF, la couverture reste à 5/8 ; la première position complète passe de 2/8 à 3/8. La reformulation ne corrige donc pas la fragmentation des passages. Les champs historiques omettent souvent le nom de la personne dans le texte encodé (ex. valeur de lieu seule avec son libellé), ce qui limite aussi la recherche à l’échelle d’un dossier. Ces deux problèmes demandent une amélioration distincte du découpage et de la représentation documentaire.

## Reproduction

Depuis la racine, avec l’API locale active et le tunnel SSH opérationnel :

```bash
.venv/bin/python experiments/query_rewriting/evaluate.py --prompt prompts/query_rewriting/v1.txt --output experiments/query_rewriting/results/v1
.venv/bin/python experiments/query_rewriting/evaluate.py --prompt prompts/query_rewriting/v4.txt --output experiments/query_rewriting/results/v4
```

Les sorties locales ignorées par Git comprennent : `generations.json` (réponses Qwen, cache par empreinte prompt/question, temps), `report.json` (questions, formulations, résultats exacts et mesures), `manifest.json` (prompt, empreinte du corpus, configuration et profil d’embedding). Réutiliser un répertoire réutilise les générations en cache ; choisir un autre répertoire pour une nouvelle série de générations. Les métriques sont recalculées, sans réindexer les données de l’application.
