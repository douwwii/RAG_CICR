# Sillage — guide BGE-M3

Application locale du prototype SPOC : dossiers du catalogue, recherche BGE-M3 dans Qdrant, ingestion de PDF numériques par Qwen et consultation des sources. Les cartes affichent uniquement des extraits du texte source ; Qwen intervient pour préparer la recherche et juger la pertinence, sans génération de réponse factuelle.

[Présentation](README.md) · [Architecture](wiki/Architecture.md) · [Sources et évaluations](wiki/Sources.md) · [Historique](wiki/history/README.md)

## Parcours de lecture

- [Installation](#installation) et [démarrage](#démarrage) pour un nouveau poste ou une session existante.
- [Qwen distant](#qwen-distant) et [démonstration](#démonstration) pour importer et chercher.
- [Prompts actifs](#prompts-actifs) et [profil BGE-M3](#profil-bge-m3) pour comprendre la configuration courante.
- [Reconstruction de l'index](#reconstruction-de-lindex-bge-m3) pour une nouvelle génération ; ce n'est pas une étape du démarrage habituel.
- [Vérifications](#vérifications), [documents longs](#documents-longs), [gestion](#bureau-documentaire-et-gestion-des-dossiers) et [suppression](#suppression-avec-confirmation) selon la tâche.

## Installation

Depuis la racine du projet, avec Python 3.10+ compatible avec les dépendances et Node.js 22.12+ (Node 24 convient). Pour une installation neuve, créer l’environnement virtuel ; sur un poste installé, conserver l’environnement existant :

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-web.txt
cd frontend
pnpm install --frozen-lockfile
cd ..
```

Si `pnpm` n'est pas installé, installer pnpm depuis son registre habituel (`npm install -g pnpm@11`). Le fichier `pnpm-lock.yaml` fixe les dépendances réellement testées. Aucun chargement de polices, lecteur PDF ou script depuis un CDN.

Le catalogue `catalogue.sqlite` et le profil `web_data/active_index.json` sont conservés pour une session existante. Si le manifeste pointe déjà vers BGE-M3, passer au démarrage sans réindexer. Sans manifeste, le code charge encore un profil de compatibilité ancien : ne pas le prendre pour la version BGE-M3.

Sur un nouveau poste, télécharger explicitement **uniquement BGE-M3** à la révision applicative. Ce chargement initial nécessite Internet ; les chargements habituels utilisent ensuite le cache local :

```bash
PYTHONPATH=src .venv/bin/python - <<'PYTHON'
from web.index_config import BGE_CONFIG, create_embedder
embedder = create_embedder(BGE_CONFIG.model_copy(update={'local_files_only': False}))
print(embedder.profile.model_name, embedder.profile.revision)
PYTHON
```

Pour un checkout neuf, serveurs arrêtés, initialiser le catalogue fictif puis construire et activer la génération BGE-M3 :

```bash
.venv/bin/python src/import_catalog.py
PYTHONPATH=src .venv/bin/python -m web.migrate_index
```

Cette construction lit les champs JSON directement ; elle ne nécessite pas d'index préalable de première génération. Un tunnel Qwen opérationnel est nécessaire si des PDF déjà importés doivent être redécoupés. Les sources TXT du catalogue ne sont pas automatiquement ingérées par cette commande.

Pour reconstruire une session existante, suivre plutôt les précautions de [reconstruction](#reconstruction-de-lindex-bge-m3). Les scripts CLI archivés ne reconstruisent pas l'index web courant.

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

Qwen sert à la segmentation des imports, à la reformulation et au reranking. Sur les documents déjà indexés, une panne Qwen entraîne les replis décrits ci-dessous ; la recherche cosinus reste possible. Un import nécessite le tunnel SSH déjà configuré sur ce poste :

```bash
ssh -N -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:11435:127.0.0.1:11434 wired-insa
```

Si SSH expire, rétablir au préalable l'accès réseau/VPN INSA. Garder ce terminal ouvert. Le navigateur ne contacte jamais Ollama : seul le backend utilise `http://127.0.0.1:11435`.

Variables facultatives à définir **avant** de démarrer :

- `SPOC_OLLAMA_URL` : URL locale du tunnel.
- `SPOC_OLLAMA_MODEL` : modèle installé sur la machine, par défaut `qwen3.8:27b-mlx`.
- `SPOC_WEB_DATA` : répertoire des PDF, textes extraits et journal des traitements, par défaut `web_data/`.
- `SPOC_RERANK_CANDIDATES` : nombre total de candidats, entre 20 et 30, par défaut 30.

Ne pas changer `SPOC_WEB_DATA` pour une session déjà alimentée sans déplacer les fichiers et leur catalogue de façon cohérente.

## Démonstration

Deux PDF intégralement fictifs sont fournis dans `data/demo/` ; ils ne sont pas préindexés :

1. Sélectionner `DOS001`, importer `dossier-a-temoignages.pdf` et attendre « Indexé ».
2. Demander : « Pourquoi le registre ne suffit-il pas à exclure un passage de Lina ? » (page 1), « Qui a récupéré le sac de Sami ? » (page 2), « Le décès de Lina à Port-Lys est-il confirmé ? » (page 2).
3. Consulter les passages et ouvrir leur source ; les numéros affichés sont ceux des pages physiques du PDF, à partir de 1.
4. Sélectionner `DOS002` et importer `dossier-b-homonyme.pdf`. Demander « Où Lina a-t-elle été vue et son identité est-elle confirmée ? ».
5. Vérifier que la recherche ne mélange jamais les dossiers. Changer de dossier efface résultats et source sélectionnée.

Les questions proposées servent à vérifier les extraits et leurs sources, sans garantir un classement parfait. BGE-M3 encode les champs préparés avec leur contexte et les passages PDF cohérents ; le reranker Qwen choisit l’ordre final lorsque son analyse réussit. La qualité sur un corpus plus large reste à évaluer.

Les anciennes sources JSON et TXT s'ouvrent comme texte ; aucune page PDF n'est inventée. Le statut « Non indexé » est affiché pour une source de catalogue absente de l'index, notamment les rapports TXT historiques.

## Fonctionnement et limites explicites

- PDF de 20 Mo maximum, 1 000 pages et 2 millions de caractères extraits. Les PDF protégés, illisibles et pages sans texte sont refusés. Pas d'OCR ; les documents mixtes contenant des pages sans texte sont également refusés.
- Extraction `pypdf`, page par page. Le texte et ses positions sont persistés avant indexation. « Texte original » signifie texte numérique extrait du PDF ; la disposition visuelle, les ligatures et l'ordre de lecture de tableaux peuvent différer de l'affichage. Le PDF reste la référence visuelle.
- Qwen reçoit le texte brut, par fenêtres pour les documents longs. L’ancrage cohérent projette les frontières proposées sur la source et conserve le contenu omis par le modèle ; les textes affichés restent ceux de la source.
- Si la segmentation est invalide, le document est indexé en extraits techniques exacts, avec avertissement explicite. Un échec réseau, délai ou sortie tronquée produit une erreur à réessayer, sans succès artificiel.
- Les passages trop longs sont divisés avec le tokenizer réel de BGE-M3, sans troncature ; chaque extrait conserve son titre parent, ses positions et ses pages. Ce découpage technique peut séparer une réserve du début de son passage parent : lire le contexte dans la source reste nécessaire. Aucun surlignage approximatif n'est présenté.
- Une file d'ingestion séquentielle, journalisée dans `web_data/jobs.sqlite`. Les imports interrompus deviennent des erreurs au redémarrage. Réimporter le même fichier après erreur relance la même tâche et conserve le même document ; un doublon déjà en attente/indexé renvoie vers l'existant. Un même fichier dans deux dossiers obtient deux références distinctes.
- Collections de la génération BGE-M3 : `cicr_fields_bge_context_v1` et `spoc_pdf_bge_coherent_v1`, avec profil d'embedding vérifié. Les points PDF ne deviennent recherchables qu'après publication du statut terminé ; un échec partiel reste exclu des recherches.
- Le backend vérifie dossier, document et texte source ; les routes fichiers n'acceptent aucun chemin système. Le lecteur et le moteur PDF.js sont servis localement.
- Sans coordonnées fiables, affichage de la page et du passage exact côte à côte. Les scores sont des similarités cosinus, jamais des probabilités de vérité.

## Vérifications

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v
cd frontend
pnpm build
```

Les tests HTTP automatisés utilisent de vrais catalogues SQLite et Qdrant temporaires, mais des modèles simulés pour isoler les contrats de l'accès distant. Ils couvrent import, doublons, validation, séparation des dossiers, exactitude source, pages, découpage, reranking et redémarrage. Ils ne mesurent pas la qualité sémantique des modèles ; les benchmarks séparés servent à cette comparaison.

Pour régénérer les PDF de démonstration : `.venv/bin/python scripts/create_demo_pdfs.py` (ReportLab dans les dépendances de développement).

## Préparation des questions

Chaque recherche envoie d’abord la question à Qwen pour obtenir une phrase de recherche concise, sans réponse ni ajout de faits. BGE-M3 encode ensuite cette formulation et Qdrant classe les candidats par similarité cosinus dans le dossier sélectionné. Le reranking décrit plus bas sélectionne les cinq résultats affichés. Une panne Qwen ou une formulation invalide/trop longue fait utiliser la question originale. Cette étape de reformulation ne garantit pas à elle seule une amélioration de pertinence.

La reformulation utilise le prompt multilingue V5, avec contrôles conservateurs des noms, nombres, mois et négations. Le [banc de reformulation](experiments/query_rewriting/README.md) précise pourquoi ses anciennes mesures ne constituent pas une évaluation de la configuration BGE-M3 actuelle.


## Prompts actifs

| Étape | Prompt courant | Sélection dans le code |
|---|---|---|
| Reformulation | [V5 multilingue](prompts/query_rewriting/v5-multilingual.txt) | `src/query_rewriting.py` |
| Segmentation cohérente | [V4 multilingue](prompts/segmentation/v4-multilingual.txt) | `src/ingestion.py`, si `coherent=True` dans le profil actif |
| Reranking | [V3 multilingue](prompts/reranking/v3-multilingual.txt) | `src/reranking.py` |

Les anciennes consignes restent dans le dépôt pour les expériences et la compatibilité. Leur présence ne signifie pas qu’elles sont actives. Une modification de prompt ne redécoupe pas les documents déjà indexés ; un nouvel import ou une reconstruction est nécessaire pour appliquer une nouvelle segmentation.

## Profil BGE-M3

La version de référence utilise `BAAI/bge-m3` à la révision `5617a9f61b028005a4858fdac845db406aefb181`, CPU, batch de quatre et quatre threads. Elle encode la question préparée et les documents avec le même modèle. La recherche reste limitée au dossier et à cinq passages maximum.

- Champs historiques : le nom de la personne explicitement associée est inclus dans l’embedding. Les valeurs et identifiants source sont conservés.
- PDF : prompt `prompts/segmentation/v4-multilingual.txt`, ancrage des frontières dans le texte original, regroupement des intertitres courts, conservation des réserves et des phrases complètes lorsque Qwen les propose correctement. Toute la source est conservée, y compris les zones omises dans la proposition du modèle. Un échec d’ancrage entraîne la nouvelle tentative/repli explicite habituels.
- Nouveaux imports : utilisent le profil actif et enregistrent leurs textes extraits dans le répertoire d’artefacts de cette génération.
- Les anciennes générations et commandes sont décrites dans l’[historique](wiki/history/README.md) ; elles ne pilotent pas le profil actif.

## Reconstruction de l'index BGE-M3

Pour construire une nouvelle génération et l’activer, arrêter les deux serveurs puis lancer :

```bash
PYTHONPATH=src .venv/bin/python -m web.migrate_index
./scripts/start-web.sh
```

Les poids BGE-M3 doivent être présents dans le cache Hugging Face ; le téléchargement ciblé est décrit dans l’[installation](#installation). Un tunnel Qwen fonctionnel est nécessaire pour redécouper les PDF. Ne pas lancer de nouveaux imports pendant cette opération.

La migration écrit dans `web_data/indexes/` un stockage distinct et des artefacts distincts. Elle vérifie les empreintes des PDF, les références du catalogue, les profils, les décomptes et la recherche des champs après réouverture. Un PDF en repli interrompt la migration avant activation. Le fichier `active_index.json` n’est remplacé qu’après ces contrôles. `previous_index.json` permet un retour à la génération précédente seulement si elle reste cohérente avec le catalogue courant, serveurs arrêtés. **Après déplacement ou suppression documentaire, ne pas réactiver une ancienne génération sans reconstruction.** Le manifeste seul ne restaure ni le catalogue, ni les fichiers supprimés, ni les journaux. Si les seules différences sont de nouveaux imports, le retour peut être effectué ainsi :

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

## Reranking Qwen et bilan de pertinence

La recherche prépare la question avec Qwen, récupère **30 candidats** cosinus au total dans le dossier, vérifie leurs sources, puis demande à Qwen d’en classer cinq. Le nombre de candidats est configurable entre 20 et 30 via `SPOC_RERANK_CANDIDATES` avant le démarrage. Il ne s’agit pas de 30 candidats par collection après fusion : les champs et passages PDF sont réunis puis limités au nombre demandé.

Le reranker juge la question originale, pas uniquement sa reformulation. Il ne reçoit pas les scores cosinus et renvoie des identifiants existants, une catégorie (`direct`, `partial`, `context`, `unrelated`), une justification courte et un diagnostic global. Le backend reprend les textes originaux, sans copier une version générée par le modèle. Le score affiché reste la similarité cosinus ; il ne détermine plus l’ordre final et n’est pas une probabilité de vérité.

Le bilan affiché décrit la pertinence et les limites des extraits à partir des catégories de Qwen, avec des liens vers les passages. Il n’est pas une synthèse factuelle libre : les premiers essais ont montré une perte possible de conditionnel dans une telle synthèse. Les faits et leurs réserves restent lisibles dans les passages exacts. Les catégories et justifications demeurent des jugements du modèle, à vérifier.

En cas de réponse invalide, délai, modèle occupé ou budget dépassé, les cinq premiers résultats cosinus sont retournés avec un avertissement et sans bilan prétendument réussi. Les identifiants inconnus, doublons et sorties hors schéma sont refusés. Une seule nouvelle tentative est permise avec les identifiants contraints par le schéma ; si elle échoue, le repli est explicite. Un lot contient au plus 60 000 octets JSON UTF-8 ; les extraits restent entiers. Un traitement par petits lots est prévu jusqu’à quatre lots avec sélection finale ; si les finalistes dépassent encore le budget, le système revient explicitement au cosinus. Aucune troncature silencieuse.

Une seule analyse de reranking est exécutée à la fois dans ce backend local. La première analyse peut prendre plusieurs dizaines de secondes sur la machine distante, davantage en cas d’attente sur la machine partagée. Les 32 dernières analyses réussies sont conservées en mémoire, uniquement pour une question et une liste de candidats identiques. Les sources sont relues/vérifiées avant consultation de ce cache. Les erreurs ne sont pas mises en cache ; redémarrer le backend vide ce cache, notamment après un changement du modèle distant.

Le [banc de classement](experiments/reranking/README.md) utilise les sources fictives de `data/reranking_demo/`. Ce corpus est séparé du catalogue de démonstration pour ne pas le polluer avec des copies et références fictives adversariales.

Le [rapport historique du 24 novembre](wiki/history/reranking-resultats-2026-11-24.md) compare cosinus seul, dédoublonnage et reranking sur 24 questions fictives, avec calibration et validation séparées. Le classement y retrouve mieux les preuves attendues ; le diagnostic global de contradiction reste insuffisant même lorsque les deux témoignages sont sélectionnés. Ces mesures portent sur les prompts de cette série, pas sur une nouvelle évaluation des versions multilingues actuelles.


## Documents longs

Au-delà de 8 000 caractères, l’ingestion utilise `src/long_segmentation.py` : fenêtres de 6 000 caractères utiles, avec jusqu’à 1 000 caractères de contexte de chaque côté. Les appels restent séquentiels. La frontière de sortie privilégie une frontière thématique proposée près de la cible ; sinon une fin de phrase ou un paragraphe. Un texte sans séparateur peut nécessiter une frontière technique. Un thème très long peut donc rester réparti entre plusieurs passages.

Le chevauchement sert seulement au contexte : chaque caractère est attribué une seule fois, dans l’ordre. Les positions globales et les pages sont calculées depuis le texte extrait original. Une vérification de couverture refuse omissions, duplications ou désalignements. Le découpage supplémentaire par le tokenizer d’embedding reste actif : aucune entrée surdimensionnée n’est tronquée silencieusement. Les embeddings et écritures Qdrant sont traités par lots de 16 passages.

Les fenêtres terminées sont sauvegardées atomiquement sous `checkpoints/<document>/`, dans le répertoire d’artefacts actif. Leur empreinte inclut texte, source, prompt, configuration LLM et version du traitement. Une panne de transport arrête l’import sans publier un succès. Après rétablissement du tunnel ou redémarrage du serveur, réimporter le même PDF dans le même dossier : les fenêtres compatibles sont relues, les autres recalculées. La reprise n’est pas automatique ; la préparation des embeddings et l’indexation sont réexécutées. Les checkpoints sont des données documentaires locales et restent conservés avec les artefacts.

La progression indique les caractères traités. La limite de taille du fichier reste 20 Mo et les PDF sans texte numérique sont toujours refusés. Les documents anciens restent consultables sans migration ; ces changements s’appliquent aux nouveaux imports et réimports.

Validation : tests synthétiques d’un PDF de 120 pages, texte multilingue, absence de séparateurs, couverture exacte, coupure réseau, cache et checkpoint corrompu. Ces tests utilisent un LLM simulé : la qualité du découpage Qwen de vrais documents longs reste à évaluer sur la machine distante.


## Mode multilingue

Le sélecteur en haut de l’interface propose français, anglais, espagnol et arabe. Le choix est mémorisé localement dans le navigateur et reste indépendant de la question et des documents. Le mode arabe définit `lang=ar` et `dir=rtl` ; les extraits utilisent leur propre direction de lecture. Les noms de dossiers, les noms de fichiers et les textes sources restent inchangés. Les libellés, les statuts, l’import, le lecteur de sources et les bilans de pertinence fixes sont traduits sans appel LLM. Des erreurs détaillées non répertoriées du serveur peuvent rester en français.

Le prompt de reformulation V5 multilingue conserve la langue de la question ; les contrôles conservateurs protègent aussi les négations anglaises, espagnoles et arabes. Le prompt de segmentation V4 demande des titres dans la langue du passage et préserve le texte original. Le reranker V3 compare les sens entre langues et demande des justifications dans la langue de la question. Cette consigne reste imparfaitement suivie sur certains cas entre langues ; les justifications libres peuvent encore apparaître en français. Les anciennes versions de prompts restent disponibles. Aucun ancien document n’est traduit ou réindexé automatiquement.

`node frontend/scripts/check-i18n.cjs` vérifie les traductions déclarées. Les essais réels sur données fictives et leurs limites sont dans `experiments/multilingual/`. Ils isolent segmentation et recherche textuelle ; ils ne prouvent pas la qualité d’extraction de PDF arabes réels ou de scans.


## Bureau documentaire et gestion des dossiers

L’interface se répartit entre gestion des dossiers et documents, recherche, et lecteur source. Les introductions et statistiques permanentes ont été retirées ; les scores et justifications détaillées sont accessibles dans « Détails de la recherche ». Les cinq passages restent sourcés, avec accès à la page originale. Le lecteur peut être agrandi ; sur écran étroit il s’ouvre au-dessus des résultats. Les quatre langues et le mode RTL sont conservés.

Le bouton « Nouveau dossier » crée un dossier nommé. L’action « Gérer le dossier » permet de renommer, archiver après confirmation et restaurer. Le filtre « Archivés » donne accès aux dossiers retirés de la liste active. L’archivage conserve les documents et interdit les nouveaux imports et recherches jusqu’à restauration. La lecture des documents existants reste possible. La suppression définitive dispose d’une confirmation distincte.

« Déplacer » transfère le document vers un autre dossier actif, avec ses associations de personnes, son journal d’import, ses passages sources et les périmètres Qdrant. Les imports en cours et doublons dans la destination sont refusés. Le cache du reranker est vidé. Un journal local `document-move.json` permet de restaurer le dossier d’origine après une erreur ou une interruption du serveur. Si cette restauration échoue, le journal est conservé et le démarrage refuse de poursuivre tant que la cohérence n’est pas rétablie. Ce mécanisme concerne l’index web actif ; une ancienne génération d’index ne doit pas être réactivée après réorganisation sans reconstruction.

Pour les PDF importés en échec ou absents de l’index actif, « Réessayer » réutilise le fichier déjà reçu. Les fenêtres de découpage compatibles sont réutilisées. Les sources JSON/TXT du catalogue restent consultables. La reconstruction BGE-M3 reprend les champs JSON ; les rapports TXT ne sont pas automatiquement ingérés.

API : `POST /api/dossiers`, `PATCH /api/dossiers/{id}` (`title`, `archived`), `POST /api/dossiers/{id}/documents/{document}/move` (`destination`), `POST /api/dossiers/{id}/documents/{document}/retry`. Les identifiants restent stables lors d’un renommage et d’un déplacement. Les écritures restent soumises au contrôle d’origine local existant.


## Suppression avec confirmation

Le bouton « Supprimer » de chaque document et « Supprimer le dossier » dans sa gestion ouvrent une confirmation nommant la cible. Pour un dossier, le dialogue précise que tous ses documents seront supprimés. La case « Je confirme cette suppression » est nécessaire avant activation du bouton final ; Annuler ne lance aucune requête de suppression.

Les routes DELETE correspondantes exigent `confirmed=true`. La suppression retire les références du catalogue, les passages des collections Qdrant actives, les tâches d’import, les fichiers PDF reçus, les artefacts actifs et leurs checkpoints. Les sources historiques JSON/TXT peuvent être partagées : leur fichier original reste conservé, seule la référence documentaire est supprimée. Les sauvegardes et anciennes générations d’index ne sont pas purgées ; il ne s’agit pas d’un effacement sécurisé de toutes les copies. Les imports en cours empêchent la suppression. Le journal `document-delete.json` termine une suppression interrompue au redémarrage, de manière idempotente.
