# Reranking Qwen — protocole du 24 novembre 2026

Corpus figé dans `corpus.json` : 24 questions annotées, quatre dossiers fictifs, 128 passages. Les sources intégrales lisibles sont dans `data/reranking_demo/`. Ces documents comprennent des homonymes, références familiales, dates administratives, rectifications, inventaires, témoignages contradictoires et nombreux extraits proches portant sur un autre événement.

Les identifiants présentés au modèle sont des UUID opaques : les premiers pilotes utilisaient des identifiants descriptifs, qui ont été corrigés avant la série finale. Les dossiers sont de nouvelles données, mais répètent plusieurs patrons de questions : la réserve ne constitue pas un échantillon indépendant représentatif de documents réels.

Les frontières de passages et annotations sont explicites pour isoler l’effet du reranking ; ce benchmark ne mesure pas la qualité de la segmentation de ces nouveaux documents. Ils ne sont pas automatiquement ajoutés au catalogue de l’application. Douze questions sont étiquetées calibration, douze réserve ; le prompt initial est figé avant les mesures, sans ajustement sur les résultats de réserve.

Pour chaque question, le même vecteur BGE-M3 issu de la préparation Qwen V4 sert à récupérer 30 candidats dans le dossier. Six cas CAL-A, couvrant tous les types de questions, comparent 20, 25 et 30 candidats. Le nombre retenu maximise successivement la couverture, la NDCG puis minimise le temps total sur ces seuls six cas. Il est ensuite figé pour les dix-huit autres questions, dont les douze cas de réserve. Les scores de calibration et de validation doivent être présentés séparément. Ce choix en deux étapes réduit le coût sur la machine partagée sans choisir le paramètre sur la validation. Le reranker reçoit la question originale, les textes entiers, les titres et les noms de sources, sans les scores cosinus.

Annotations de pertinence : 3 = réponse explicite, 2 = élément nécessaire d’une réponse composée, 1 = contexte utile, 0 = sans réponse utile ou mauvais événement/personne. Les questions sans réponse n’ont aucune annotation de niveau 2 ou 3. La NDCG compare l’ordre des cinq résultats à ces annotations graduées ; la couverture exige la présence de tous les passages nécessaires. Le premier résultat utile exige un niveau 2 ou 3. Les questions sans réponse sont évaluées séparément et ne gonflent pas la couverture.

Le prompt V1 et ses essais de calibration sont conservés dans `results-v1-calibration/`. Après observation de sa latence et de paraphrases perdant des réserves, la version V2 ne génère plus de résumé factuel ni de citations recopiées : elle classe des identifiants et leurs catégories. Le bilan affiché est formulé de manière déterministe à partir de ces catégories, avec des références vérifiées aux textes originaux. La version V2 est figée avant sa propre comparaison.

Les bilans doivent distinguer absence d’information dans les candidats et absence dans le dossier. Un récit contradictoire ne peut être arbitré en faveur d’un témoin sans preuve. La conformité JSON et les identifiants sont vérifiés automatiquement ; le bilan n’ajoute aucun fait documentaire. La justesse des catégories et justifications demande aussi une relecture des sources. Qwen n’est pas utilisé comme unique juge de ses propres résultats.

Quatre questions prédéfinies sont aussi traitées avec un ordre de candidats mélangé (graine 42), pour mesurer la sensibilité à leur position. Les réponses brutes sont conservées en cache par empreinte du prompt, de la requête complète et du schéma. Les temps reportés utilisent le temps réel des appels enregistrés, même lors d’un recalcul depuis le cache.

## Exécution

Avec les dépendances du projet, les poids BGE en cache et le tunnel Qwen actif :

```bash
.venv/bin/python experiments/reranking/prepare.py
.venv/bin/python experiments/reranking/run.py
.venv/bin/python experiments/reranking/baseline.py
.venv/bin/python experiments/reranking/summarize.py
```

`prepare.py` recrée le même corpus déterministe. `run.py` utilise une collection Qdrant en mémoire ; il ne modifie jamais l’index applicatif. Les sorties détaillées et réponses Qwen se trouvent dans `results/`, ignoré par Git. Les données fictives et le prompt sont versionnés pour permettre la reproduction.

Un contrôle additionnel `baseline.py` compare une sélection cosinus après suppression des doublons textuels exacts parmi les trente candidats. Il évite d’attribuer au seul LLM les gains pouvant venir du retrait de copies répétées.

Les trois tailles sont appelées successivement 20 → 25 → 30 sur la calibration. Les temps peuvent favoriser les derniers appels via le cache de préfixe du serveur : ils ne démontrent pas un avantage intrinsèque de vitesse d’une taille. La validation effectue ensuite un seul classement par nouvelle question ; ses temps sont rapportés séparément. Si la qualité est identique sur les six cas, ce petit échantillon ne permet pas de conclure à une taille universellement optimale.

Les résultats effectivement mesurés et leurs limites sont dans [RESULTATS.md](RESULTATS.md). Une correction structurelle après un UUID mal recopié ajoute une seule nouvelle tentative contrainte ; la politique finale est rejouée sur les réponses brutes conservées, avec de vrais appels pour les corrections nécessaires. Le rapport distingue ce changement de la version du prompt sémantique, restée figée.
