> Archive documentaire conservée le 25 novembre 2026. Décrit une étape passée ; utiliser le [guide actuel](../../README.md) pour exploiter BGE-M3. Les commandes et chemins en code se lisent depuis la racine du projet.

# Découpage de textes fictifs : titre et bornes

Modèle : `qwen3.8:27b-mlx` sur `wired` (Ollama 0.40.13).
Les trois documents fictifs ont été envoyés dans un seul appel, avec un schéma JSON.

## Message système exact

```text
Découpe chaque document fictif en passages contigus par sujet. Conserve tous les blocs, une seule fois et dans leur ordre d’origine. Garde avec chaque information les phrases qui la précisent, la nuancent ou la corrigent. Pour chaque passage, renvoie uniquement un titre descriptif, le premier bloc (start_ref) et le dernier bloc (end_ref), bornes incluses. Un passage ne traverse pas deux documents. Reprends un libellé du document quand il convient. Sinon, nomme le sujet avec des mots du passage. N’ajoute ni résumé, ni déduction, ni attribution. Ne recopie pas le corps du passage : il sera récupéré à partir des bornes.
```

## Texte exact envoyé

```text
Document 1
[B01] Fiche fictive de suivi : Nora Belin.
[B02] Dernière localisation rapportée : gare de Valbrune, 12 mars.
[B03] Le témoin dit l’avoir reconnue de dos ; l’identification n’est pas confirmée.
[B04] Vérification du registre : aucune mention de Nora le 12 mars.
[B05] Ce registre est incomplet entre 18 h et 20 h.
[B06] Suite à donner : demander le registre complet.

Document 2
[A1] La mairie dit qu’Ana Derval a été évacuée vers Mont-Rive, pas son frère Elias.
[A2] Un voisin dit avoir aperçu Elias près du lac.
[A3] Il admet qu’il a pu se tromper de personne.

Document 3
[B1] Pour Camille, le 8 mai désigne son dernier appel, pas une disparition confirmée.
[B2] Une attestation indique Port-Lys comme lieu de décès.
[B3] L’attestation concerne un homonyme. Le décès de Camille n’est pas établi.
[B4] Note logistique : réunion d’équipe déplacée à 16 h.
```

## Réponse exacte de Qwen

```json
{
  "passages": [
    {
      "title": "Suivi de Nora Belin et vérification du registre",
      "start_ref": "B01",
      "end_ref": "B06"
    },
    {
      "title": "Évacuation d’Ana Derval et localisation d’Elias",
      "start_ref": "A1",
      "end_ref": "A3"
    },
    {
      "title": "Statut de Camille et attestation de décès",
      "start_ref": "B1",
      "end_ref": "B3"
    },
    {
      "title": "Note logistique sur la réunion d’équipe",
      "start_ref": "B4",
      "end_ref": "B4"
    }
  ]
}
```

## Passages reconstruits par le programme

**Document 1 — Suivi de Nora Belin et vérification du registre** (`B01` à `B06`)

```text
Fiche fictive de suivi : Nora Belin.
Dernière localisation rapportée : gare de Valbrune, 12 mars.
Le témoin dit l’avoir reconnue de dos ; l’identification n’est pas confirmée.
Vérification du registre : aucune mention de Nora le 12 mars.
Ce registre est incomplet entre 18 h et 20 h.
Suite à donner : demander le registre complet.
```

**Document 2 — Évacuation d’Ana Derval et localisation d’Elias** (`A1` à `A3`)

```text
La mairie dit qu’Ana Derval a été évacuée vers Mont-Rive, pas son frère Elias.
Un voisin dit avoir aperçu Elias près du lac.
Il admet qu’il a pu se tromper de personne.
```

**Document 3 — Statut de Camille et attestation de décès** (`B1` à `B3`)

```text
Pour Camille, le 8 mai désigne son dernier appel, pas une disparition confirmée.
Une attestation indique Port-Lys comme lieu de décès.
L’attestation concerne un homonyme. Le décès de Camille n’est pas établi.
```

**Document 3 — Note logistique sur la réunion d’équipe** (`B4` à `B4`)

```text
Note logistique : réunion d’équipe déplacée à 16 h.
```

## Observation

Les 13 blocs sont couverts exactement une fois, dans leur ordre d’origine. Les quatre paires ciblées entre une information et sa réserve restent dans le même passage. La note logistique, précédemment omise, est cette fois isolée.

Le découpage reste large : les documents 1 et 2 sont chacun conservés dans un seul passage. Le titre « localisation d’Elias » ne reprend pas le caractère incertain du témoignage, même si cette réserve est conservée mot pour mot dans le passage.

Durée observée : 4.73 s pour cet appel. Il s’agit d’un essai sur trois textes courts, sans extraction PDF ni mesure de pertinence de recherche.
