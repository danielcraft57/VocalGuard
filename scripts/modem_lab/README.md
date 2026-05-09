# Modem Lab

Ce dossier regroupe des scripts de laboratoire pour tester le modem USB de maniere isolee.

## Architecture

- `labcore/` : bootstrap commun (config, logging, creation modem)
- `labscenarios/` : scénarios téléphonie — **index et rôles** : [labscenarios/README.md](labscenarios/README.md)
- `labaudio/` : outillage TTS et generation de packs audio modem
- `modem_lab_ui.py` : interface CLI centralisee pour piloter le lab
- `.presets.json` : preferences locales de l'interface (port, voix, numero, etc.)
- `logs/` : logs dates par execution (console + fichier)

## Scripts (aperçu)

- **`cli.py`** : point d’entrée unique — `python scripts/modem_lab/cli.py -h` pour la liste des sous-commandes.
- **`labscenarios/*.py`** : un fichier par scénario ; détail, tableau par usage et pièges courants → **[labscenarios/README.md](labscenarios/README.md)**.
- **`tts_engine_copy.py`**, **`generate_modem_sounds.py`** : voix / packs WAV modem.
- **`modem_lab_ui.py`** : menu interactif (réutilise les mêmes chemins que les scénarios).

## Documentation modem

- **Index thématique (notes extraites du PDF) :** [docs/README.md](docs/README.md)
- **Patterns dialogue prospection** (chaîne d’intents, policy, observer, deadline, ports) : [docs/prospection-dialogue-patterns/README.md](docs/prospection-dialogue-patterns/README.md)
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

Exemples via **`cli.py`** (recommandé) :

```powershell
python scripts/modem_lab/cli.py smoke -- --port COM6
python scripts/modem_lab/cli.py answer-metrics-probe -- --port COM6 --number 0780833873
python scripts/modem_lab/cli.py metrics-voicemail -- --port COM6 --number 0780833873 --prompt-wav scripts/modem_lab/generated/default/modem_wav/welcome.wav
python scripts/modem_lab/cli.py dialer -- --port COM6 --number 147
python scripts/modem_lab/cli.py outbound-announce -- --port COM6 --number 0780833873 --message-wav scripts/modem_lab/generated/default/modem_wav/welcome.wav
```

L'interface **`modem_lab_ui.py`** (Rich + Questionary) propose :
- **Scénarios téléphonie** (entrant / sortant / DTMF / smoke)
- **Audio / TTS** : menu voix edge-tts, génération pack modem, **assistant pack WAV d’intents** (JSON sous `data/intents/` → `greeting_01.wav`, etc.) et rappel CLI « intents vs prospection »
- **Configuration** (port, voix, numéro… dans `.presets.json`)

Prérequis TUI : `pip install rich questionary` (voir `requirements.txt`).

Pour générer les WAV **sans** l’UI : **`labaudio/generate_intent_pack.py`** — pas `prospection_outbound` (`--out` / `--var` sont réservés au script de génération).

Quand une voix est choisie via le menu TTS, elle devient la voix par défaut des presets.

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

## Appels sortant / entrant (exemples directs)

Les équivalents `python .../labscenarios/<script>.py` restent valides ; la matrice complète (éviter de confondre répondeur **entrant** vs **metrics_voicemail** sortant) est dans **[labscenarios/README.md](labscenarios/README.md)**.

- Répondeur **entrant** : `answering_machine.py` (greeting + bip + enregistrement).
- Sonde + répondeur **sortant** : `metrics_voicemail.py` via `cli.py metrics-voicemail`.

## Notes

- Ces scripts reutilisent `backend.core.modem_handler.ModemHandler`.
- Le mode voix et le support DTMF dependent du firmware modem et de la ligne.
- Pour un diagnostic detaille DTMF, utiliser aussi `scripts/modem_dtmf_diag.py`.
