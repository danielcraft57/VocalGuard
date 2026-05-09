# Patterns de conception — dialogue de prospection (`labcore/prospection_dialogue`)

Ce dossier documente les **patrons logiciels** utilisés pour le scénario sortant **prospection** (démarchage téléphonique + intents JSON + WAV), sans dupliquer le détail ligne à ligne du code : il renvoie vers les modules sous `scripts/modem_lab/labcore/prospection_dialogue/`.

## Public visé

- Développeurs qui étendent les **niveaux d’intent** (DanielCraft, autres JSON).
- Revue de code / onboarding sur **pourquoi** ces abstractions existent.

## Sommaire

| Document | Contenu |
|----------|---------|
| [01-vue-densemble.md](./01-vue-densemble.md) | Objectifs, flux d’un appel, liens entre patrons |
| [02-chaine-de-responsabilite-intents.md](./02-chaine-de-responsabilite-intents.md) | Fichiers JSON ordonnés + ordre des intents ; classe `IntentChain` |
| [03-memento-snapshot.md](./03-memento-snapshot.md) | `ConversationSnapshot` : ce qu’on mémorise et pourquoi |
| [04-strategy-policy.md](./04-strategy-policy.md) | `ProspectionDialoguePolicy`, `build_dialogue_policy`, troncature d’écoute |
| [05-specification-composite.md](./05-specification-composite.md) | `DialogueContext`, règles `AllOf`, poursuite de boucle |
| [06-observer-bus-evenements.md](./06-observer-bus-evenements.md) | `DialogueEventBus`, kinds, `loguru_dialogue_sink` |
| [07-deadline-budget-wall-clock.md](./07-deadline-budget-wall-clock.md) | `CallDeadline`, `--dialogue-max-wall-sec` |
| [08-ports-intent-matcher.md](./08-ports-intent-matcher.md) | `IntentMatcherProtocol`, inversion de dépendance |
| [09-integration-prospection-outbound.md](./09-integration-prospection-outbound.md) | Où le scénario branche policy, bus, matcher, Vosk |
| [10-pistes-evolution.md](./10-pistes-evolution.md) | Saga, circuit breaker, actor « ligne », etc. |

## Point d’entrée code

- Paquet Python : `labcore/prospection_dialogue/`
- Scénario : `labscenarios/prospection_outbound.py`
- Inventaire scénarios : `labscenarios/README.md`
