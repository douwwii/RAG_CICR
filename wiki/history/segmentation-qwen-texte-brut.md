> Archive documentaire conservée le 25 novembre 2026. Décrit une étape passée ; utiliser le [guide actuel](../../README.md) pour exploiter BGE-M3. Les commandes et chemins en code se lisent depuis la racine du projet.

# Découpage par Qwen à partir du texte brut

Modèle : `qwen3.8:27b-mlx` sur `wired` (Ollama 0.40.13).
Chaque document fictif a été envoyé séparément comme un paragraphe continu, sans identifiants, numéros de blocs ou séparateurs ajoutés. Le système demande à Qwen de choisir lui-même les frontières et de renvoyer chaque titre avec l’extrait recopié.

## Message système exact

```text
Tu reçois le texte brut d’un seul document fictif. Trouve toi-même où le couper par sujets. Fais un nouveau passage quand le sujet change. Garde une information avec les phrases qui la précisent, la nuancent ou la corrigent. Pour chaque passage, donne un titre bref qui nomme uniquement le sujet présent dans cet extrait et le texte exact de l’extrait. Reprends un libellé existant s’il convient. N’ajoute ni déduction, ni attribution, ni résumé. Recopie les caractères du texte, y compris la ponctuation et les apostrophes, sans corriger ni reformuler. Conserve tout le texte dans l’ordre, sans omission ni doublon. Renvoie uniquement le JSON avec une liste passages contenant title et text.
```

## 1. Fiche avec libellés et réserves

**Texte brut envoyé**

```text
Fiche fictive de suivi : Nora Belin. Dernière localisation rapportée : gare de Valbrune, 12 mars. Le témoin dit l’avoir reconnue de dos ; l’identification n’est pas confirmée. Vérification du registre : aucune mention de Nora le 12 mars. Ce registre est incomplet entre 18 h et 20 h. Suite à donner : demander le registre complet.
```

**Réponse exacte de Qwen**

```json
{
  "passages": [
    {
      "title": "Localisation et identification de Nora Belin",
      "text": "Fiche fictive de suivi : Nora Belin. Dernière localisation rapportée : gare de Valbrune, 12 mars. Le témoin dit l’avoir reconnue de dos ; l’identification n’est pas confirmée."
    },
    {
      "title": "Vérification du registre",
      "text": "Vérification du registre : aucune mention de Nora le 12 mars. Ce registre est incomplet entre 18 h et 20 h. Suite à donner : demander le registre complet."
    }
  ]
}
```

Deux extraits retrouvés caractère par caractère dans le texte d’entrée, dans l’ordre et sans omission. Les espaces entre les extraits appartiennent au texte d’origine.

## 2. Récit libre avec deux personnes

**Texte brut envoyé**

```text
La mairie dit qu’Ana Derval a été évacuée vers Mont-Rive, pas son frère Elias. Un voisin dit avoir aperçu Elias près du lac. Il admet qu’il a pu se tromper de personne.
```

**Réponse exacte de Qwen**

```json
{
  "passages": [
    {
      "title": "Évacuation d'Ana Derval",
      "text": "La mairie dit qu’Ana Derval a été évacuée vers Mont-Rive, pas son frère Elias."
    },
    {
      "title": "Aperçu d'Elias près du lac",
      "text": "Un voisin dit avoir aperçu Elias près du lac. Il admet qu’il a pu se tromper de personne."
    }
  ]
}
```

Deux extraits retrouvés caractère par caractère dans le texte d’entrée, dans l’ordre et sans omission. Les espaces entre les extraits appartiennent au texte d’origine.

## 3. Rectification et homonyme

**Texte brut envoyé**

```text
Pour Camille, le 8 mai désigne son dernier appel, pas une disparition confirmée. Une attestation indique Port-Lys comme lieu de décès. L’attestation concerne un homonyme. Le décès de Camille n’est pas établi. Note logistique : réunion d’équipe déplacée à 16 h.
```

**Réponse exacte de Qwen**

```json
{
  "passages": [
    {
      "title": "Statut du décès de Camille",
      "text": "Pour Camille, le 8 mai désigne son dernier appel, pas une disparition confirmée. Une attestation indique Port-Lys comme lieu de décès. L’attestation concerne un homonyme. Le décès de Camille n’est pas établi."
    },
    {
      "title": "Réunion d’équipe",
      "text": "Note logistique : réunion d’équipe déplacée à 16 h."
    }
  ]
}
```

Deux extraits retrouvés caractère par caractère dans le texte d’entrée, dans l’ordre et sans omission. Les espaces entre les extraits appartiennent au texte d’origine.

## Ce que montre cet essai

- La fiche de Nora est séparée entre localisation rapportée et vérification du registre.
- Le récit sépare l’évacuation rapportée d’Ana du témoignage incertain sur Elias.
- La note logistique est isolée. La date rectifiée et l’attestation concernant un homonyme restent groupées ; « Statut du décès de Camille » n’est pas un titre aussi prudent que le texte.
- Les six corps de passage sont des extraits exacts et, ensemble, couvrent les trois entrées.

Le format de sortie et le regroupement des appels ont changé depuis l’essai par bornes. Ce résultat montre que le découpage direct et la copie fidèle sont possibles sur ces trois textes courts. Il ne mesure pas l’effet isolé de la suppression des repères et ne garantit pas la copie sur des PDF longs.
