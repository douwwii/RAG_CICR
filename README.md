# SPOC CICR — Retrieval V1 (100 % fictif)

**Objectif** : rechercher dans des dossiers et des documents entièrement fictifs. Le socle historique indexe des champs de formulaires ; l’interface web ajoute l’import de PDF numériques, la segmentation par Qwen et la consultation des sources. Aucun document réel du CICR. Pas d’OCR ni de génération de réponses RAG.

**Interface web locale** : voir [la procédure de démarrage et de démonstration](README-web.md). Les commandes ci-dessous décrivent le socle historique ; il n’est pas nécessaire de reconstruire un index existant pour lancer l’interface.

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
python src/import_catalog.py
python src/index.py
```

- Lit `data/documents.json`.
- Transforme chaque champ en texte `Type de champ : ... Information : ...`.
- Calcule un embedding **384 dimensions** avec MiniLM multilingue.
- Crée une collection Qdrant locale dans `qdrant_data/`.
- Stocke pour chaque point un vecteur, un identifiant et les champs d'origine dans le *payload*.
- Vérifie les références contre le catalogue SQLite avant de charger MiniLM.
- Utilise la collection `cicr_synthetic_minilm_v3`, avec profil d'embedding,
  version des métadonnées, dossier et provenance de chaque champ.
- Réexécuter le script **remplace cette collection si son profil est compatible**
  (ne pas l'utiliser pour des données à conserver). Un index sans profil ou incompatible
  est refusé. Les anciennes collections V1 et V2 sont conservées.

## 2. Chercher des informations

```bash
python src/search.py "Où la personne est-elle décédée ?" --dossier DOS001 --person P001
python src/search.py "Où la personne est-elle décédée ?" --dossier DOS001 --person P001 --field lieu_de_deces
python src/search.py "Dans quelle ville a-t-on vu Marie pour la dernière fois ?" --dossier DOS001
```

- `--dossier` est obligatoire : la similarité est calculée parmi les champs de ce dossier.
- Avec `--person` : filtre exact sur `person_id` + similarité sémantique.
- Avec `--field` : filtre exact sur `field_name` en supplément.
- La sortie indique le score cosinus, la valeur, le type de champ, le dossier et la provenance fictive.
- Le filtre d'identité est fourni explicitement : nous ne prétendons pas avoir résolu le nom dans une question libre.

## 3. Évaluer le retrieval

```bash
python src/evaluate.py
```

`data/scoped_queries.json` contient 32 questions, un dossier explicite, la personne
attendue et les identifiants des champs pertinents (*ground truth*). Comparaison :
**dossier seul** vs **dossier + filtre sur personne**. Le fichier historique
`data/queries.json` reste conservé pour les anciennes expériences globales.

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
| `lookup_document(document_id)` | Retrouve la référence globale d’un document pour le rattacher à son dossier lors de l’indexation. |

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

Le périmètre est désormais imposé dans le retrieval par la brique décrite en
section 8. Le catalogue ne fournit pas d'authentification ou de droits d'accès.
Il stocke des métadonnées déclarées et
des références, sans extraire le texte des sources ni versionner leur contenu.
Le manifeste reste portable ; après déplacement du projet, les chemins absolus
enregistrés nécessiteront une régénération du catalogue dans une nouvelle base.
Pour remplacer SQLite ultérieurement, les contrats métier et les méthodes de
`Catalog` constituent l'interface à préserver. Le retrieval reçoit désormais un
catalogue explicite ; le modèle d’embedding et l’adaptateur Qdrant restent indépendants
du catalogue.

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

L’adaptateur `src/qdrant_store.py` raccorde ces informations à Qdrant. Sa méthode
`check_compatibility()` vérifie le profil, la dimension, la distance cosinus et la
version de préparation des textes avant la recherche. Elle reprend les contrôles
de l’ancien module `index_metadata.py`, désormais intégré à l’adaptateur.

Le profil est publié dans la collection **après** la réussite de l'insertion.
Une collection absente, sans profil, incomplète ou incompatible est refusée par
`retrieve()`, avant le calcul du vecteur de question et la recherche. Une dimension
identique entre deux modèles ne suffit pas. Un échec d'indexation avant publication
du profil laisse un index non utilisable automatiquement ; il faut choisir une
nouvelle collection ou supprimer explicitement la collection incomplète avant de
réessayer. Il n'y a pas de récupération ou de migration automatique.

La collection V2 historique contient les mêmes 48 champs que la V1. La V3 actuelle
conserve leurs textes et ajoute leur rattachement au catalogue (section 8). Les deux
rapports croisés restent absents de l’index.

Pour changer de modèle ou d'instructions, modifier la configuration, renseigner
une révision précise et choisir **un nouveau nom de collection** dans
`VectorStoreConfig` (`src/config.py`),
puis exécuter l'indexation. Pour changer la construction des textes, modifier aussi
`TEXT_BUILDER_VERSION`. L'application ne convertit pas les anciens vecteurs et ne
remplace pas un index dont le profil est différent. L’interface de stockage est
décrite dans la section 7.

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

Lors de la validation initiale du service d’embedding, les **77 tests** ont réussi. Les calculs
réels ont été exécutés sur CPU et hors ligne : les 48 vecteurs documentaires ont
la forme `(48, 384)`, et leur écart maximal avec ceux de la collection V1 est
`9.31e-8`. Le profil utilisé porte l'empreinte courte `c99ab5b252f0`.

| Évaluation historique globale sur les 32 questions | Hit@1 | Recall@5 |
|---|---|---|
| Dense seul | 25 % | 34,4 % |
| Dense + filtre personne | 25 % | 100 % |

Ces résultats reproduisent la référence précédente ; ils n'indiquent pas une
amélioration du classement. Les fichiers JSON, le catalogue SQLite et la collection
V1 ont été conservés.

## 7. Adaptateur de stockage vectoriel

Le stockage reçoit des vecteurs déjà calculés et leurs métadonnées. Il ne charge
aucun modèle, ne lit pas les sources et ne déduit pas le dossier ou la personne
depuis une question. Le dossier lui est fourni dans les filtres obligatoires.
`index.py`, `search.py` et `evaluate.py` utilisent l’interface
`VectorStore` de `src/vector_store.py` ; seul `src/qdrant_store.py` manipule les
points, collections et filtres propres à Qdrant.

```text
Indexation : champs validés → textes → EmbeddingService → VectorStore → Qdrant local
Recherche  : dossier validé + question → EmbeddingService → VectorStore → list[VectorHit]
```

### Entrées et sorties

Les contrats Pydantic sont stricts, figés et refusent les propriétés inconnues :

| Objet | Contenu |
|---|---|
| `VectorRecord` | Les propriétés de `FieldRecord`, plus `embedding_text`, `dossier_id`, `source_path` et `source_locator`. |
| `VectorFilters` | `dossier_id` obligatoire ; `person_id` et `field_name` facultatifs ; les filtres renseignés sont combinés par ET. |
| `VectorHit` | `id`, `score` cosinus fini et `payload` de type `VectorRecord`. L’identifiant doit correspondre à `payload.id`. |

Les textes et références sont conservés exactement, y compris leurs espaces et
sauts de ligne. Le score reste une mesure de similarité, sans interprétation comme
probabilité ou vérité de l’information. Ces contrats ciblent les 48 champs actuels,
avec des identifiants entiers ; ils ne constituent pas encore un schéma de chunks
de PDF ou de rapports libres.

### Interface publique

| Méthode | Contrat |
|---|---|
| `check_compatibility(profile, text_builder_version)` | Refuse un index absent, incomplet ou incompatible. |
| `rebuild(records, vectors, *, profile, text_builder_version)` | Reconstruit la collection ciblée avec un lot complet non vide et un tableau flottant `(nombre_de_records, dimension)`. |
| `search(vector, filters, top_k=5, *, profile, text_builder_version)` | Reçoit un vecteur `(dimension,)`, exige un filtre avec dossier et retourne les `VectorHit` classés par score décroissant. |
| `close()` | Ferme le client et libère les ressources locales. |

La méthode `search()` exige elle aussi le profil et la version de préparation :
elle protège les appels directs à l’adaptateur. `retrieve()` effectue en plus un
contrôle avant le calcul de l’embedding de question pour éviter un calcul inutile
si l’index est incompatible. Les filtres vides ou de mauvais type et un `top_k`
non entier ou inférieur à 1 sont refusés. Un filtre sans correspondance donne une
liste vide, sans élargir la recherche. Les propriétés de filtre inconnues sont refusées
plutôt qu’ignorées. Un objet filtre absent ou sans dossier est refusé.

Avant toute suppression, `rebuild()` valide l’ensemble des métadonnées, l’unicité
des identifiants, le nombre et la dimension des vecteurs, leur type flottant, leur
représentation en `float32`, leur finitude, leur norme non nulle et, si le profil
l’exige, leur normalisation. Il refuse ensuite de remplacer une collection dont
le profil, la distance ou la préparation des textes sont incompatibles.

La reconstruction supprime puis recrée uniquement la collection configurée. Le
profil est publié après une insertion terminée et la vérification du nombre de
points. Une erreur avant publication laisse une collection sans profil utilisable,
refusée par la recherche. **Cette reconstruction n’est pas transactionnelle** :
l’ancien index n’est pas restauré si une panne survient après sa suppression. Pour
reprendre, choisir une nouvelle collection ou supprimer explicitement la collection
incomplète ; il n’y a pas de récupération automatique ni de mise à jour incrémentale.

Les opérations refusées ou les résultats mal formés lèvent `VectorStoreError` ;
les incompatibilités conservent `EmbeddingCompatibilityError`. La cause d’une
erreur Qdrant est conservée pour le diagnostic.

### Configuration et remplacement

`src/config.py` centralise `VECTOR_STORE_CONFIG`, instance figée de
`VectorStoreConfig`, et `DEFAULT_TOP_K=5` pour les recherches usuelles :

| Paramètre | Valeur par défaut |
|---|---|
| `backend` | `qdrant`, seul backend implémenté. |
| `path` | Objet `Path` pointant vers `qdrant_data/` à la racine du projet. |
| `collection_name` | `cicr_synthetic_minilm_v3`. |

`open_vector_store(config)` crée l’adaptateur et ouvre son client. L’import de
Qdrant est différé jusqu’à cet appel. Les alias `DB_DIR` et `COLLECTION` de
`common.py` restent disponibles, mais leurs valeurs proviennent de la configuration ;
la fonction `common.client()` a été retirée. `QdrantVectorStore` accepte aussi un
client injecté pour les tests et prend en charge sa fermeture. Utiliser un seul
processus à la fois sur le même répertoire Qdrant local.

Pour remplacer le stockage, implémenter les quatre méthodes du protocole avec
les mêmes contrats et la même sémantique de score cosinus, puis adapter la fabrique
et les valeurs de backend admises par la configuration. Les modèles, la construction
des textes, `retrieve()` et les règles d’évaluation restent réutilisables. Une
migration effective des données vers un nouveau backend sera à effectuer séparément.
Le service d’embedding peut aussi être remplacé indépendamment du stockage.

### Utilisation et inspection

Les commandes des sections 1 à 3 restent valables. Depuis la racine, pour inspecter
les objets retournés par le retrieval :

```bash
PYTHONPATH=src python -B - <<'PY'
from catalog import Catalog
from common import CATALOG_FILE
from embeddings import SentenceTransformerEmbedder
from search import retrieve
from vector_store import open_vector_store

