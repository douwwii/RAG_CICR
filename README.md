# SPOC CICR — Retrieval V1 (100 % fictif)

**Objectif** : indexer des champs de formulaires fictifs, calculer leurs embeddings, les stocker dans Qdrant et récupérer les passages pertinents. **Pas d'OCR ni de LLM** à ce stade. Aucun document réel du CICR.

## Pré-requis

Python 3.10+. Le service utilise par défaut le modèle déjà présent dans le cache
local. Pour une première installation, le téléchargement explicite du modèle est
décrit dans la section 6 ; les calculs d'embedding restent locaux.

```bash
cd spoc_retrieval_v1
python3 -m venv .venv
source .venv/bin/activate   # Windows PowerShell : .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 1. Indexer les données

```bash
python src/index.py
```

- Lit `data/documents.json`.
- Transforme chaque champ en texte `Type de champ : ... Information : ...`.
- Calcule un embedding **384 dimensions** avec MiniLM multilingue.
- Crée une collection Qdrant locale dans `qdrant_data/`.
- Stocke pour chaque point un vecteur, un identifiant et les champs d'origine dans le *payload*.
- Utilise la collection `cicr_synthetic_minilm_v2`, avec un profil d'embedding enregistré.
- Réexécuter le script **remplace cette collection si son profil est compatible**
  (ne pas l'utiliser pour des données à conserver). Un index sans profil ou incompatible
  est refusé. L'ancienne collection `cicr_synthetic_minilm_v1` est conservée.

## 2. Chercher des informations

```bash
python src/search.py "Où la personne est-elle décédée ?" --person P001
python src/search.py "Où la personne est-elle décédée ?" --person P001 --field lieu_de_deces
python src/search.py "Dans quelle ville a-t-on vu Marie pour la dernière fois ?"
```

- Sans filtre : similarité sémantique sur tous les champs.
- Avec `--person` : filtre exact sur `person_id` + similarité sémantique.
- Avec `--field` : filtre exact sur `field_name` en supplément.
- La sortie indique le score cosinus, la valeur, le type de champ et la provenance fictive.
- Le filtre d'identité est fourni explicitement : nous ne prétendons pas avoir résolu le nom dans une question libre.

## 3. Évaluer le retrieval

```bash
python src/evaluate.py
```

`data/queries.json` contient des questions, la personne attendue, et les identifiants des champs pertinents (*ground truth*). Comparaison : **dense seul** vs **dense + filtre sur personne**.

- **Hit@1** : fraction des questions où le premier résultat est pertinent.
- **Recall@5** : fraction des champs pertinents présents dans les cinq premiers résultats, moyennée sur les questions.

Il s'agit de mesures exploratoires sur un petit jeu synthétique, pas de performances garanties sur des données réelles. Un rappel élevé ne prouve pas la justesse d'une réponse générée.

## 4. Contrat de données et validation

Le corpus contient des **champs préextraits**, représentés par `FieldRecord` dans
`src/schemas.py`. Un enregistrement n'est pas un document complet : les identifiants
`document_id` actuels sont synthétiques et distincts pour chaque champ. Plusieurs
champs peuvent néanmoins partager un `document_id` ; seul `id` doit être unique
dans le corpus. Aucun dossier ni numéro de page n'est déduit de ces identifiants.

| Propriété | Contrat |
|---|---|
| `id` | Entier entre 0 et `2**64 - 1`, conservant le format accepté par l'index actuel. |
| `document_id` | Référence synthétique du document source. |
| `person_id` | Identifiant de la personne concernée. |
| `field_name` | Nom technique du champ. |
| `field_label` | Libellé original du champ. |
| `value` | Valeur textuelle originale. |
| `source_kind` | Type de source déclaré dans les données. |

Les sept propriétés sont obligatoires. Les six propriétés textuelles doivent être
des chaînes non vides et non composées uniquement d'espaces. Pydantic v2 est utilisé
en **mode strict** : `"2"`, `2.0` et `true` ne deviennent pas implicitement l'entier
`2`. Les propriétés inconnues sont rejetées pour détecter les erreurs de saisie.
Les valeurs acceptées restent identiques, y compris les accents et les espaces ;
les dates restent du texte. Les noms de champs et les identifiants de personnes ne
sont pas limités à la liste actuelle.

Le parcours de chargement est :

```text
JSON UTF-8 non vide
  → validation individuelle FieldRecord
  → vérification de l'unicité des id
  → objets typés
  → dictionnaires historiques pour l'indexation existante
