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

Definir le SDK **avant** `npm run android` (sinon Gradle : `SDK location not found`) :

```powershell
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$env:PATH = "$env:ANDROID_HOME\platform-tools;$env:ANDROID_HOME\emulator;$env:PATH"
adb devices
```

Apres un `npx expo prebuild --clean`, recreer `android/local.properties` si besoin :

```powershell
$sdk = "$env:LOCALAPPDATA\Android\Sdk".Replace('\', '\\')
Set-Content -Path "android\local.properties" -Value "sdk.dir=$sdk" -Encoding ASCII
```

Puis builder / installer :

```powershell
npm run android
```

Si Gradle echoue en essayant de supprimer des `.so` (`Unable to delete directory` sous `react-native-screens` / `expo-modules-core`) :

```powershell
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue "node_modules\react-native-screens\android\build"
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue "node_modules\expo-modules-core\android\build\intermediates\cxx"
$env:ORG_GRADLE_PROJECT_reactNativeArchitectures = "arm64-v8a"
npx expo run:android --variant debug
```

(`arm64-v8a` suffit pour un telephone recent type Samsung ; evite le lock `armeabi-v7a`.)

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

- Liste : icones entrant / sortant, pastilles marques OSINT (telecom + interim) dessous, numeros FR
- Detail : cadre Sous-titres (karaoke + bande sonore waveform), texte complet, OSINT chips
- Sync offline SQLite (`/public/sync/delta`) avec transcription + cues

### Messages

- Bande sonore interactive sur chaque ligne (play, ±2 s en calque, waveform cliquable)
- Une seule piste a la fois (coupe l'autre message et l'audio d'un appel)

Voir aussi `docs/IDEES.md`, `docs/APPELS_OSINT_UI.md`.