with Catalog(CATALOG_FILE, read_only=True) as catalog:
    embedder = SentenceTransformerEmbedder()
    store = open_vector_store()
    try:
        hits = retrieve(store, embedder, 'Où la personne est-elle décédée ?',
                        catalog=catalog, dossier_id='DOS001',
                        person_id='P001', field_name='lieu_de_deces')
        for hit in hits:
            print(hit.id, hit.score, hit.payload.document_id)
            print(hit.payload.value)
            print(hit.model_dump())
    finally:
        store.close()
PY
```

`retrieve()` reçoit désormais un `VectorStore` en premier argument, à la place
d’un client Qdrant brut. Les propriétés d’un résultat se lisent par exemple avec
`hit.payload.value` ; `hit.model_dump()` fournit un dictionnaire sérialisable.
Pour évaluer uniquement le retrieval, les scripts actuels restent indépendants de
tout LLM génératif.

### Tests indépendants et limites

Sans charger MiniLM ni utiliser l’index du projet :

```bash
python -B -m unittest discover -s tests -p 'test_vector_store.py' -v
```

Les tests utilisent Qdrant en mémoire ou un répertoire temporaire, des vecteurs
connus et un stockage fictif. Ils vérifient la provenance, le classement, les scores,
les filtres, la persistance après fermeture/réouverture, les refus avant écrasement,
les erreurs d’écriture et les profils incomplets. Ils vérifient aussi que les
scripts et contrats s’importent sans Qdrant, Torch ou Sentence Transformers.

Lors de la validation initiale de l’adaptateur, les **98 tests** ont réussi, dont 21 nouveaux
tests dédiés au stockage. `pip check` ne signale aucun conflit de dépendances.
L’indexation réelle a été exécutée sur CPU et hors ligne. Par rapport à un instantané
de la V2 pris avant reconstruction, les 48 métadonnées et vecteurs sont identiques,
ainsi que les classements et scores des **64 recherches** (32 questions avec et sans
filtre personne) ; l’écart numérique maximal observé est nul dans cet essai. Le profil
reste `c99ab5b252f0`. Les fichiers JSON, le catalogue et les octets de la collection V1
ont été conservés. Cette validation confirme le comportement existant et ne mesure
aucune amélioration de la pertinence.

Sous Python 3.14 avec Qdrant Client 1.19.1, un `ResourceWarning` peut signaler la
connexion SQLite temporaire de détection des capacités internes de Qdrant
(`local/persistence.py`), distincte des clients explicitement fermés par l’adaptateur.

Le raccord au catalogue et le filtrage obligatoire par dossier sont décrits ci-dessous.
L’extraction PDF et le chunking restent à implémenter dans leurs briques dédiées.

## 8. Raccord au catalogue et périmètre obligatoire par dossier

Le catalogue est l’autorité pour le rattachement d’un document à son dossier. Le
rattachement passe par `document_id`, jamais par le nom ou la seule personne : la
même personne peut appartenir à plusieurs dossiers et des personnes peuvent être
homonymes. Les dossiers sont sélectionnés explicitement par identifiant dans cette
version ; aucune déduction automatique depuis une question n’est implémentée.

### Indexation et provenance

`src/catalog_index.py` expose `prepare_index_records(records, catalog, source_path)`.
Pour chaque `FieldRecord`, il utilise `Catalog.lookup_document(document_id)` et
vérifie la référence documentaire, la présence de la personne dans les associations
du document, le type de source, le chemin du corpus et l’emplacement exact `id=N`.
Il produit ensuite un `VectorRecord` enrichi du dossier et de sa provenance. Le
JSON original et la fonction `make_text()` restent inchangés. Toutes ces vérifications
précèdent le chargement de MiniLM et l’ouverture du stockage vectoriel.

Le contrat des métadonnées porte `VECTOR_RECORD_SCHEMA_VERSION=2`, enregistré sous
`vector_record_schema_version` dans la collection. Une ancienne collection sans
cette version est refusée, même si son modèle et ses dimensions sont identiques.
Le nom par défaut est `cicr_synthetic_minilm_v3` ; les collections V1 et V2 restent
conservées. Cette V3 contient les 48 champs actuels : 24 pour `DOS001`, 24 pour
`DOS002`. Les deux rapports croisés ne sont toujours pas extraits ou indexés.

`Catalog(path, read_only=True)` ouvre un catalogue existant en lecture seule et
vérifie sa version. Une base absente n’est pas créée automatiquement. L’importeur
reste la commande explicite pour initialiser le catalogue. Le format SQLite
et sa version de schéma restent inchangés.

### Résolution du périmètre et recherche

`src/scope.py` est indépendant de NumPy, du modèle et de Qdrant. Il expose :

| Objet ou fonction | Rôle |
|---|---|
| `SearchScope` | Dossier, personne facultative et références documentaires du périmètre. |
| `resolve_scope(catalog, dossier_id, person_id=None)` | Valide l’identifiant et récupère les documents du dossier, éventuellement limités à une personne. |
| `validate_field_reference(...)` | Vérifie la provenance d’un champ JSON contre sa référence de catalogue. |
| `ScopeError` | Signale une incohérence de périmètre ou de provenance. |

La signature du retrieval est désormais :

```python
retrieve(store, embedder, question, *, catalog, dossier_id,
         person_id=None, field_name=None, top_k=5)
