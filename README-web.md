# Sillage — interface documentaire V1

Application locale du prototype SPOC : dossiers du catalogue existant, recherche réelle dans Qdrant, ingestion de PDF numériques par Qwen et consultation des sources. Aucun appel de génération de réponse : les cartes affichent uniquement des extraits du texte source.

## Installation

Depuis la racine du projet, avec Python compatible avec les dépendances du projet et Node.js 22.12+ (Node 24 convient) :

```bash
.venv/bin/python -m pip install -r requirements-web.txt
cd frontend
pnpm install --frozen-lockfile
cd ..
```

Si `pnpm` n'est pas installé, installer pnpm depuis son registre habituel (`npm install -g pnpm@11`). Le fichier `pnpm-lock.yaml` fixe les dépendances réellement testées. Aucun chargement de polices, lecteur PDF ou script depuis un CDN.

Le catalogue `catalogue.sqlite` est conservé. Le profil web actif est enregistré dans `web_data/active_index.json` ; après migration, il utilise BGE-M3 avec la préparation contexte + cohérent. Sans manifeste, le socle historique MiniLM reste disponible. Pour initialiser un checkout dépourvu de catalogue/index, suivre d'abord la procédure du README principal (`src/import_catalog.py`, puis `src/index.py`). Ne pas réindexer un corpus existant pour simplement démarrer l'interface.

## Démarrage

```bash
./scripts/start-web.sh
```

Ouvrir **http://127.0.0.1:5173**. `Ctrl+C` arrête les deux serveurs. Ports : frontend 5173, backend 8000. Un seul processus backend doit ouvrir ce stockage Qdrant local. Fermer une éventuelle commande CLI qui détient déjà ce stockage.

Alternative, dans deux terminaux depuis la racine :

```bash
.venv/bin/python -m uvicorn web.app:app --app-dir src --host 127.0.0.1 --port 8000
```

```bash
cd frontend
pnpm dev
```

L'application écoute sur la boucle locale. Elle ne fournit pas d'authentification et reste destinée à une démonstration sur ce poste avec des données fictives ou publiques. Ne pas la publier telle quelle.

## Qwen distant

La recherche sur les documents déjà indexés fonctionne sans Qwen. Un import nécessite le tunnel SSH déjà configuré :

```bash
ssh -N -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:11435:127.0.0.1:11434 wired-insa
```

Si SSH expire, rétablir au préalable l'accès réseau/VPN INSA. Garder ce terminal ouvert. Le navigateur ne contacte jamais Ollama : seul le backend utilise `http://127.0.0.1:11435`.

Variables facultatives à définir **avant** de démarrer :

- `SPOC_OLLAMA_URL` : URL locale du tunnel.
- `SPOC_OLLAMA_MODEL` : modèle installé sur la machine, par défaut `qwen3.8:27b-mlx`.
- `SPOC_WEB_DATA` : répertoire des PDF, textes extraits et journal des traitements, par défaut `web_data/`.

Ne pas changer `SPOC_WEB_DATA` pour une session déjà alimentée sans déplacer les fichiers et leur catalogue de façon cohérente.

## Démonstration

Deux PDF intégralement fictifs sont fournis dans `data/demo/` ; ils ne sont pas préindexés :

1. Sélectionner `DOS001`, importer `dossier-a-temoignages.pdf` et attendre « Indexé ».
2. Demander : « Pourquoi le registre ne suffit-il pas à exclure un passage de Lina ? » (page 1), « Qui a récupéré le sac de Sami ? » (page 2), « Le décès de Lina à Port-Lys est-il confirmé ? » (page 2).
3. Consulter les passages et ouvrir leur source ; les numéros affichés sont ceux des pages physiques du PDF, à partir de 1.
4. Sélectionner `DOS002` et importer `dossier-b-homonyme.pdf`. Demander « Où Lina a-t-elle été vue et son identité est-elle confirmée ? ».
5. Vérifier que la recherche ne mélange jamais les dossiers. Changer de dossier efface résultats et source sélectionnée.

Les réponses attendues servent à vérifier les extraits, sans garantie que chaque question classe le bon passage en tête. Le classement est celui du modèle MiniLM actuel. Les champs historiques et les nouveaux extraits emploient le même encodeur, mais leur préparation diffère ; leur classement combiné devra être évalué sur un corpus plus large.

Les anciennes sources JSON et TXT s'ouvrent comme texte ; aucune page PDF n'est inventée. Le statut « Non indexé » est affiché pour une source de catalogue absente de l'index, notamment les rapports TXT historiques.

## Fonctionnement et limites explicites

