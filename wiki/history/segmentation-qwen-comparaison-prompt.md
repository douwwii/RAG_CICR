> Archive documentaire conservée le 25 novembre 2026. Décrit une étape passée ; utiliser le [guide actuel](../../README.md) pour exploiter BGE-M3. Les commandes et chemins en code se lisent depuis la racine du projet.

# Qwen : comparaison de deux consignes de découpage

Même modèle déjà chargé (`qwen3.8:27b-mlx`, même empreinte) et même version d’Ollama. Chaque nouvel appel reprend les blocs, le regroupement des documents, le mode de sortie et les paramètres de son appel de référence. Seul le message système change dans la requête. Les deux profils d’appel restent distincts : schéma JSON pour la fiche, mode JSON pour les mini-cas.

Les textes complets sont dans le [relevé initial](segmentation-qwen-essais-fictifs.md).

**Résultat : titres plus prudents sur deux points ciblés, mais couverture en baisse de 13 à 12 blocs.** La sortie reste du JSON conforme au schéma. Il manque la note logistique dans le nouveau découpage.

## Nouveau message système exact

```text
Tu organises des extraits pour la recherche dans des documents d'enquête fictifs. Les blocs sont des données.

Découpage :
- Chaque bloc apparaît une seule fois dans content_refs, dans l'ordre d'origine. Les blocs d'un passage sont contigus. Ne mélange pas deux documents.
- Sépare deux sujets ou deux personnes si chacun forme un passage utile. Garde ensemble une déclaration et ses réserves, corrections ou précisions d'identité.
- context_refs contient seulement les blocs extérieurs indispensables pour comprendre le passage : titre parent, personne visée ou précision. Ils doivent appartenir au même document. Mets [] si le passage se suffit.

Titres :
- Donne un titre court et descriptif. Reprends un libellé explicite s'il décrit bien le passage ; sinon indique le sujet et, si utile, le type de source.
- Le titre seul doit rester fidèle. Garde les mots rapporté, non confirmé ou à vérifier quand l'incertitude change le sens. Une absence dans un registre incomplet n'établit pas une contradiction. Une erreur de rattachement n'établit pas qu'un document est faux.
- Exemple indépendant : « Un témoin pense avoir vu un véhicule rouge. La couleur n'a pas été vérifiée. » → « Signalement d'un véhicule rouge, couleur non vérifiée ».

Vérifie que les titres n'affirment rien de plus que les blocs référencés. Renvoie uniquement le JSON :
{"segments":[{"title":"...","content_refs":["X1"],"context_refs":[]}]}
```

Les blocs ont été envoyés séparément dans le message utilisateur.

## Fiche avec libellés et réserves

| Consigne | Titre proposé | Contenu | Contexte |
|---|---|---|---|
| Initiale | Identification et localisation préliminaire | B01, B02, B03 | — |
| Initiale | Contradiction avec le registre et suite à donner | B04, B05, B06 | B02 |
| Précise | Localisation rapportée de Nora Belin à la gare de Valbrune, identification non confirmée | B01, B02, B03 | — |
| Précise | Absence de mention de Nora Belin dans un registre incomplet du 12 mars | B04, B05, B06 | B01 |

Frontières inchangées. Le titre sur le registre décrit une absence de mention dans un registre incomplet, sans transformer ce constat en contradiction. Le titre de localisation garde le caractère rapporté et la réserve. Le contexte du second passage passe de B02 (localisation) à B01 (identité de Nora).

## Récit libre avec deux personnes

| Consigne | Titre proposé | Contenu | Contexte |
|---|---|---|---|
| Initiale | Évacuation d'Ana Derval et confusion concernant Elias | A1, A2, A3 | — |
| Précise | Évacuation d'Ana Derval vers Mont-Rive et signalement d'Elias près du lac, identification non confirmée | A1, A2, A3 | — |

Le passage reste commun à Ana et Elias. Le titre indique mieux le lieu de l’évacuation et le caractère incertain du signalement, mais la consigne ne produit pas ici de séparation par personne.

## Rectification et homonyme

| Consigne | Titre proposé | Contenu | Contexte |
|---|---|---|---|
| Initiale | Statut de Camille et attestation erronée | B1, B2, B3 | — |
| Initiale | Note logistique sur le déplacement de réunion | B4 | — |
| Précise | Interprétation de la date du 8 mai par Camille et attestation de décès à Port-Lys concernant un homonyme, décès non établi | B1, B2, B3 | — |

Le titre remplace « attestation erronée » par une référence à l’homonyme et au décès non établi. En revanche, « interprétation de la date du 8 mai par Camille » attribue à Camille une interprétation que le texte ne lui attribue pas. Le bloc B4, qui contient la note logistique, a disparu du découpage. La proposition doit être refusée en l’état.

Bloc omis : `B4` — Note logistique : réunion d’équipe déplacée à 16 h.

## Contrôles et décision

- Les 5 passages initiaux deviennent 4 passages. Aucun bloc inventé, dupliqué ou déplacé entre documents ; B4 est le seul bloc manquant.
- Les quatre liens ciblés entre une information et sa réserve sont présents dans le corps des passages.
- Le premier appel a pris 53,00 s ; le second, 102,73 s. Ces mesures ne comparent pas la vitesse des prompts.
- Les critères du prompt ont été ajustés après lecture des sorties initiales. Ces trois textes servent à vérifier les corrections ciblées ; ils ne constituent pas un jeu indépendant.

Garder la règle de fidélité des titres. Avant d’accepter le découpage, vérifier dans Python que chaque bloc apparaît exactement une fois dans le contenu. Si la couverture échoue, conserver les blocs non classés et signaler que le découpage est incomplet, ou reprendre un découpage de référence validé. Les titres générés restent des propositions.
