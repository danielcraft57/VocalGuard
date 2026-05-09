# Strategy — `ProspectionDialoguePolicy`

## Intention du patron

**Strategy** : encapsuler une **famille d’algorithmes** ou de **paramètres** interchangeables sans modifier le client.

Dans notre cas, une **politique d’appel** (campagne DanielCraft, démo courte, CI) peut changer :

- nombre max de tours,
- durée d’écoute par tour,
- budget wall-clock,
- règles de poursuite (Specification),
- abonnés aux événements (Observer),

sans dupliquer la boucle modem / Vosk dans `prospection_outbound.py`.

## Implémentation : `policy.py`

### Classe `ProspectionDialoguePolicy` (immuable)

| Attribut | Rôle |
|----------|------|
| `config` | `ProspectionDialogueConfig` : chemins JSON, `pack_dir`, `max_reply_turns`, tags terminaux, graine RNG. |
| `listen_sec_per_turn` | Durée **souhaitée** d’écoute STT par tour (avant troncature deadline). |
| `wall_budget_sec` | Valeur « métier » du plafond temps (peut coexister avec un objet `CallDeadline` instancié côté scénario). |
| `continue_dialogue` | Objet satisfaisant `DialogueSpecification` (souvent `AllOfSpecifications` par défaut). |
| `event_bus` | `DialogueEventBus` pour les observateurs. |

### Méthode `effective_listen_seconds(deadline)`

Calcule la durée **réelle** passée à `pump_vrx_pcm16_to_vosk` :

- sans deadline : `max(1.0, listen_sec_per_turn)` ;
- avec deadline : `min(base, remaining)` avec un **plancher** (0,5 s ou 0,05 s si le budget est presque épuisé) pour éviter des valeurs absurdes ou bloquantes.

**Intérêt** : respecter `--dialogue-max-wall-sec` même si `--listen-sec` est grand.

### Fabrique `build_dialogue_policy`

- Construit la `ProspectionDialogueConfig` avec validations (`__post_init__`).
- Crée un `DialogueEventBus` neuf si besoin et, par défaut, y branche `loguru_dialogue_sink` **une seule fois** (éviter les doublons si vous injectez votre propre bus déjà configuré).
- Injecte `default_continue_dialogue_spec()` si aucune spec personnalisée.

### Paramètre `attach_default_log_sink`

Permet les tests ou pipelines silencieux : `attach_default_log_sink=False` pour ne pas souscrire le sink loguru par défaut.
