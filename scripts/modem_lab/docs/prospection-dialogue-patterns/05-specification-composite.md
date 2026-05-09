# Specification + Composite — poursuite du dialogue

## Intention des patrons

**Specification** : un objet (ou une fonction) qui répond à « **cet état** satisfait-il une **règle métier** ? ». Ici l’état est le couple **(memento, contexte du tour)**.

**Composite** : combiner plusieurs specifications avec une logique **ET** (`AllOfSpecifications`) : toutes doivent être vraies pour poursuivre.

Intérêts :

- règles **testables unitairement** ;
- évolution sans toucher à la structure de la boucle `for` dans le scénario ;
- nommage explicite (`NotStoppedSpecification`, …).

## Fichier `specification.py`

### `DialogueContext` (immuable)

| Champ | Rôle |
|-------|------|
| `next_turn_index` | Numéro du tour **1-based** que l’on **s’apprête** à exécuter. |
| `max_turns` | Plafond configuré (`config.max_reply_turns`). |
| `deadline` | `CallDeadline | None` : si présent, la règle « avant deadline » s’applique. |

### Protocole `DialogueSpecification`

Méthode unique : `is_satisfied_by(snapshot, ctx) -> bool`.

### Règles fournies

| Classe | Condition |
|--------|-----------|
| `NotStoppedSpecification` | `not snapshot.stop_dialogue` |
| `WithinMaxTurnsSpecification` | `ctx.next_turn_index <= ctx.max_turns` |
| `BeforeDeadlineSpecification` | pas de deadline **ou** `not deadline.expired()` |

### `AllOfSpecifications`

Contient un tuple `_parts` de specifications ; `is_satisfied_by` retourne `True` seulement si **chaque** partie retourne `True` (court-circuit au premier `False`).

### `default_continue_dialogue_spec()`

Raccourci : `AllOf(NotStopped, WithinMaxTurns, BeforeDeadline)` — politique par défaut du produit.

## Utilisation dans le scénario

Au **début** de chaque itération de tour, on construit un `DialogueContext` puis on appelle `policy.continue_dialogue.is_satisfied_by(snap, ctx)`. Si `False` : on émet un événement `DIALOGUE_STOPPED` avec la raison et on sort de la boucle **sans** lancer un nouveau `pump` inutile.