```

Les interfaces publiques de `src/data_loader.py` sont :

- `load_field_records(path: Path) -> list[FieldRecord]` : lecture et validation du corpus.
- `validate_corpus(records: Sequence[FieldRecord]) -> None` : vérification globale
  d'un corpus non vide dont les éléments sont déjà validés individuellement.
- `load_evaluation_cases(path: Path, records: Sequence[FieldRecord]) -> list[EvaluationCase]` :
  lecture des questions, validation de leur structure et de leurs références.

`load_documents()` conserve sa signature et retourne les mêmes dictionnaires
qu'avant, après validation. Le modèle et la recherche vectorielle ne changent pas.
`evaluate.py` valide désormais aussi les annotations avant de charger le modèle :
chaque question doit avoir un texte, une personne et au moins un identifiant
pertinent ; les références doivent être uniques, exister dans le corpus et
appartenir à la personne annotée. Un jeu de questions vide est rejeté.

Les erreurs de données lèvent `DataValidationError`, une sous-classe de `ValueError`,
avec le chemin du fichier et l'emplacement fautif. Les positions commencent à zéro :
`1.value` désigne la propriété `value` du deuxième enregistrement. Un fichier absent
ou inaccessible conserve l'erreur système correspondante (`FileNotFoundError`, etc.).

Pour inspecter les données sans charger MiniLM ni ouvrir Qdrant, depuis la racine :

```bash
PYTHONPATH=src python - <<'PY'
from pathlib import Path
from data_loader import load_evaluation_cases, load_field_records

