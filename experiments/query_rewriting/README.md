# Banc de reformulation — périmètre historique

L'application BGE-M3 utilise le prompt multilingue V5 ; sa configuration et son repli sur la question originale sont décrits dans le [guide actuel](../../README-web.md#prompts-actifs).

Le script `evaluate.py` conserve une reconstruction propre au socle de première génération, indépendante de l'encodeur du manifeste web. Il dépend aussi de l'API et d'un artefact PDF local. **Ne pas l'utiliser pour annoncer une mesure du pipeline BGE-M3 actuel.**

Le [rapport du 23 novembre 2026](../../wiki/history/query-rewriting-2026-11-23.md) conserve les configurations V1/V4, les résultats, les limites et les commandes d'origine. Sans option `--prompt`, le script importe désormais le prompt courant ; une relance ne reproduit donc pas automatiquement ces mesures. Aucun nouveau résultat BGE-M3 n'est déduit de cette archive.
