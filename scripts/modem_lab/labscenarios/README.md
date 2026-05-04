# Scénarios `labscenarios/`

Scripts modem USB (USR / Conexant). **Préférer** la CLI :

`python scripts/modem_lab/cli.py <sous-commande> -- --port COM6 ...`

---

## Prioritaires (VRX / métriques)

| CLI | Fichier | Rôle |
|-----|---------|------|
| `answer-metrics-probe` | `answer_metrics_probe.py` | Sonde seule : CSV, `capture.wav`, `report.json` / timing. |
| `answer-vosk-live-probe` | `answer_vosk_live_probe.py` | Compose puis écoute **STT Vosk** en temps réel (thread) : affiche `PARTIAL`/`FINAL` en console et écrit `transcript.srt` en continu. |
| `metrics-voicemail` | `metrics_voicemail.py` | Même sonde puis prompt WAV, bips, message, option `wait_remote_hangup`. Défauts delay/fenêtre capture ; plafond d’attente voix = delay+fenêtre sauf `--extend-wait-beyond-capture`. |
| `prospection-outbound` | `prospection_outbound.py` | Démarchage : sonde comme ci-dessus, lecture **greeting** (WAV ou `greeting_01.wav` d’un pack), **STT Vosk** (thread) → `transcript.srt` / `transcript.vtt`, option `--try-intent-reply` + `intents_*.json` + pack audio. Modèles FR : `--vosk-list-models`, téléchargement via `--vosk-model-slug` / profil `generated/vosk_lab_profile.json`, config seule : `--vosk-configure-only`. Génération pack : `labaudio/generate_intent_pack.py`. |

Partagent `labcore.answer_wait_common` + `labcore.call_watch`.

---

## Sortant « simple »

| CLI | Fichier | Rôle |
|-----|---------|------|
| `dialer` | `dialer.py` | Compose, `--hold-seconds`, raccroche. |
| `outgoing` | `outgoing_call.py` | Compose puis DTMF interactif (clavier). |
| `outbound-announce` | `outbound_announce.py` | Compose, attentes sonnerie, lecture WAV. |
| `outbound-listen-vad` | `outbound_listen_vad.py` | VRX + VAD sans WAV (logs parole). |

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
