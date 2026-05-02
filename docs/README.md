# Index documentation

## Guides à jour (référence)

| Document | Contenu |
|----------|---------|
| [INSTALLATION.md](INSTALLATION.md) | Prérequis, paquets système, Python |
| [TELEPHONY_STACK.md](TELEPHONY_STACK.md) | API vs daemon modem, variables `.env`, dev PC + Pi, tests |
| [DEPLOYMENT_PROD.md](DEPLOYMENT_PROD.md) | systemd, déploiement Pi |
| [OSINT.md](OSINT.md) / [APPELS_OSINT_UI.md](APPELS_OSINT_UI.md) | Enrichissement numéros, UI liste appels |
| [AGENDA_API.md](AGENDA_API.md) | Endpoints agenda |
| [AUDIO_SETUP_RPI.md](AUDIO_SETUP_RPI.md) / [TROUBLESHOOTING_AUDIO.md](TROUBLESHOOTING_AUDIO.md) | Audio modem / ALSA |
| [CI_CD.md](CI_CD.md) | CI, déploiement |

## Architecture (plusieurs versions — la plus récente en premier)

- [ARCHITECTURE_V3.md](ARCHITECTURE_V3.md) — backend `backend/` + frontend Next.js (référence structure dépôt)
- [ARCHITECTURE_V2.md](ARCHITECTURE_V2.md) — historique
- [ARCHITECTURE.md](ARCHITECTURE.md) — schéma ancien package `vocalguard/` (obsolète, conservé pour archive)

## Spécifications / périmètres

| Document | Note |
|----------|------|
| [MODEM_APPELS_MVP_SCOPE.md](MODEM_APPELS_MVP_SCOPE.md) | Périmètre appels sortants ; détails runtime dans **TELEPHONY_STACK** |
| [PALETTE_UX.md](PALETTE_UX.md) | Couleurs / UI |
| [IDEES.md](IDEES.md) | Pistes / brouillon |

## Divers

- [IMPROVEMENTS_SUMMARY.md](IMPROVEMENTS_SUMMARY.md) — synthèse évolutions
- [IMPROVEMENTS.md](IMPROVEMENTS.md) — détail vs callattendant
- [REPUTATION_SERVICES.md](REPUTATION_SERVICES.md), [WHITELIST_BLACKLIST_SCREENED.md](WHITELIST_BLACKLIST_SCREENED.md), [API_SIRENE.md](API_SIRENE.md)