records = load_field_records(Path('data/documents.json'))
cases = load_evaluation_cases(Path('data/queries.json'), records)
print(f'{len(records)} champs validés, {len(cases)} questions validées')
print(records[1].model_dump())
PY
```

Ce chemin ne nécessite que Pydantic et la bibliothèque standard. Il ne produit
aucun embedding et ne modifie pas l'index. Les objets `FieldRecord` interdisent la
réaffectation de leurs attributs ; `model_dump()` produit des dictionnaires séparés
pour les scripts existants.

Les tests utilisent `unittest`, sans dépendance de test supplémentaire :

```bash
python -B -m unittest discover -s tests -v
```

Ils couvrent le corpus actuel, les erreurs de structure et de types, les doublons,
les références des annotations, la conservation des textes et l'indépendance vis-à-vis
des bibliothèques d'embedding et de stockage. Le contrat ne vérifie pas la vérité des
informations, les contradictions ni les autorisations d'accès. Le catalogue documentaire
et la représentation des dossiers sont présentés ci-dessous.

## 5. Catalogue documentaire : dossiers, personnes et sources

Le **dossier est le périmètre logique d'enquête**. Il regroupe plusieurs documents
et peut concerner plusieurs personnes. Un document peut mentionner plusieurs
personnes, et une personne peut apparaître dans plusieurs dossiers. Le nom
d'affichage n'est jamais une clé : deux personnes peuvent être homonymes.

```text
Fichiers sources / JSON : contenu original
Catalogue SQLite       : identifiants, relations et provenance
Qdrant                 : embeddings et métadonnées de recherche
```

Le catalogue est indépendant de l'extraction, du modèle d'embedding et de Qdrant.
Dans cette version, **un document appartient à un seul dossier**. Un document ou
un dossier peut ne comporter aucune personne identifiée. En revanche, toute personne
associée à un document doit aussi être associée au dossier de ce document.

### Modèle et stockage

Les nouveaux contrats Pydantic sont définis dans `src/schemas.py` :

- `Dossier(dossier_id, title, person_ids)` : un dossier et les personnes associées.
- `Person(person_id, display_name)` : un identifiant stable et un nom d'affichage.
- `DocumentMetadata(document_id, dossier_id, source_kind, source_path, source_locator, person_ids)` :
  les métadonnées d'une source, sans contenu extrait ni vecteur. `source_locator`
  est facultatif ; il vaut `id=2`, par exemple, pour un enregistrement du JSON actuel.
- `CatalogSeed(dossiers, persons, documents)` : le manifeste d'initialisation.

Les identifiants et propriétés textuelles sont strictement validés. Une même
personne ne peut pas être répétée dans la liste `person_ids` d'un dossier ou d'un
document. Le contrat `FieldRecord` de la brique 1 reste inchangé.

`src/catalog.py` utilise le module standard `sqlite3`, sans serveur ni ORM. La base
contient cinq tables :

| Table | Responsabilité |
|---|---|
| `dossiers` | Identifiants et intitulés des dossiers. |
| `persons` | Identifiants et noms d'affichage des personnes. |
| `dossier_persons` | Associations entre dossiers et personnes. |
| `documents` | Documents, dossier propriétaire et références des sources. |
| `document_persons` | Personnes mentionnées par les documents. |

Les clés étrangères sont activées à chaque connexion. Deux contraintes composites
sur `document_persons` garantissent à la fois que le document appartient au dossier
indiqué et que la personne est membre de ce dossier. Les valeurs des requêtes SQL
sont passées comme paramètres.

Le schéma porte la version 1, enregistrée dans `PRAGMA user_version`. Une base
étrangère ou une version inconnue est refusée, sans suppression automatique de son
contenu. `initialize()` est réexécutable et conserve les données existantes.

### Jeu fictif et initialisation

Le fichier `data/catalog_seed.json` décrit explicitement deux dossiers. Leurs
associations sont une convention de test, sans inférence depuis les noms ou les
lieux cités dans les documents.

| Dossier | Personnes | Références documentaires |
|---|---|---|
| `DOS001` | `P001` à `P004` | 24 références historiques + `DOC-CROISE-001`. |
| `DOS002` | `P005` à `P008` | 24 références historiques + `DOC-CROISE-002`. |

Les 48 références historiques gardent leur `document_id`. Elles pointent vers
`data/documents.json` avec un emplacement `id=N`, sans inventer de PDF ni de page.
Les deux nouvelles sources sont des textes fictifs dans `data/catalog_sources/` :
la première mentionne Jean Dupont et Marie Laurent, la seconde Nadia Karim et Hugo
Martin. Elles permettent d'inspecter de vrais liens vers plusieurs personnes.
**Ces deux textes ne sont pas ajoutés à l'index Qdrant.**

Depuis la racine du projet, dans l'environnement virtuel :

```bash
python src/import_catalog.py
```

Le résultat du premier import est :

```text
Ajoutés : 2 dossiers, 8 personnes, 50 documents
DOS001 | Dossier fictif A — personnes P001 à P004 | 4 personnes | 25 documents
DOS002 | Dossier fictif B — personnes P005 à P008 | 4 personnes | 25 documents
```

La base générée `catalogue.sqlite` est exclue de Git. Ses chemins par défaut et celui
du manifeste sont centralisés dans `src/common.py` (`CATALOG_FILE`, `CATALOG_SEED_FILE`).
Ils peuvent être remplacés pour l'import :

```bash
python src/import_catalog.py --seed data/catalog_seed.json --db catalogue.sqlite
```

Dans le manifeste, les chemins des sources sont relatifs au répertoire du manifeste.
L'importeur vérifie leur existence et les enregistre comme chemins absolus. Pour
les références `id=N`, il réutilise `load_field_records()` et vérifie l'identifiant,
la référence documentaire, la personne déclarée et le type de source. Cet importeur
de démonstration ne prend pas encore en charge les emplacements de pages PDF.

### Interfaces et règles d'import

`Catalog(path)` ouvre la connexion. Le bloc `with` la ferme automatiquement.

| Méthode | Entrées et résultat |
|---|---|
| `initialize()` | Initialise une base vide ou vérifie le schéma existant. |
| `register(dossiers=(), persons=(), documents=())` | Reçoit les objets typés et retourne un `ImportSummary` des nouvelles entités. |
| `list_dossiers()` | Retourne les dossiers et leurs identifiants de personnes. |
| `list_persons(dossier_id)` | Retourne les personnes du dossier. |
| `list_documents(dossier_id, person_id=None)` | Retourne ses documents, éventuellement limités à une personne. |
| `get_document(dossier_id, document_id)` | Retourne les métadonnées ou `None` si ce document n'est pas dans le dossier. |

Un dossier inconnu déclenche `DossierNotFoundError` ; il ne provoque aucun repli
vers tous les documents. Une personne absente du périmètre produit une liste vide.

`register()` traite chaque lot dans une transaction explicite : une relation
invalide ou un conflit annule toutes les insertions du lot. Un réimport identique
retourne `ImportSummary(0, 0, 0)`. L'ordre des personnes dans les associations ne
compte pas. Une définition différente sous un identifiant déjà enregistré lève
`CatalogConflictError` ; les titres, noms, sources et associations ne sont pas
écrasés. Il est possible d'ajouter de nouveaux dossiers ou documents, mais les
modifications et suppressions nécessiteront de futures opérations explicites.

### Inspection indépendante

Après l'import, depuis la racine :

```bash
PYTHONPATH=src python - <<'PY'
from catalog import Catalog
from common import CATALOG_FILE

