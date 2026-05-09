# Chaîne de responsabilité — intentions (JSON + WAV)

## Intention du patron

**Chaîne de responsabilité** : une requête (ici : la **transcription** textuelle) traverse une **série de maillons** ; le **premier** maillon capable de traiter la requête s’arrête la chaîne pour ce tour.

Avantages :

- **Priorité explicite** : par exemple un fichier « stop / RGPD » passé **avant** le fichier « niveau 1 ouverture » en argument CLI.
- **Pas de if géant** centralisant tous les cas ; chaque fichier JSON reste une unité métier.

## Implémentation dans VocalGuard

### Deux niveaux d’ordre

1. **Ordre des fichiers** : argument `--intents-json` répétable (ou `nargs="*"` côté argparse) — le **premier** fichier listé est consulté en premier.
2. **Ordre dans un fichier** : la clé JSON `"intents"` est un **tableau** ; on parcourt les objets **dans l’ordre** du tableau.

### Classe `IntentChain` (`chain.py`)

- **Entrée** : `transcript` (texte), `pack_dir` (dossier WAV), `rng` (tirage de variante).
- **Traitement** : pour chaque `(fichier, payload)`, pour chaque `item` dans `intents`, pour chaque `pattern`, si le pattern est une **sous-chaîne** de la transcription (comparaison en minuscules), on cherche des WAV sur disque pour ce `tag`.
- **Sortie** : un `IntentMatchResult` (chemin WAV, tag, index de variante, pattern retenu, fichier source, booléen `terminal`) ou `None`.

### Variantes WAV au hasard

Parmi les fichiers existants `tag_01.wav`, `tag_02.wav`, … un indice est tiré avec `rng.choice` : **stratégie A/B** pour varier les réponses sans changer le JSON entre deux appels.

### Variables et types utiles

| Symbole | Rôle |
|---------|------|
| `IntentChain._payloads` | Liste `(Path, dict)` chargée à l’`__init__` |
| `IntentMatchResult` | Données immuables du match gagnant |
| `terminal_tags` | `frozenset` de tags qui marquent une fin de dialogue après lecture |

### Lien avec les ports

`IntentChain` satisfait le contrat `IntentMatcherProtocol` (`ports.py`) : le scénario peut dépendre du **protocole** plutôt que de la classe concrète.
