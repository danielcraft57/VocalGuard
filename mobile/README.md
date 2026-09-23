# VocalGuard Mobile

Application Expo / React Native connectee a l'API publique VocalGuard.

## Demarrage rapide

```powershell
cd mobile
npm install
npm run web
```

Appairage : page web **App mobile** (code 8 caracteres), ou coller un token API dans la saisie manuelle.

## Scripts

| Script | Role |
|--------|------|
| `npm run web` | Dev navigateur |
| `npm start` | Metro |
| `npm run android` | Android debug |
| `npm test` | Jest |
| `npm run typecheck` | TypeScript |

## Fonctionnalites appels

- Liste avec icones entrant / sortant, numeros FR, OSINT
- Clic carte : modal avec audio + karaoke
- Sync offline SQLite (`/public/sync/delta`)

Voir aussi `docs/IDEES.md`, `docs/APPELS_OSINT_UI.md`.