with Catalog(CATALOG_FILE) as catalog:
    catalog.initialize()
    for dossier in catalog.list_dossiers():
        print(dossier.dossier_id, dossier.person_ids)
    document = catalog.get_document('DOS001', 'DOC-CROISE-001')
    print(document.document_id, document.person_ids)
    print('Source :', document.source_path)
    print('Documents P001 :', len(catalog.list_documents('DOS001', 'P001')))
    print('Documents P005 dans DOS001 :', catalog.list_documents('DOS001', 'P005'))
PY
```

Le rapport croisé est lié à `P001` et `P002`. La recherche des documents de `P001`
dans `DOS001` retourne sept références ; celle de `P005` dans ce dossier retourne
une liste vide. L'API peut aussi utiliser `Catalog(':memory:')` pour les tests.
Les tests du catalogue sont inclus dans la commande `unittest` de la section 4.

Cette brique n'impose pas encore le périmètre dans `search.py` et ne fournit pas
d'authentification ou de droits d'accès. Elle stocke des métadonnées déclarées et
des références, sans extraire le texte des sources ni versionner leur contenu.
Le manifeste reste portable ; après déplacement du projet, les chemins absolus
enregistrés nécessiteront une régénération du catalogue dans une nouvelle base.
Pour remplacer SQLite ultérieurement, les contrats métier et les méthodes de
`Catalog` constituent l'interface à préserver ; les scripts de retrieval actuels
restent indépendants de ce catalogue.

## 6. Service d'embedding configurable

Le service transforme des **textes déjà préparés** en vecteurs numériques. Il ne lit
aucun document, n'ajoute pas de métadonnées métier et n'accède pas au catalogue ou à
Qdrant. La construction `Type de champ : ... Information : ...` reste dans
`make_text()`, sans changement.

```text
Indexation : champs validés → make_text() → embed_documents() → stockage
Recherche  : question → embed_query() → recherche vectorielle
```

### Interfaces et implémentation

`src/embeddings.py` expose le protocole `EmbeddingService` :

| Membre | Contrat |
|---|---|
| `embed_documents(texts: Sequence[str])` | Tableau NumPy `float32` de forme `(nombre_de_textes, dimension)`, dans l'ordre d'entrée. |
| `embed_query(question: str)` | Tableau NumPy `float32` de forme `(dimension,)`. |
| `dimension` | Dimension obtenue du modèle, sans constante 384 dans les scripts. |
| `profile` | Objet `EmbeddingProfile` décrivant le calcul. |

`SentenceTransformerEmbedder` implémente ce protocole. Il charge une seule fois le
modèle à sa création, puis réutilise `encode_document()` et `encode_query()`.
Avec MiniLM, le tokenizer produit les tokens, le Transformer calcule leurs
représentations contextuelles, puis le *mean pooling* les regroupe en un vecteur de
384 dimensions. La normalisation donne un vecteur de norme proche de 1.

Le service refuse les entrées vides ou non textuelles et vérifie la forme des
sorties, leur type flottant, l'absence de valeurs non finies et de vecteurs nuls.
Si la normalisation est demandée, il vérifie aussi les normes. Une liste vide de
documents donne un tableau `(0, dimension)` sans appeler l'encodeur.

Avant l'encodage, la longueur est comptée **sans troncature**, en incluant les
instructions et les tokens spéciaux. MiniLM accepte ici au maximum **128 tokens**.
Un dépassement lève `EmbeddingError` avec la position du texte et sa longueur ;
aucun texte n'est découpé ou tronqué automatiquement. Cette implémentation cible
les modèles textuels Sentence Transformers avec un tokenizer unique.

### Configuration

Les paramètres sont centralisés dans `src/config.py`, dans l'objet Pydantic figé
`EMBEDDING_CONFIG` de type `EmbeddingConfig`.

| Paramètre | Valeur par défaut / rôle |
|---|---|
| `model_name` | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`. |
| `revision` | Commit immuable `e8f8c211226b894fcb81acc59f3b34ba3efd5f42` ; une branche comme `main` est refusée. |
| `normalize_embeddings` | `True`. |
| `batch_size` | `32`, entier strictement positif. |
| `device` | `None` : détection automatique ; `cpu` ou un périphérique explicite peut être choisi. |
| `local_files_only` | `True` : aucune récupération de poids sur Internet pendant le chargement. |
| `query_prompt` | `None` : instruction de question définie par le modèle, sinon instruction par défaut. |
| `document_prompt` | `None` : première instruction disponible parmi `document`, `passage`, `corpus`, sinon instruction par défaut. |