```

Le dossier et le catalogue sont obligatoires. Un dossier inconnu déclenche
`DossierNotFoundError` avant l’encodage ou la requête vectorielle. Un dossier vide,
une personne inconnue ou une personne absente du dossier produisent une liste
vide sans encoder la question ni interroger Qdrant. Des documents présents au
catalogue peuvent toutefois ne pas encore avoir de passages indexés.

L’adaptateur applique le filtre de dossier **avant le classement et le top-K**.
Il combine les filtres par ET, refuse les appels sans dossier et vérifie que les
résultats respectent ces filtres. Le retrieval contrôle ensuite tous les résultats
contre le catalogue : dossier, document, personne, type de source, chemin et
emplacement. Une incohérence provoque une erreur ; aucun lot partiel ni résultat
extérieur n’est retourné. Ce contrôle s’applique aussi à un backend alternatif.

Exemples, après l’import du catalogue et l’indexation :

```bash
python src/search.py "Où la personne est-elle décédée ?" --dossier DOS001 --person P001 --field lieu_de_deces
python src/search.py "Quels témoignages figurent dans le dossier ?" --dossier DOS002 --field temoignage
python src/search.py "question" --dossier DOS001 --person P005
```

Le premier exemple retrouve le champ 2, `DOC-P001-lieu_de_deces`, et affiche le
chemin du corpus ainsi que `id=2`. Le dernier donne une liste vide : `P005` appartient
au dossier `DOS002` dans notre catalogue fictif. Un catalogue différent peut être
fourni à la recherche avec `--catalog /chemin/catalogue.sqlite`.

### Annotations et tests

`ScopedEvaluationCase` ajoute `dossier_id` au contrat d’évaluation historique.
`data/scoped_queries.json` conserve les 32 questions et leurs réponses attendues,
avec 16 questions pour chaque dossier. Les dossiers y sont enregistrés explicitement.
`load_scoped_evaluation_cases(path, records, catalog)` vérifie les identifiants,
la personne et l’appartenance de toutes les références pertinentes au dossier
annoté. L’évaluation vérifie aussi les sources avant de charger le modèle.

`evaluate.py` compare désormais **dossier seul** et **dossier + filtre personne**.
Les mesures globales des sections précédentes sont historiques : changer le nombre
de candidats peut modifier le rappel sans améliorer le modèle d’embedding.

Sans MiniLM et sans utiliser l’index du projet :

```bash
python -B -m unittest discover -s tests -p 'test_scope.py' -v
```

Les tests créent leurs propres catalogues et collections temporaires. Ils couvrent
notamment un résultat très proche dans un autre dossier, une même personne dans
deux dossiers, des homonymes, les documents partagés, les dossiers vides ou inconnus,
les références incohérentes, les anciens schémas et les résultats incorrects d’un
backend alternatif. Les tests de commande vérifient les refus avant tout chargement
du modèle ou accès à Qdrant.

La validation de cette brique comprend **124 tests réussis**, dont 26 nouveaux tests
dans `test_scope.py`. `pip check` ne signale aucun conflit. L’indexation réelle a été
exécutée sur CPU et hors ligne : le profil d’embedding reste `c99ab5b252f0` et les 48
vecteurs sont identiques à ceux de la V2. Les 64 recherches ont les mêmes classements
et scores que la V2 restreinte aux mêmes candidats (écart maximal observé nul).
Les octets des fichiers JSON historiques, du catalogue et des collections V1/V2
ont été conservés.

| Évaluation réelle des 32 questions avec dossier | Hit@1 | Recall@5 |
|---|---|---|
| Dossier seul | 25 % | 50 % |
| Dossier + filtre personne | 25 % | 100 % |

Le rappel de 50 % s’obtient avec 24 champs candidats par dossier au lieu de 48
dans l’évaluation globale historique ; le modèle reste inchangé. Les commandes
réelles ont aussi confirmé le refus sans dossier ou pour un dossier inconnu, et
l’absence de résultat pour `DOS001` avec `P005`.

L’isolation porte sur le périmètre de recherche déclaré ; aucun système de droits
utilisateur n’est implémenté. Les références sont contrôlées, mais le contenu des
fichiers sources n’est pas versionné ou comparé par empreinte à chaque recherche.
La reconstruction de la V3 garde les limites de reprise décrites en section 7.

## Comparaisons futures du retrieval

1. Embedding avec/sans nom du champ et avec/sans contexte.
2. Recherche structurée exacte vs dense vs hybride (BM25 + dense).
3. Un champ par vecteur vs un document complet par vecteur.
4. Cas pièges : *lieu de décès* vs *lieu de disparition* ; plusieurs personnes ayant le même lieu ; témoignages contradictoires.
5. Plusieurs modèles multilingues (BGE-M3, E5), avec un jeu de test indépendant.

**Confidentialité** : pas de vrais dossiers, et aucun service externe d'inférence pour des données sensibles sans autorisation explicite.
