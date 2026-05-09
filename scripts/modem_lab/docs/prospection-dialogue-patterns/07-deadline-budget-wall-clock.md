# Deadline — budget temps wall-clock

## Intention du patron

**Deadline / budget temps** : garantir qu’une phase ne dépasse pas une durée **réelle** mesurée sur l’horloge monotonic (insensible aux ajustements NTP sur la durée courte d’un appel).

Ce n’est pas un « pattern GoF » au sens strict, mais un **objet policy** très répandu dans les systèmes temps réel et télécom.

## Implémentation : `deadline.py`

### Classe `CallDeadline`

| Méthode / attribut | Rôle |
|--------------------|------|
| `__init__(budget_sec)` | Lève si `budget_sec <= 0`. Mémorise `time.monotonic() + budget_sec`. |
| `expired()` | `True` si l’instant courant ≥ fin. |
| `remaining_sec()` | Secondes restantes (0 si dépassé). |

### Lien avec la Strategy

`ProspectionDialoguePolicy.effective_listen_seconds(deadline)` utilise `remaining_sec()` pour **tronquer** la durée du `pump` Vosk.

### Lien avec la Specification

`BeforeDeadlineSpecification` consulte le même objet `CallDeadline` passé dans `DialogueContext` : si le budget est épuisé **avant** le prochain tour, la spec échoue et la boucle s’arrête proprement.

## CLI

`--dialogue-max-wall-sec` dans `prospection_outbound.py` : si valeur > 0, instanciation d’un `CallDeadline` pour toute la phase dialogue après l’ouverture ; `None` ou `0` = pas de limite wall-clock (seulement `max_reply_turns` et le memento comptent).
