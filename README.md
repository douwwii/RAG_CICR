# Sillage — recherche documentaire avec BGE-M3

Prototype local du projet SPOC : recherche dans un dossier, import de PDF numériques et consultation des passages sources. Les jeux de démonstration fournis sont fictifs. L'application affiche des extraits exacts et des jugements de pertinence ; elle ne génère pas de réponse factuelle. L’onglet OCR transcrit les scans avec Inkling sur le serveur configuré, avant vérification et ajout explicite à la recherche.

## Trouver le bon contexte

| Besoin | Lire |
|---|---|
| Consignes pour un agent | [AGENTS.md](AGENTS.md) |
| Installer, lancer, importer, reconstruire un index | [Guide web](README-web.md) |
| Comprendre les composants, les flux et les contrats | [Architecture](wiki/Architecture.md) |
| Trouver une expérience, une preuve ou une limite connue | [Sources](wiki/Sources.md) |
| Consulter les anciennes versions et leurs résultats | [Historique](wiki/history/README.md) |

Lire seulement le document correspondant à la tâche. Les anciens guides et résultats sont séparés de la documentation courante.

## Version de référence

- Embeddings locaux : **BAAI/bge-m3**, révision épinglée dans le profil web.
- Préparation des champs : contexte de la personne explicitement associée.
- PDF : segmentation cohérente avec le prompt multilingue V4, puis subdivisions adaptées au tokenizer si nécessaire.
- Recherche : modes sémantique, hybride et exact, filtrage par dossier et documents, 30 candidats par défaut, reranking V3 et cinq extraits au maximum.
- Interface : français, anglais, espagnol et arabe ; lecture RTL pour l'arabe.
- Stockages : catalogue SQLite, tâches SQLite, Qdrant local et fichiers sources/artefacts.

Le profil réellement chargé dépend de `web_data/active_index.json`. Vérifier `GET /api/health` après démarrage. **L'absence de manifeste n'active pas automatiquement BGE-M3** : construire l'index selon le [guide d'installation](README-web.md#installation) avant d'utiliser une installation neuve.

Les scripts CLI de première génération ne suivent pas le profil web actif. Ils sont documentés dans l'[historique](wiki/history/README.md), et ne servent pas à reconstruire l'index courant.

## Démarrage habituel

Sur un poste déjà installé, avec un catalogue et un index BGE-M3 actifs :

```bash
./scripts/start-web.sh
```

Ouvrir [l'application locale](http://127.0.0.1:5173). Un seul backend doit ouvrir le stockage Qdrant local. Il n'est pas nécessaire de réindexer pour lancer l'interface.

Le tunnel Qwen sert à l'import, à la reformulation et au reranking. Une recherche sur des documents déjà indexés peut se replier sur le classement cosinus lorsque Qwen est indisponible. Voir le [guide web](README-web.md#qwen-distant).

## Vérifications

Depuis la racine, après installation des dépendances de développement :

```bash
.venv/bin/python -B -m unittest discover -s tests -v
node frontend/scripts/check-i18n.cjs
cd frontend
pnpm build
```

Les dépendances nécessaires à la suite complète sont dans `requirements-dev.txt`, qui inclut les dépendances web et ReportLab. Les tests vérifient les contrats avec des modèles simulés ; ils ne prouvent pas la qualité sémantique de BGE-M3 ou de Qwen. Les protocoles et limites des évaluations réelles sont indexés dans les [sources](wiki/Sources.md).

## Limites à conserver

Le dossier est sélectionné explicitement ; un nom n'est jamais une clé d'identité. Les passages doivent rester alignés avec leur texte source et leurs pages physiques. Un score cosinus ou un jugement Qwen n'est pas une probabilité de vérité.

L’import numérique refuse les pages sans texte extractible ; les scans passent par l’[onglet OCR](README-web.md#ocr-inkling). Le service local n'a pas d'authentification et n'est pas destiné à être publié tel quel. Les petits corpus d'évaluation ne démontrent pas une fiabilité générale.
