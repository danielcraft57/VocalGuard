# Modem Lab

Ce dossier regroupe des scripts de laboratoire pour tester le modem USB de maniere isolee.

## Architecture

- `labcore/` : bootstrap commun (config, logging, creation modem)
- `labscenarios/` : scenarios telephonie (entrant, sortant, dtmf, smoke tests)
- `labaudio/` : outillage TTS et generation de packs audio modem
- `modem_lab_ui.py` : interface CLI centralisee pour piloter le lab
- `.presets.json` : preferences locales de l'interface (port, voix, numero, etc.)
- `logs/` : logs dates par execution (console + fichier)

## Scripts

- `labscenarios/dialer.py` : numerotation simple (sortant) + raccrochage.
- `labscenarios/outgoing_call.py` : appel sortant interactif (clavier DTMF, hangup).
- `labscenarios/incoming_call.py` : attente d'appel entrant + decrochage manuel.
- `labscenarios/answering_machine.py` : repondeur (auto-answer, message d'accueil WAV, enregistrement du message).
- `labscenarios/dtmf_keypad.py` : envoi de touches DTMF sur appel en cours.
- `labscenarios/smoke_tests.py` : tests rapides des commandes AT de base.
- `cli.py` : lanceur unique avec sous-commandes (`smoke`, `dialer`, `incoming`, etc.).
- `tts_engine_copy.py` : copie locale du menu TTS (voix edge-tts + sample).
- `generate_modem_sounds.py` : generation d'un pack de prompts au format modem.
- `modem_lab_ui.py` : interface CLI interactive (menu unique).

## Documentation modem

- **Index thématique (notes extraites du PDF) :** [docs/README.md](docs/README.md)
- Manuel USR 5637 OEM (local) : `scripts/modem_lab/docs/5637-OEM.pdf`
- Source officielle : [USR 5637 OEM PDF](https://support.usr.com/support/5637-oem/5637-oem-files/5637-OEM.pdf)

## Usage rapide

Activer l'environnement puis executer un script:

```powershell
conda activate vocalguard
python scripts/modem_lab/labscenarios/smoke_tests.py --port COM6
python scripts/modem_lab/labscenarios/dialer.py --port COM6 --number 147
python scripts/modem_lab/labscenarios/outgoing_call.py --port COM6 --number 147
python scripts/modem_lab/tts_engine_copy.py
python scripts/modem_lab/generate_modem_sounds.py --voice fr-FR-DeniseNeural
python scripts/modem_lab/modem_lab_ui.py
python scripts/modem_lab/labscenarios/answering_machine.py --port COM6 --greeting-wav scripts/modem_lab/generated/default/modem_wav/welcome.wav --record-seconds 25
```

Alternative compacte via la CLI unifiée :

```powershell
python scripts/modem_lab/cli.py smoke -- --port COM6
python scripts/modem_lab/cli.py dialer -- --port COM6 --number 147
python scripts/modem_lab/cli.py outbound-announce -- --port COM6 --number 0780833873 --message-wav scripts/modem_lab/generated/default/modem_wav/welcome.wav
```

L'interface `modem_lab_ui.py` est organisee en sous-menus:
- **Scenarios telephonie** (entrant/sortant/dtmf/smoke)
- **Audio / TTS** (voix + packs audio)
- **Configuration** (port/voix/numero sauvegardes dans `.presets.json`)
- les choix audio et repondeur (devices, rx-only, PTT, greeting WAV, duree enregistrement) sont aussi memorises dans `.presets.json`
- quand une voix est choisie via le menu TTS, elle devient automatiquement la nouvelle voix par defaut

## Logging (niveaux + date)

Chaque script du `modem_lab` initialise Loguru avec:
- sortie console (niveau `INFO` par defaut)
- sortie fichier (niveau `DEBUG`) dans `scripts/modem_lab/logs`
- format date/heure milliseconde + niveau + module + message

Exemples de fichiers crees:
- `logs/dialer_20260502_213000.log`
- `logs/incoming_call_20260502_213015.log`
- `logs/modem_lab_ui_20260502_213100.log`

Le fichier contient des traces de plusieurs niveaux: `DEBUG`, `INFO`, `WARNING`, `ERROR`.
Rotation active a 10 MB et retention 30 jours.

## Creer de nouvelles voix

1. Lister et choisir une voix:

```powershell
python scripts/modem_lab/tts_engine_copy.py
```

2. Generer un pack audio avec une voix precise:

```powershell
python scripts/modem_lab/generate_modem_sounds.py --voice fr-FR-HenriNeural --pack-name henri_v1
```

3. Generer avec des prompts personnalises:

- Créer un fichier JSON, ex `scripts/modem_lab/custom_prompts.json`:

```json
{
  "welcome": "Bonjour, bienvenue chez DanielCraft.",
  "menu": "Tapez un pour le support, deux pour le commercial.",
  "bye": "Merci et au revoir."
}
```

- Lancer:

```powershell
python scripts/modem_lab/generate_modem_sounds.py --voice fr-FR-DeniseNeural --pack-name custom_v1 --prompts-file scripts/modem_lab/custom_prompts.json
```

Sorties:
- `generated/<pack-name>/modem_wav` (8 kHz, 8-bit, pour le modem)
- `generated/<pack-name>/listen_wav` (ecoute confortable)

## Appel sortant / entrant

- Sortant simple:
  - `python scripts/modem_lab/labscenarios/dialer.py --port COM6 --number 147`
- Sortant interactif DTMF:
  - `python scripts/modem_lab/labscenarios/outgoing_call.py --port COM6 --number 147`
- Entrant auto-answer (immediat):
  - `python scripts/modem_lab/labscenarios/incoming_call.py --port COM6 --auto-answer --answer-delay-ms 0 --rx-only`
- Entrant manuel:
  - `python scripts/modem_lab/labscenarios/incoming_call.py --port COM6 --manual-answer`
- Repondeur (accueil + enregistrement):
  - `python scripts/modem_lab/labscenarios/answering_machine.py --port COM6 --answer-delay-ms 0 --greeting-wav scripts/modem_lab/generated/default/modem_wav/welcome.wav --record-seconds 25 --beep`
  - options utiles: `--beep-ms 300 --beep-hz 1000`
  - mode double bip (pro): `--beep --beep-pattern double --beep-ms 220 --beep-hz 1200 --beep2-ms 150 --beep2-hz 780`

## Notes

- Ces scripts reutilisent `backend.core.modem_handler.ModemHandler`.
- Le mode voix et le support DTMF dependent du firmware modem et de la ligne.
- Pour un diagnostic detaille DTMF, utiliser aussi `scripts/modem_dtmf_diag.py`.