- PDF de 20 Mo maximum, 100 pages et 24 000 caractères extraits : limites de démonstration pour contenir l'extraction et la requête Qwen. Les PDF protégés, illisibles et pages sans texte sont refusés. Pas d'OCR ; les documents mixtes contenant des pages sans texte sont également refusés.
- Extraction `pypdf`, page par page. Le texte et ses positions sont persistés avant indexation. « Texte original » signifie texte numérique extrait du PDF ; la disposition visuelle, les ligatures et l'ordre de lecture de tableaux peuvent différer de l'affichage. Le PDF reste la référence visuelle.
- Qwen reçoit le texte brut complet, sans blocs numérotés. Les extraits sont vérifiés contre la source ; seuls les séparateurs blancs omis entre extraits exacts peuvent être restaurés. La validation stricte historique conserve son comportement par défaut.
- Si la segmentation est invalide, le document est indexé en extraits techniques exacts, avec avertissement explicite. Un échec réseau, délai ou sortie tronquée produit une erreur à réessayer, sans succès artificiel.
- Les passages trop longs sont divisés avec le tokenizer réel de MiniLM, sans troncature ; chaque extrait conserve son titre parent, ses positions et ses pages. Ce découpage technique peut séparer une réserve du début de son passage parent : lire le contexte dans la source reste nécessaire. Aucun surlignage approximatif n'est présenté.
- Une file d'ingestion séquentielle, journalisée dans `web_data/jobs.sqlite`. Les imports interrompus deviennent des erreurs au redémarrage. Réimporter le même fichier après erreur relance la même tâche et conserve le même document ; un doublon déjà en attente/indexé renvoie vers l'existant. Un même fichier dans deux dossiers obtient deux références distinctes.
- Nouvelle collection `spoc_pdf_passages_v1`, profil d'embedding vérifié. La collection historique n'est pas reconstruite. Les points ne deviennent recherchables qu'après publication du statut terminé ; un échec partiel reste exclu des recherches.
- Le backend vérifie dossier, document et texte source ; les routes fichiers n'acceptent aucun chemin système. Le lecteur et le moteur PDF.js sont servis localement.
- Sans coordonnées fiables, affichage de la page et du passage exact côte à côte. Les scores sont des similarités cosinus, jamais des probabilités de vérité.

## Vérifications

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v
cd frontend
pnpm build
```

Les tests HTTP automatisés utilisent de vrais catalogues SQLite et Qdrant temporaires, mais des modèles simulés pour isoler les contrats de l'accès distant. Ils couvrent import, doublons, validation, séparation des dossiers, exactitude source, pages, découpage et redémarrage. Ils ne mesurent pas la qualité sémantique de Qwen ou MiniLM.

Pour régénérer les PDF de démonstration : `.venv/bin/python scripts/create_demo_pdfs.py` (ReportLab dans les dépendances de développement).

## Préparation des questions

Chaque recherche envoie d’abord la question à Qwen pour obtenir une phrase de recherche concise, sans réponse ni ajout de faits. MiniLM encode ensuite cette formulation et Qdrant classe les passages par similarité cosinus dans le dossier sélectionné. Cinq résultats maximum sont retournés. Une panne Qwen ou une formulation invalide/trop longue fait utiliser la question originale. Cette reformulation ne constitue pas un reranking et ne garantit pas une amélioration de pertinence.

La reformulation utilise désormais le prompt versionné `prompts/query_rewriting/v4.txt`, avec contrôles conservateurs des noms, nombres, mois et négations. L’évaluation comparative et ses limites sont décrites dans `experiments/query_rewriting/README.md`. Elle ne remplace pas un classement plus fin des passages ni une amélioration du découpage documentaire.


## Version BGE-M3 — contexte + cohérent

La version migrée utilise `BAAI/bge-m3` à la révision `5617a9f61b028005a4858fdac845db406aefb181`, CPU, batch de quatre et quatre threads. Elle encode la question préparée et les documents avec le même modèle. La recherche reste limitée au dossier et à cinq passages maximum.

- Champs historiques : le nom de la personne explicitement associée est inclus dans l’embedding. Les valeurs et identifiants source sont conservés.
- PDF : prompt `prompts/segmentation/v3-coherent.txt`, ancrage des frontières dans le texte original, regroupement des intertitres courts, conservation des réserves et des phrases complètes lorsque Qwen les propose correctement. Toute la source est conservée, y compris les zones omises dans la proposition du modèle. Un échec d’ancrage entraîne la nouvelle tentative/repli explicite habituels.
- Nouveaux imports : utilisent le profil actif et enregistrent leurs textes extraits dans le répertoire d’artefacts de cette génération.
- Les collections MiniLM historiques et les anciens artefacts restent disponibles. Les scripts CLI historiques continuent à utiliser MiniLM ; ils ne reconstruisent pas l’index BGE web.

Pour construire une nouvelle génération et l’activer, arrêter les deux serveurs puis lancer :

```bash
PYTHONPATH=src .venv/bin/python -m web.migrate_index
./scripts/start-web.sh
```

Les poids BGE doivent être présents dans le cache Hugging Face ; le téléchargement local épinglé est disponible avec `experiments/embedding_benchmark/download_models.py`. Un tunnel Qwen fonctionnel est nécessaire pour redécouper les PDF. Ne pas lancer de nouveaux imports pendant cette opération.

La migration écrit dans `web_data/indexes/` un stockage distinct et des artefacts distincts. Elle vérifie les empreintes des PDF, les références du catalogue, les profils, les décomptes et la recherche des champs après réouverture. Un PDF en repli interrompt la migration avant activation. Le fichier `active_index.json` n’est remplacé qu’après ces contrôles. `previous_index.json` permet un retour à la génération précédente, serveurs arrêtés :

```bash
.venv/bin/python - <<'PYTHON'
from pathlib import Path
from shutil import copyfile
root = Path('web_data')
copyfile(root / 'previous_index.json', root / 'active_index.tmp')
(root / 'active_index.tmp').replace(root / 'active_index.json')
PYTHON
./scripts/start-web.sh
```

Le retour arrière change uniquement l’index consulté : les PDF importés depuis la migration restent visibles au catalogue et sont indiqués non indexés si leur artefact est absent de cette génération ; un réimport permet de les y indexer. Les compteurs de passages reflètent la dernière migration effectuée. Le profil actif est consultable via `GET /api/health`, sans exposer de chemins système.
