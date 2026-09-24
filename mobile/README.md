# VocalGuard Mobile

Application Expo / React Native connectee a l'API publique VocalGuard.

## Demarrage rapide

```powershell
cd mobile
npm install
npm run web
```

Appairage : page web **App mobile** (code 8 caracteres), ou coller un token API dans la saisie manuelle.

## Android (telephone / emulateur)

Definir le SDK avant `npm run android` (sinon Expo ne voit ni device ni AVD) :

```powershell
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$env:PATH = "$env:ANDROID_HOME\platform-tools;$env:ANDROID_HOME\emulator;$env:PATH"
adb devices
npm run android
```

- Telephone USB : activer le debogage USB.
- Wireless : `adb connect <ip>:5555` puis verifier `adb devices`.
- Emulateurs locaux connus : `Medium_Phone_API_36.1`, `Small_Phone`
  (`emulator -list-avds`).

## Scripts

| Script | Role |
|--------|------|
| `npm run web` | Dev navigateur |
| `npm start` | Metro |
| `npm run android` | Android debug |
| `npm test` | Jest |
| `npm run typecheck` | TypeScript |

## Fonctionnalites

### Appels

- Liste : icones entrant / sortant, numeros FR, OSINT
- Detail : cadre Sous-titres (karaoke + bande sonore waveform), texte complet, OSINT chips
- Sync offline SQLite (`/public/sync/delta`) avec transcription + cues

### Messages

- Bande sonore interactive sur chaque ligne (play, ±2 s en calque, waveform cliquable)
- Une seule piste a la fois (coupe l'autre message et l'audio d'un appel)

Voir aussi `docs/IDEES.md`, `docs/APPELS_OSINT_UI.md`.
