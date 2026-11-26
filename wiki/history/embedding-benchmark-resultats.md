> Archive documentaire conservée le 25 novembre 2026. Décrit une étape passée ; utiliser le [guide actuel](../../README.md) pour exploiter BGE-M3. Les commandes et chemins en code se lisent depuis la racine du projet.

# Résultats du benchmark croisé — 23 novembre 2026

60 questions fictives, cinq résultats maximum, 24 configurations. Les résultats décrivent ce corpus, sans garantie de généralisation. Aucun changement n’a été appliqué à l’index de l’interface.

| Modèle | Préparation | Question | Premier complet | Couverture à cinq | Caractères retournés moyens |
| --- | --- | --- | ---: | ---: | ---: |
| minilm | actuel | original | 25/60 | 37/60 | 491 |
| minilm | actuel | qwen | 26/60 | 40/60 | 441 |
| minilm | contexte | original | 34/60 | 55/60 | 340 |
| minilm | contexte | qwen | 45/60 | 56/60 | 344 |
| minilm | coherent | original | 32/60 | 42/60 | 686 |
| minilm | coherent | qwen | 32/60 | 45/60 | 627 |
| minilm | contexte_coherent | original | 41/60 | 59/60 | 447 |
| minilm | contexte_coherent | qwen | 51/60 | 59/60 | 459 |
| bge-m3 | actuel | original | 27/60 | 43/60 | 354 |
| bge-m3 | actuel | qwen | 24/60 | 51/60 | 333 |
| bge-m3 | contexte | original | 49/60 | 57/60 | 324 |
| bge-m3 | contexte | qwen | 48/60 | 57/60 | 339 |
| bge-m3 | coherent | original | 35/60 | 48/60 | 625 |
| bge-m3 | coherent | qwen | 35/60 | 55/60 | 606 |
| bge-m3 | contexte_coherent | original | 56/60 | 60/60 | 592 |
| bge-m3 | contexte_coherent | qwen | 59/60 | 60/60 | 609 |
| qwen-0.6b | actuel | original | 27/60 | 41/60 | 494 |
| qwen-0.6b | actuel | qwen | 27/60 | 42/60 | 490 |
| qwen-0.6b | contexte | original | 47/60 | 56/60 | 428 |
| qwen-0.6b | contexte | qwen | 42/60 | 56/60 | 428 |
| qwen-0.6b | coherent | original | 33/60 | 46/60 | 704 |
| qwen-0.6b | coherent | qwen | 33/60 | 48/60 | 719 |
| qwen-0.6b | contexte_coherent | original | 53/60 | 60/60 | 618 |
| qwen-0.6b | contexte_coherent | qwen | 48/60 | 60/60 | 610 |

## Ressources observées

| Modèle | Chargement (s) | Requête médiane/P95 (ms) | Pic RAM processus (Mio) |
| --- | ---: | ---: | ---: |
| sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 | 6.5 | 14.2 / 35.5 | 1566 |
| BAAI/bge-m3 | 9.0 | 95.1 / 170.7 | 2488 |
| Qwen/Qwen3-Embedding-0.6B | 10.3 | 187.3 / 246.6 | 4366 |

Mesures CPU float32, quatre threads, batch de quatre. Le pic RAM concerne le processus de benchmark, pas tout le poste. Les encodages de requête sont mesurés à chaud ; ajouter le coût réseau/Qwen pour les requêtes reformulées. Le téléchargement des modèles est exclu.

## Détail avec contexte et passages cohérents

| Modèle, avec reformulation | Champs (32) | PDF (8) | Nouveaux cas (20) | Premier complet (60) |
| --- | ---: | ---: | ---: | ---: |
| minilm | 32/32 | 8/8 | 19/20 | 51/60 |
| bge-m3 | 32/32 | 8/8 | 20/20 | 59/60 |
| qwen-0.6b | 32/32 | 8/8 | 20/20 | 48/60 |

## Incertitude des différences

Bootstrap apparié exploratoire sur les 60 questions (5 000 tirages, graine 42), différence de couverture à cinq par rapport à MiniLM, avec contexte, passages cohérents et reformulation :
- bge-m3 : +1.7 points ; intervalle indicatif [+0.0 ; +5.0].
- qwen-0.6b : +1.7 points ; intervalle indicatif [+0.0 ; +5.0].

Les patrons de questions répétés et les faits du même document ne sont pas indépendants : cet intervalle n’est pas une garantie statistique sur un corpus réel. Les sorties longues sont avantagées par les métriques de couverture ; comparer aussi les volumes de texte et les exemples d’erreurs.

Les paramètres, révisions, instructions de requête et profils effectifs sont conservés dans les JSON de chaque modèle. Le corpus, les preuves, les segmentations et leurs sorties Qwen sont conservés séparément. Voir README.md pour le protocole et les limites.

## Conclusion opérationnelle

La meilleure configuration observée est BGE-M3, contexte explicite des champs, passages cohérents et reformulation V4 : 59/60 premiers résultats complets et 60/60 couvertures à cinq. Le seul premier résultat incomplet concerne le suivi médical de Marwa : le premier extrait porte sur son identité et sa consultation passée ; le rendez-vous attendu est au deuxième rang.

La correction de préparation avec MiniLM fait passer la couverture de 40/60 à 59/60, contre 51/60 en changeant seulement MiniLM pour BGE-M3 sur la préparation actuelle (avec reformulation dans les trois cas). La préparation est donc prioritaire sur ce corpus. BGE-M3 apporte ensuite un meilleur premier rang : 59/60 contre 51/60 pour MiniLM corrigé.

Qwen3-Embedding-0.6B obtient aussi 60/60 en couverture avec la préparation corrigée, mais 53/60 au premier rang sans reformulation, contre 48/60 avec reformulation. La reformulation ne doit pas être considérée comme universellement bénéfique.

BGE-M3 utilise environ 2,4 Gio au pic de ce processus, contre 1,5 Gio pour MiniLM et 4,3 Gio pour Qwen en calcul CPU float32. Ces mesures incluent le processus de benchmark et ne sont pas des besoins minimaux garantis. Son encodage de requête médian est d’environ 95 ms, contre 14 ms pour MiniLM et 187 ms pour Qwen, hors reformulation distante.

La fenêtre de contexte plus grande permet de conserver des passages complets, mais ce benchmark ne démontre pas à lui seul que l’augmentation de la fenêtre explique tout le gain : les modèles diffèrent aussi par leur entraînement et leur taille. Il ne teste pas les limites de 8 192 ou 32 768 tokens ; les documents restent courts. Les résultats doivent être confirmés avec davantage de documents hétérogènes avant toute conclusion de fiabilité générale.

Les vecteurs Qwen ont initialement échoué au contrôle de normalisation car le calcul utilisait les poids bfloat16 d’origine malgré une sortie float32. La série finale impose explicitement les poids et le calcul float32 aux trois modèles et conserve les contrôles de norme. Les fichiers JSON finaux correspondent exclusivement à cette série corrigée.

Aucune migration n’a été effectuée dans l’application. Les modèles ont été téléchargés sur ce poste ; aucun modèle supplémentaire n’a été installé sur la machine partagée de Stéphane.
