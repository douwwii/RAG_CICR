> Archive documentaire conservée le 25 novembre 2026. Décrit une étape passée ; utiliser le [guide actuel](../../README.md) pour exploiter BGE-M3. Les commandes et chemins en code se lisent depuis la racine du projet.

# Découpage thématique avec Qwen : trois textes fictifs

Modèle : `qwen3.8:27b-mlx` déjà chargé sur `wired`. Ollama : `0.40.13`.

**Résultat : 13 blocs conservés dans 5 passages.** Les 4 liens ciblés entre une information et sa réserve ont été gardés dans le même passage.

Qwen a reçu des blocs numérotés et a proposé des titres, des références de contenu et des références de contexte. Le texte des passages a été repris dans les blocs sources par le programme. Les titres ci-dessous sont les titres réellement proposés par Qwen.

## Les trois textes et leurs découpages

### 1. Fiche avec libellés et réserves

**Texte envoyé**

- `B01` : Fiche fictive de suivi : Nora Belin.
- `B02` : Dernière localisation rapportée : gare de Valbrune, 12 mars.
- `B03` : Le témoin dit l’avoir reconnue de dos ; l’identification n’est pas confirmée.
- `B04` : Vérification du registre : aucune mention de Nora le 12 mars.
- `B05` : Ce registre est incomplet entre 18 h et 20 h.
- `B06` : Suite à donner : demander le registre complet.

**Découpage obtenu**

| Titre proposé | Blocs du passage | Contexte |
|---|---|---|
| Identification et localisation préliminaire | B01, B02, B03 | — |
| Contradiction avec le registre et suite à donner | B04, B05, B06 | B02 |

Le doute sur l’identification reste avec la localisation rapportée. Le registre incomplet reste avec l’absence de mention. Le bloc B02 est également rattaché en contexte au second passage. Le titre « Contradiction » va plus loin que le texte : une absence dans un registre incomplet ne réfute pas le témoignage.

**Liens vérifiés**

- Localisation et réserve sur l’identification (`B02` → `B03`) : même passage.
- Absence dans le registre et limite du registre (`B04` → `B05`) : même passage.

### 2. Récit libre avec deux personnes

**Texte envoyé**

- `A1` : La mairie dit qu’Ana Derval a été évacuée vers Mont-Rive, pas son frère Elias.
- `A2` : Un voisin dit avoir aperçu Elias près du lac.
- `A3` : Il admet qu’il a pu se tromper de personne.

**Découpage obtenu**

| Titre proposé | Blocs du passage | Contexte |
|---|---|---|
| Évacuation d'Ana Derval et confusion concernant Elias | A1, A2, A3 | — |

Ana et Elias se retrouvent dans le même passage, sans fusion du texte qui les concerne. C’est fidèle au récit, mais le passage est assez large pour une recherche centrée sur Elias.

**Liens vérifiés**

- Témoignage et doute sur l’identité (`A2` → `A3`) : même passage.

### 3. Rectification et homonyme

**Texte envoyé**

- `B1` : Pour Camille, le 8 mai désigne son dernier appel, pas une disparition confirmée.
- `B2` : Une attestation indique Port-Lys comme lieu de décès.
- `B3` : L’attestation concerne un homonyme. Le décès de Camille n’est pas établi.
- `B4` : Note logistique : réunion d’équipe déplacée à 16 h.

**Découpage obtenu**

| Titre proposé | Blocs du passage | Contexte |
|---|---|---|
| Statut de Camille et attestation erronée | B1, B2, B3 | — |
| Note logistique sur le déplacement de réunion | B4 | — |

La note logistique est isolée. Le lieu de décès mentionné reste avec l’avertissement sur l’homonyme. « Attestation erronée » est une interprétation trop forte : le texte dit qu’elle concerne quelqu’un d’autre, sans dire que l’attestation elle-même est fausse.

**Liens vérifiés**

- Lieu de décès mentionné et avertissement sur l’homonyme (`B2` → `B3`) : même passage.

## Conditions de l’essai

| Appel | Format et réglages | Premier texte | Aller-retour |
|---|---|---:|---:|
| Fiche courte (6 blocs) | Schéma JSON, streaming, température 0, sortie plafonnée à 250 jetons | 67.20 s | 69.16 s |
| Deux mini-cas groupés (7 blocs) | Mode JSON, streaming, température 0, sortie plafonnée à 220 jetons | 37.26 s | 39.69 s |

Une première requête sans streaming a expiré après 90 s. Un essai individuel du récit à deux personnes a aussi expiré, sans texte reçu en 110 s. Les deux mini-cas ont ensuite été raccourcis et groupés dans un appel. Les durées ne sont donc pas comparables comme un benchmark, et la cause des délais n’a pas été isolée.

Les contrôles ont vérifié le JSON, l’existence des références, la couverture sans doublon, l’ordre et la contiguïté des passages, ainsi que l’absence de référence entre les deux documents du lot. Les quatre liens ci-dessus sont des vérifications ciblées, pas une mesure générale de la qualité du découpage. Aucun PDF, index ni retrieval n’a été testé ici.

## Consignes utilisées

**Fiche courte :**

> Découpe le texte fictif en passages thématiques. Choisis les limites. Chaque bloc doit figurer une seule fois dans content_refs, dans l'ordre du texte, et les blocs d'un passage doivent se suivre. Reprends les libellés explicites quand ils conviennent. Garde les négations et rectifications avec l'information concernée. Mets dans context_refs les blocs extérieurs nécessaires pour comprendre le passage, sinon []. Renvoie uniquement titres et références.

**Deux mini-cas groupés :**

> Découpe les deux textes fictifs A et B en passages thématiques séparés. Ne mélange pas les documents. Garde chaque bloc exactement une fois dans content_refs, dans l’ordre d’origine, avec des groupes contigus. Préserve les réserves et corrections. Si un bloc extérieur est indispensable pour comprendre un passage, ajoute son identifiant dans context_refs ; sinon []. Donne des titres descriptifs prudents. Réponds uniquement en JSON : {"segments":[{"title":"...","content_refs":["A1"],"context_refs":[]}]}
