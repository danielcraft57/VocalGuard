# Plan 03 — UX/UI Material Design (toutes pages concernees)

Principe : **aucune config backend sans ecran Material**. Une seule charte MUI sur tout le perimetre telephonie.

---

## Etat actuel

| Zone | Etat | Cible |
|------|------|-------|
| `entreprises`, `agenda`, `api` | MUI 9 | Reference visuelle |
| `Topbar`, `IncomingCallModal`, `filtering`, `settings` | CSS custom `vg-*` | Migration MUI |
| Theme | `ThemeContext` dark/light (CSS) | MUI `createTheme` synchronise |

Stack : `@mui/material` ^9, `@mui/icons-material`, `@emotion/react`.

---

## Phase UI-0 — Design system Material

### Theme unifie

Fichier : `frontend/src/theme/vocalguardTheme.ts`

- `createTheme()` modes dark + light
- Couleurs : primary `#22c55e`, error (bloque), warning (screened), success (permitted)
- Sync `useTheme()` existant → `palette.mode` + classes `vg-theme-dark`
- `MuiThemeProvider` dans `ThemeProviderWrapper`

### Composants reutilisables (`frontend/src/components/mui/`)

| Composant | Role |
|-----------|------|
| `VgPageHeader` | Titre + sous-titre + actions |
| `VgSettingsSection` | Card MUI avec icone + description |
| `VgFormRow` | Label + helper + controle |
| `VgSaveBar` | Snackbar + bouton Enregistrer sticky |
| `VgProfileChip` | permitted / screened / blocked |
| `VgRingsSlider` | 0–8 sonneries + texte explicatif |
| `VgActionsBuilder` | Chips reordonnables (answer, greeting, record…) |
| `VgAudioSourcePicker` | TTS / WAV + preview play |
| `VgPresetSelector` | Cards Repondeur vs Telephone |
| `VgEffectiveConfigBanner` | « Valeur effective : heritee du preset » |

Icones : `@mui/icons-material` (remplace `material-icons` CSS sur pages migrees).

---

## Navigation

```
Parametres (/settings)                    Hub Material
├── Ligne entrante                        /settings/incoming-line
├── Profils et sonneries                  /settings/incoming-profiles
├── Messages et audio                     /settings/incoming-audio
├── Messagerie et DTMF                    /settings/voicemail
├── Patterns numeros                      /settings/number-patterns
└── Avance                                /settings/incoming-advanced

Filtrage (/filtering)                     Refonte MUI
Appels (/calls)                           Badges profil
Topbar                                    ToggleButtonGroup MUI
Modale entrant                            Dialog MUI full-screen mobile
```

Sidebar : entree Parametres avec hub a tuiles ou sous-menu.

---

## Pages detaillees

### 1. Hub Parametres — `/settings`

Grille de `Card` cliquables :

| Tuile | Icone MUI | Route |
|-------|-----------|-------|
| Ligne entrante | `PhoneInTalk` | `/settings/incoming-line` |
| Profils appelants | `FilterList` | `/settings/incoming-profiles` |
| Messages vocaux | `RecordVoiceOver` | `/settings/incoming-audio` |
| Messagerie | `Voicemail` | `/settings/voicemail` |
| Patterns | `Pattern` | `/settings/number-patterns` |
| Avance | `Tune` | `/settings/incoming-advanced` |

Bandeau synthese : preset actif, modem OK, dernier profil applique.

---

### 2. Ligne entrante — `/settings/incoming-line`

- `ToggleButtonGroup` Repondeur / Telephone (meme API que topbar)
- `Alert` explicatif fixe sonne vs coupe sonnerie
- `Switch` `whitelist_ring_only`
- `Slider` + `TextField` `phone_mode_rings`
- `Chip` apercu decision

---

### 3. Profils et sonneries — `/settings/incoming-profiles`

Onglets MUI `Tabs` : Autorises | Inconnus | Bloques

Par onglet :

- `VgRingsSlider`
- `VgActionsBuilder`
- `FormControlLabel` seize_on_ring, require_cid_before_action
- `Accordion` heritage preset vs override
- `VgEffectiveConfigBanner`

