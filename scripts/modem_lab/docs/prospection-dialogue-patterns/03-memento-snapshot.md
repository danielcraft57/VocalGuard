# Memento — `ConversationSnapshot`

## Intention du patron

**Memento** : capturer l’**état interne** d’un objet (ou d’un processus) sous une forme **externe** pour :

- le **journaliser** (rapport de session, audit),
- envisager plus tard une **reprise** (rejeu, debug),
- ou simplement **séparer** l’état mutable des paramètres immuables (`ProspectionDialogueConfig`).

Ici le « caretaker » (gardien) est le scénario `prospection_outbound` ; le memento est volontairement **minimal** (pas d’historique complet des PCM).

## Implémentation : `ConversationSnapshot` (`snapshot.py`)

### Champs

| Champ | Signification |
|-------|----------------|
| `reply_turns_completed` | Nombre de réponses intent **effectivement jouées** après une écoute. |
| `played_intent_tags` | Liste ordonnée des `tag` dont un WAV a été joué (traçabilité). |
| `last_turn_transcript` | Texte STT du **dernier** segment (diagnostic rapide). |
| `stop_dialogue` | `True` après un intent **terminal** (ex. au revoir, RGPD). |

### Méthode `record_reply_played`

Incrémente le compteur de tours, append le tag, et si `terminal` est vrai, positionne `stop_dialogue` pour que la **Specification** « non arrêté » fasse échouer la poursuite au tour suivant.

### Sérialisation

`to_jsonable()` renvoie un `dict` prêt pour JSON (logs `loguru` en fin de phase dialogue dans le scénario).

## Différence avec `ProspectionDialogueConfig`

- **Config** : fixée au début ; **immutable** (`frozen=True`).
- **Snapshot** : **évolue** pendant l’appel ; mutable mais petit et explicite.
