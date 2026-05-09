# Intégration — `prospection_outbound.py`

## Rôle du scénario

Le fichier `labscenarios/prospection_outbound.py` reste l’**orchestrateur** : modem, préparation voix, composition, attente décroché/voix (`run_answer_wait_phase`), lecture du **greeting**, ouverture/fermeture VRX, thread Vosk, lecture WAV, attente fin de ligne.

Le paquet `labcore/prospection_dialogue` fournit les **décisions** et la **structure** du dialogue après le greeting lorsque `--try-intent-reply` est actif et qu’au moins un `--intents-json` est fourni.

**Avant le greeting**, la phase `run_answer_wait_phase` / `wait_answer_or_voice_activity` peut tenir toute la fenêtre de capture si `--wait-full-capture-window` est actif : l’appelé n’entend alors pas encore l’audio sortant du modem (souvent seulement la sidetone PSTN). Pour la prospection, le défaut du scénario est **`--no-wait-full-capture-window`** afin de jouer l’ouverture peu après décroché ou première voix.

## Ordre des opérations (phase dialogue)

1. Construire `rng` (graine optionnelle).
2. Optionnel : `CallDeadline` si `--dialogue-max-wall-sec` > 0.
3. `build_dialogue_policy(...)` → `ProspectionDialoguePolicy` + bus + spec par défaut.
4. Instancier `IntentChain` comme **`IntentMatcherProtocol`** (`matcher`).
5. Émettre `DIALOGUE_STARTED` sur le bus.
6. Boucle `for turn in 1..max_reply_turns` :
   - Construire `DialogueContext` ;
   - si `continue_dialogue` faux → `DIALOGUE_STOPPED` + `break` ;
   - rouvrir VRX si `turn > 1` ;
   - `effective_listen_seconds(deadline)` puis `pump` ;
   - émissions `TURN_STT_*` ;
   - `matcher.match(...)` ;
   - émissions `INTENT_*` ;
   - lecture WAV + `snapshot.record_reply_played` ;
   - si terminal → `DIALOGUE_STOPPED` + `break`.
7. Fermer VRX, `close_input` Vosk, joindre les utterances, écrire SRT/VTT.
8. `wait_remote_line_end_optional` (comportement existant).

## Paramètres CLI liés au dossier « patterns »

| Option | Patron concerné |
|--------|-----------------|
| `--intents-json` (répétable) | Chaîne de responsabilité |
| `--dialogue-max-turns` | Specification + config |
| `--dialogue-max-wall-sec` | Deadline + Strategy (`effective_listen`) |
| `--dialogue-rng-seed` | Strategy / ouverture + variantes |
| `--terminal-intent-tags` | Chaîne + memento |
| `--opening-tag` | Service d’ouverture (`opening.py`) |

## `report_session_extra`

Le scénario enrichit le rapport de session avec `dialogue_max_wall_sec` et la liste des chemins JSON pour corréler métriques et logs bus.