Couleurs : permitted = success, screened = warning, blocked = error.

---

### 4. Messages et audio — `/settings/incoming-audio`

| Section | Controles |
|---------|-----------|
| Accueil | Radio TTS/WAV, texte, upload, preview |
| Message bloque | idem |
| Bip enregistrement | WAV / DTMF / aucun |
| TTS | Slider rate Edge TTS |

Option : bouton « Tester sur le modem » (API test, phase ulterieure).

---

### 5. Messagerie et DTMF — `/settings/voicemail`

- `Switch` require_dtmf
- `TextField` chiffre DTMF
- `TextField` multiline prompt
- `Slider` timeout, duree max, fin silence
- Stepper horizontal : Accueil → DTMF → Bip → Enregistrement → Fin

---

### 6. Patterns numeros — `/settings/number-patterns`

- `Table` ou `DataGrid` : pattern, action, raison, actif
- `Dialog` ajout / edition
- `Autocomplete` action (blocked / screened / permitted)
- Lien vers `/filtering`

Decision phase 0 : fusionner avec `/filtering` en onglets ou pages separees.

---

### 7. Avance — `/settings/incoming-advanced`

- cid_wait_sec, ring_cycle_sec, ring_quiet_abort_sec
- Switches abort parallele, retry greeting
- `Accordion` JSON config effective (lecture seule, copier)
- `Alert` severity warning : reglages experts

---

### 8. Filtrage — `/filtering` (refonte MUI)

Migration complete depuis CSS custom :

| Onglet | Contenu |
|--------|---------|
| Liste blanche | Table + FAB, chips permitted |
| Liste noire | Table + FAB, chips blocked |
| Regles | Patterns (lien settings si unifie) |

Ajouts :

- Colonne « Comportement » selon profil
- Action rapide « Forcer sonnerie fixe »

---

### 9. Appels — `/calls`

- `Chip` couleur par profil
- Tooltip « Decision » (`source: preset:voicemail`)
- Filtre `Select` par profil
- Lien « Modifier le filtrage » sur appel bloque

---

### 10. Topbar — refactor MUI

Remplacer `vg-line-mode` :

- `ToggleButtonGroup` size small
- `Chip` modem success / error
- `Tooltip` firmware, CID
- Responsive : icones seules < 600px (`useMediaQuery`)

API inchangee : `setIncomingLineMode`.

---

### 11. Modale appel entrant — `IncomingCallModal`

`Dialog` MUI fullScreen (mobile) / maxWidth sm (desktop) :

- `Avatar` + numero
- `LinearProgress` ringing
- `Chip` phase + profil
- `Button` Masquer
- Animations `Fade` / pulse via `sx`

---

### 12. Dashboard — indicateurs legers

- Carte appels bloques aujourd'hui
- Chip mode ligne actif

---

## Services front

Extension `frontend/src/services/settingsApi.ts` :

```ts
fetchIncomingCallConfig()
patchIncomingCallConfig(partial)
fetchIncomingPresets()
patchIncomingPreset(name, partial)
fetchNumberPatterns()
patchNumberPatterns(...)
```

Hook `useIncomingCallConfig()` :

- charge config
- merge local
- `save()` → PUT + snackbar
- `resetToPreset()` / `resetField(path)`

Pattern identique a `useAgendaCalendar`.

---

## Principes UX Material

1. **Un reglage = un controle visible**
2. **Valeur effective toujours affichee** (preset vs override)
3. **Feedback immediat** : Snackbar, skeleton, `Alert` erreurs
4. **Mobile first** : drawer, full width
5. **Accessibilite** : aria-labels, focus trap modale, contrastes WCAG dark
6. **Coherence** : meme `VgSaveBar` partout

---

## Checklist QA UI

- [ ] Dark + light theme
- [ ] Mobile + desktop (topbar, settings, modale)
- [ ] Sauvegarde partielle (patch) sans ecraser autres champs
- [ ] Etats loading / erreur / vide sur chaque page
- [ ] Navigation retour hub settings depuis chaque sous-page
