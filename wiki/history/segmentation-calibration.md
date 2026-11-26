> Archive documentaire conservée le 25 novembre 2026. Décrit une étape passée ; utiliser le [guide actuel](../../README.md) pour exploiter BGE-M3. Les commandes et chemins en code se lisent depuis la racine du projet.

# Calibration du découpage documentaire

Le service reçoit le texte UTF-8 d’un document et sa référence de catalogue. Il transmet le texte brut au client LLM et accepte des passages dont les champs `text` restituent la source caractère par caractère. Les positions `start` et `end` sont des indices Python, avec une fin exclue. La commande conserve les réponses et les diagnostics de chaque tentative dans un fichier JSONL.

## Corpus et mesures

Le corpus contient 10 textes fictifs de calibration et 6 textes réservés. Les annotations indiquent où un nouveau sujet doit commencer, où une coupure est acceptable et quels extraits doivent rester ensemble. Le score des frontières tolère que les blancs entre deux passages soient attachés à l’un ou à l’autre. Le contrôle technique de couverture reste strict, y compris sur ces blancs.

Le relevé indique les réussites au premier appel, les réussites après reprise, les replis, les erreurs et les temps. Les scores de Qwen portent uniquement sur les découpages validés. Pour une comparaison sur un même ensemble de documents, comparer le découpage fixe des cas où les variantes ont toutes réussi et présenter aussi le taux d’échec sur le corpus complet. Dans chaque sortie validée, relire les titres pour repérer toute attribution erronée, affirmation ajoutée ou réserve perdue. Ce contrôle des titres demande une lecture humaine.

## Commandes depuis la racine du projet

```bash
.venv/bin/python -B -m unittest discover -s tests -p 'test_segmentation*.py'

.venv/bin/python -B experiments/segmentation/run.py --baseline-only \
  --output experiments/segmentation/results/reference.jsonl
```

Pour utiliser Ollama sur wired, ouvrir le tunnel habituel depuis Linux et le laisser ouvert pendant l’essai.

```bash
ssh -N -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:11435:127.0.0.1:11434 wired-insa
```

Dans un second terminal, commencer par un seul cas. Par défaut, la commande utilise un modèle déjà chargé. Si la liste des modèles en mémoire est vide, ajouter `--allow-load` permet de démarrer un modèle déjà installé.

```bash
.venv/bin/python -B experiments/segmentation/run.py --case fiche \
  --output experiments/segmentation/results/fiche-v1.jsonl
```

Pour comparer les prompts, garder tous les autres réglages identiques. Les trois fichiers sont `v0-historique.txt`, `v1.txt` et `v2-exemples.txt`. L’option `--retry` teste séparément l’effet d’une seconde tentative avec le diagnostic. Un échec de transport ou une génération tronquée provoque un repli immédiat. Le délai HTTP s’applique aux opérations réseau bloquantes.

```bash
.venv/bin/python -B experiments/segmentation/run.py \
  --prompt prompts/segmentation/v2-exemples.txt \
  --output experiments/segmentation/results/calibration-v2.jsonl
```

Voir `--help` pour le modèle, le mode de raisonnement, le format et le budget de sortie. Après avoir choisi la variante, utiliser `--split reserve` sur les six textes réservés.
