# Architecture actuelle

Révisée le 25 novembre 2026 à partir du code et du manifeste web local. Référence : BGE-M3 avec préparation contexte + cohérent. Le manifeste de chaque installation reste l'autorité pour le profil chargé.

## Composants et points d'entrée

| Responsabilité | Fichiers à lire selon la tâche |
|---|---|
| API FastAPI et contrôles HTTP | [app.py](../src/web/app.py) |
| Orchestration, recherche et imports | [service.py](../src/web/service.py) |
| Gestion des dossiers, déplacements et suppressions | [management.py](../src/web/management.py) |
| Profil actif et reconstruction d'une génération | [index_config.py](../src/web/index_config.py), [migrate_index.py](../src/web/migrate_index.py) |
| Catalogue et contrats métier | [catalog.py](../src/catalog.py), [schemas.py](../src/schemas.py), [scope.py](../src/scope.py) |
| Validation des champs et préparation du contexte | [data_loader.py](../src/data_loader.py), [catalog_index.py](../src/catalog_index.py) |
| Embeddings et compatibilité | [embeddings.py](../src/embeddings.py), [qdrant_store.py](../src/qdrant_store.py) |
| Extraction et ingestion PDF | [pdf_extraction.py](../src/pdf_extraction.py), [ingestion.py](../src/ingestion.py), [passage_index.py](../src/passage_index.py) |
| Segmentation et documents longs | [segmentation.py](../src/segmentation.py), [coherent_segmentation.py](../src/coherent_segmentation.py), [long_segmentation.py](../src/long_segmentation.py) |
| Reformulation, reranking et transport LLM | [query_rewriting.py](../src/query_rewriting.py), [reranking.py](../src/reranking.py), [ollama_client.py](../src/ollama_client.py) |
| Interface React | [App.tsx](../frontend/src/App.tsx), [client API](../frontend/src/api/client.ts), [composants](../frontend/src/components), [i18n.tsx](../frontend/src/i18n.tsx) |

## Parcours des données

```text
Navigateur React → API locale FastAPI → dossier explicite dans le catalogue
  Import PDF → fichier reçu + tâche SQLite
    → extraction pypdf et pages
    → segmentation Qwen + contrôle d'alignement
    → passages exacts + artefact/checkpoints
    → embeddings BGE-M3 → Qdrant → statut terminé

  Recherche → reformulation Qwen ou question originale en repli
    → embedding BGE-M3 → candidats du dossier dans les champs et passages PDF
    → fusion cosinus limitée à 30 candidats par défaut
    → contrôle des sources → reranking Qwen ou repli cosinus
    → cinq extraits maximum + pages + jugement de pertinence
```

Les nombres de candidats et les versions de prompts sont détaillés dans le [guide d'exploitation](../README-web.md). Le navigateur ne contacte pas le service LLM.

## Autorités et persistance

| Emplacement | Responsabilité et précaution |
|---|---|
| `data/` et PDF reçus | Contenu source ; les fichiers de démonstration versionnés sont fictifs. |
| `catalogue.sqlite` | Identifiants, relations dossier/personne/document et provenance. |
| `web_data/jobs.sqlite` | Tâches d'import et état de gestion des dossiers, notamment archivage. |
| `web_data/active_index.json` | Profil web chargé : encodeur, collections, préparation et emplacement des artefacts. |
| `web_data/indexes/<génération>/` | Stockage Qdrant et artefacts propres à une génération BGE-M3. |
| Artefacts de la génération | Texte extrait, pages, segmentation et passages exacts ; checkpoints dans le sous-répertoire `checkpoints/`. |
| `web_data/document-move.json`, `document-delete.json` | Journaux de reprise des mutations documentaires. |
| `web_data/previous_index.json` | Référence précédente ; sa réactivation exige de vérifier la cohérence avec le catalogue courant. |

`SPOC_WEB_DATA` déplace le répertoire de travail web, pas automatiquement le catalogue ni les chemins stockés dans un manifeste. Ne pas transférer une session par simple changement de variable.

Les répertoires de données locaux, modèles, caches et sorties ne sont pas un contexte à lire par défaut. Les [sources](Sources.md) précisent les expériences qui dépendent du poste.

## Contrats à préserver

- **Identité et périmètre** : un document appartient à un seul dossier. Une personne peut apparaître dans plusieurs dossiers ; un homonyme est une autre identité. Les relations passent par les identifiants, jamais par les noms. Le dossier est obligatoire pour la recherche.
- **Catalogue** : cinq tables métier, contraintes de clés étrangères, schéma versionné. Une base étrangère ou de version inconnue est refusée ; l'initialisation conserve les données existantes.
- **Champs JSON** : `FieldRecord` impose un identifiant entier unique entre 0 et `2**64 - 1` et six propriétés textuelles non vides : `document_id`, `person_id`, `field_name`, `field_label`, `value`, `source_kind`. Les types sont stricts, les propriétés inconnues refusées, les valeurs sources conservées. Le rattachement au catalogue est validé avant l'indexation.
- **Contexte des champs** : la préparation web inclut la personne explicitement associée, sans inférer une identité depuis le texte. Les valeurs et identifiants d'origine restent conservés.
- **Source PDF** : la référence visuelle est le PDF. Le texte indexé est celui extrait par pypdf ; positions Python avec fin exclue et pages physiques à partir de 1. Les titres Qwen sont des propositions ; les corps des passages restent tirés du texte source.
- **Segmentation** : l'ancrage cohérent restaure les frontières sur la source et conserve les zones omises. Une sortie invalide peut produire un repli technique signalé ; une panne de transport ou une sortie tronquée fait échouer l'import.
- **Embeddings** : pas de troncature silencieuse. Les passages sont subdivisés selon le tokenizer actif. Le profil inclut modèle, révision, instructions, dimension, normalisation et versions pertinentes.
- **Compatibilité** : une même dimension ne suffit pas. Profil, préparation des textes et version des métadonnées sont vérifiés ; une collection incompatible n'est pas convertie automatiquement.
- **Publication** : seuls les documents aux tâches terminées et artefacts présents participent à la recherche PDF. Les extraits sont revérifiés contre la source avant restitution et consultation du cache du reranker.
- **Mutations** : archivage réversible ; déplacement et suppression coordonnent catalogue, tâches, artefacts et index actif. Les générations antérieures ne sont pas synchronisées automatiquement.
- **Restitution** : les jugements Qwen peuvent être erronés. Ni le score cosinus ni l'absence de preuve dans cinq candidats ne démontrent la vérité ou l'absence d'information dans tout le dossier.

## Frontières de configuration et validation

Le [profil BGE-M3](../src/web/index_config.py) est distinct des valeurs par défaut de [config.py](../src/config.py). La classe `WebIndexConfig.load()` conserve un comportement de compatibilité en l'absence de manifeste ; ce chemin n'est pas le parcours d'installation courant. Voir l'[historique](history/README.md) seulement pour ces anciennes commandes.

Une migration construit une génération distincte, vérifie les sources et profils, puis remplace atomiquement le manifeste. Les instructions et restrictions de retour arrière sont regroupées dans le [guide web](../README-web.md#reconstruction-de-lindex-bge-m3).

Les [tests](../tests) vérifient les contrats, reprises et erreurs avec des modèles simulés et des stockages temporaires. Les [évaluations](Sources.md#évaluations-et-portée) ont des corpus et des limites propres ; leurs résultats ne valent pas validation générale de l'application.