Une instruction `""` désactive explicitement le préfixe. Le service résout les
instructions effectives, les enregistre dans le profil et les transmet explicitement
à l'encodeur ; le comptage de tokens utilise les mêmes préfixes. Les textes sources
restent inchangés. Pour MiniLM, les deux instructions effectives sont vides.

Pour télécharger le modèle lors d'une première installation, autoriser explicitement
le chargement en ligne pour cette instance, depuis la racine :

```bash
PYTHONPATH=src python - <<'PY'
from config import EMBEDDING_CONFIG, EmbeddingConfig
from embeddings import SentenceTransformerEmbedder

config = EmbeddingConfig(**{**EMBEDDING_CONFIG.model_dump(), 'local_files_only': False})
embedder = SentenceTransformerEmbedder(config)
print(embedder.profile.model_name, embedder.profile.revision)
PY
```

Les commandes habituelles utilisent ensuite la copie en cache. NumPy est déclaré
comme dépendance directe ; Qdrant Client est requis en version `>=1.19.1,<2` pour
le raccord aux métadonnées de collection vérifié dans ce prototype.

### Profils et compatibilité

`EmbeddingProfile` enregistre la version de son schéma, le backend et sa version,
le modèle, sa révision, la dimension, la normalisation, la longueur maximale,
les instructions effectives et la précision `float32`. Les versions de Transformers
et de Torch sont également enregistrées pour cette implémentation. Un autre backend
peut déclarer ces deux versions à `None` s'il ne les utilise pas.

`profile.fingerprint` est une empreinte SHA-256 de cette définition. Le périphérique,
la taille des lots et la politique de cache ne font pas partie de l'identité du
calcul. Les versions logicielles y sont incluses par prudence : une mise à jour peut
donc demander une réindexation. Des écarts numériques mineurs entre CPU et GPU
restent possibles même avec le même profil.

Le petit module `src/index_metadata.py` raccorde ces informations à Qdrant :

- `make_index_metadata()` prépare le profil et `TEXT_BUILDER_VERSION`.
- `ensure_collection_compatible()` vérifie le profil, la dimension, la distance
  cosinus et la version de préparation des textes avant la recherche.

