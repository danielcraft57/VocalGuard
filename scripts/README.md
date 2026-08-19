# Scripts VocalGuard

Scripts utilitaires pour la migration, le deploiement et les tests. Ne pas committer de donnees personnelles (hotes, numeros, chemins specifiques a une machine).

## Deploiement Raspberry Pi

- **deploy_to_rpi.ps1** (script unique) : pipeline de deploiement prod optimise (build frontend, sync code, `.env.prod` -> `.env`, venv, deps).
  Exemple : `.\scripts\deploy_to_rpi.ps1 -AppServerUser "pi" -AppServerName "app-node.lan" -RestartService`

Configurer l'hote via une variable d'environnement permet d'eviter de stocker des noms de machine ou utilisateurs dans le depot.

## Migration callattendant -> VocalGuard

- **migrate_callattendant_to_vocalguard.py** : migration des donnees (appels, appelants, blacklist/whitelist, voicemails). Option `--run-osint` pour enrichir les numeros et remplir `phone_number_profiles` (reputation, lieu, operateur). Voir `docs/APPELS_OSINT_UI.md`.
- Chemins par defaut : `callattendant.db` et `vocalguard.db` a la racine du projet. Surcharger avec `--source` et `--target` si besoin.

## Autres

- **generate_facturio_marketing_tts.py** : voix TTS pour la pub Facturio (JSON `data/marketing/facturio-publicite-2026.json`, edge-tts). Voir section ci-dessous.
- **init_french_phone_db.py** : initialisation des prefixes francais en base.
- **install_osint_tools.sh** / **install_osint_tools.ps1** : installation des outils OSINT (phoneinfoga, etc.).
- **setup_audio_rpi.sh**, **fix_asoundrc.py** : configuration audio sur RPi.
- **modem_live_call_cli.py** : appel sortant interactif modem USB (dial, ecoute, micro, DTMF) depuis un PC.
- **test_*.py** : scripts de test (audio, patterns, enregistrement, etc.). Ne pas inclure de numeros ou donnees reelles dans les tests commits.

## TTS publicite Facturio

Script principal (meme pipeline que `generate_wav_from_json_intents.py`, sortie MP3 video) :

```bash
pip install edge-tts pydub
# ffmpeg requis pour pydub

python scripts/generate_facturio_marketing_tts.py --list-voices
python scripts/generate_facturio_marketing_tts.py --variant 30s-main --concat-full
python scripts/generate_facturio_marketing_tts.py --variant all --concat-full --force
```

Entree : `data/marketing/facturio-publicite-2026.json` (segments alignes sur le storyboard Facturio).  
Sortie : `data/marketing/tts-output/facturio/<variant>/segment_*.mp3` et `full.mp3`.
