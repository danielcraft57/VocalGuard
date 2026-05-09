# Observer — bus d’événements dialogue

## Intention du patron

**Observer** : les sujets (le scénario) **notifient** des observateurs sans les connaître ; on peut ajouter des logs, métriques, traces OpenTelemetry, dumps JSON, **sans modifier** la logique métier centrale.

## Implémentation : `events.py`

### `DialogueEvent`

- `kind` : chaîne stable (voir `DialogueEventKind`).
- `payload` : dictionnaire sérialisable (tour, tag, chemins, raisons d’arrêt, etc.).

### `DialogueEventKind`

Constantes de classe pour limiter les fautes de frappe : `DIALOGUE_STARTED`, `TURN_STT_START`, `TURN_STT_DONE`, `INTENT_MATCHED`, `INTENT_NO_MATCH`, `WAV_REPLY_START`, `DIALOGUE_STOPPED`, `DIALOGUE_ERROR`.

### `DialogueEventBus`

| Élément | Comportement |
|---------|----------------|
| `_handlers` | Liste de callbacks `(DialogueEvent) -> None`. |
| `subscribe(handler)` | Ajoute un observateur (ordre d’appel = ordre d’inscription). |
| `emit(kind, **payload)` | Construit un `DialogueEvent` et appelle chaque handler ; une **exception** dans un handler est **capturée** et loguée en `warning` pour ne pas casser les autres. |

**Remarque** : le bus est **synchrone** (même thread asyncio que le scénario). Les handlers doivent rester **courts** (pas d’I/O lourd bloquant).

### `loguru_dialogue_sink`

Observateur par défaut : une ligne `logger.info` par événement. Branché automatiquement par `build_dialogue_policy` lorsqu’un bus neuf est créé (sauf désactivation).

## Intérêt opérationnel

- Brancher un second `subscribe` pour pousser vers un fichier NDJSON, une queue, ou un test qui assert sur une liste en mémoire.