Le profil est publié dans la collection **après** la réussite de l'insertion.
Une collection absente, sans profil, incomplète ou incompatible est refusée par
`retrieve()`, avant le calcul du vecteur de question et la recherche. Une dimension
identique entre deux modèles ne suffit pas. Un échec d'indexation avant publication
du profil laisse un index non utilisable automatiquement ; il faut choisir une
nouvelle collection ou supprimer explicitement la collection incomplète avant de
réessayer. Il n'y a pas de récupération ou de migration automatique.

La collection V2 contient les mêmes 48 champs que la V1. Le catalogue SQLite et
ses deux rapports croisés restent indépendants et ne sont pas réindexés ici.

Pour changer de modèle ou d'instructions, modifier la configuration, renseigner
une révision précise et choisir **un nouveau nom de collection** dans `src/common.py`,
puis exécuter l'indexation. Pour changer la construction des textes, modifier aussi
`TEXT_BUILDER_VERSION`. L'application ne convertit pas les anciens vecteurs et ne
remplace pas un index dont le profil est différent. Le remplacement complet de
l'adaptateur de stockage reste une brique ultérieure.

### Inspection et tests indépendants

Depuis la racine, sans ouvrir Qdrant :

```bash
PYTHONPATH=src python - <<'PY'
from common import load_documents, make_text
from embeddings import SentenceTransformerEmbedder

embedder = SentenceTransformerEmbedder()
texts = [make_text(record) for record in load_documents()]
vectors = embedder.embed_documents(texts)
question = embedder.embed_query('Où Jean Dupont est-il décédé ?')
print(vectors.shape, vectors.dtype)  # (48, 384) float32
print(question.shape)               # (384,)
print(embedder.profile.model_dump())
print('Empreinte :', embedder.profile.fingerprint)
PY
```

`src/index.py`, `src/search.py` et `src/evaluate.py` utilisent maintenant ce même
service. `retrieve()` reçoit un `EmbeddingService` ; toute implémentation respectant
ce protocole peut le remplacer, sans hériter d'une classe particulière. Le profil
doit décrire honnêtement le calcul de cette implémentation, et l'index doit avoir
été construit avec un profil compatible.

Les tests automatiques n'utilisent pas les poids réels : un encodeur fictif permet
de tester le contrat, les instructions, les limites et les erreurs. Les tests de
raccord utilisent Qdrant en mémoire et vérifient notamment le refus de profils
différents à dimension égale, la conservation de la V1 et l'absence de profil publié
lors d'un échec simulé. Ils font partie de la commande `unittest` de la section 4.
La comparaison réelle avec les vecteurs historiques et l'évaluation MiniLM doivent
être exécutées séparément ; les tests avec encodeur fictif ne mesurent pas la
qualité du retrieval.

Lors de la validation de cette brique, les **77 tests** ont réussi. Les calculs
réels ont été exécutés sur CPU et hors ligne : les 48 vecteurs documentaires ont
la forme `(48, 384)`, et leur écart maximal avec ceux de la collection V1 est
`9.31e-8`. Le profil utilisé porte l'empreinte courte `c99ab5b252f0`.

| Évaluation réelle sur les 32 questions | Hit@1 | Recall@5 |
|---|---|---|
| Dense seul | 25 % | 34,4 % |
| Dense + filtre personne | 25 % | 100 % |

Ces résultats reproduisent la référence précédente ; ils n'indiquent pas une
amélioration du classement. Les fichiers JSON, le catalogue SQLite et la collection
V1 ont été conservés.

## Comparaisons futures du retrieval

1. Embedding avec/sans nom du champ et avec/sans contexte.
2. Recherche structurée exacte vs dense vs hybride (BM25 + dense).
3. Un champ par vecteur vs un document complet par vecteur.
4. Cas pièges : *lieu de décès* vs *lieu de disparition* ; plusieurs personnes ayant le même lieu ; témoignages contradictoires.
5. Plusieurs modèles multilingues (BGE-M3, E5), avec un jeu de test indépendant.

**Confidentialité** : pas de vrais dossiers, et aucun service externe d'inférence pour des données sensibles sans autorisation explicite.
