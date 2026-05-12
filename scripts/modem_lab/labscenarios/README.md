# Scénarios `labscenarios/`

Scripts modem USB (USR / Conexant). **Préférer** la CLI :

`python scripts/modem_lab/cli.py <sous-commande> -- --port COM6 ...`

**Signets (raccourcis perso)** : même `cli.py`, mais la première position peut être un **identifiant** défini dans `scripts/modem_lab/scenario_bookmarks.json` (scénario intégré + arguments figés). Gestion : `python scripts/modem_lab/cli.py bookmark -h` ou menu **Signets scénarios** dans `modem_lab_ui.py`. Modèle versionné : `scenario_bookmarks.example.json`.

**Inventaire** : chaque fichier `*.py` ici (hors `__init__.py`) correspond à une sous-commande de `cli.py` — pas de scénario « mort » conservé dans ce dossier. Les sections ci-dessous classent par **usage**, pas par ancienneté.

---

## Prioritaires (VRX / métriques / Vosk)

| CLI | Fichier | Rôle |
|-----|---------|------|
| `answer-metrics-probe` | `answer_metrics_probe.py` | Sonde seule : CSV, `capture.wav`, `report.json` / timing. |
| `answer-vosk-live-probe` | `answer_vosk_live_probe.py` | Compose puis écoute **STT Vosk** en temps réel (thread) : affiche `PARTIAL`/`FINAL` en console et écrit `transcript.srt` en continu. |
| `metrics-voicemail` | `metrics_voicemail.py` | Même sonde puis prompt WAV, bips, message, option `wait_remote_hangup`. Défauts delay/fenêtre capture ; plafond d’attente voix = delay+fenêtre sauf `--extend-wait-beyond-capture`. |
| `prospection-outbound` | `prospection_outbound.py` | Démarchage : sonde, **ouverture** (WAV explicite, `greeting_01.wav`, ou `--opening-tag` + tirage), **STT Vosk** → sous-titres. Défaut **`--no-wait-full-capture-window`** : greeting peu après décroché/voix (évite long silence « que mon écho ») ; `--wait-full-capture-window` pour sonde complète type métriques. Dialogue : `--try-intent-reply` + `--intents-json` (répétable, ordre = priorité), `--dialogue-max-turns`, `--dialogue-max-wall-sec` (budget temps réel + écoutes tronquées), `--terminal-intent-tags`. **Policy / Specification / Observer / Deadline / Ports** : `labcore/prospection_dialogue/`. Pack : `labaudio/generate_intent_pack.py`. |

Partagent `labcore.answer_wait_common` + `labcore.call_watch`.

---

## Sortant « simple »

| CLI | Fichier | Rôle |
|-----|---------|------|
| `dialer` | `dialer.py` | Compose, `--hold-seconds`, raccroche. |
| `outgoing` | `outgoing_call.py` | Compose puis DTMF interactif (clavier). |
| `outbound-announce` | `outbound_announce.py` | Compose, attentes sonnerie, lecture WAV. |
| `outbound-listen-vad` | `outbound_listen_vad.py` | VRX + VAD sans WAV (logs parole). |
| `outbound-pc-headset` | `outbound_pc_headset.py` | Compose, joue un premier WAV d'ouverture ("oui allo"), puis pont micro-casque PC <-> ligne. |
| `pc-headset-direct` | `pc_headset_direct.py` | Sans modem/appel: ouverture bip/WAV, conversation locale micro <-> casque, STT Vosk live + `transcript.srt`. |

---

## Entrant / utilitaires

| CLI | Fichier | Rôle |
|-----|---------|------|
| `incoming` | `incoming_call.py` | RING, décrochage, pont audio. |
| `answering` | `answering_machine.py` | Répondeur entrant (greeting + bip + record). |
| `dtmf` | `dtmf_keypad.py` | DTMF sur ligne établie. |
| `smoke` | `smoke_tests.py` | Fumée AT rapide. |

---

## Avancé

| CLI | Fichier | Rôle |
|-----|---------|------|
| `prompt-and-play` | `prompt_and_play.py` | Séquences audio/touches ; option capture « sonde ». |

**Ne pas confondre** : `answering_machine` = **entrant** ; `metrics_voicemail` = **sortant** sonde + répondeur.
