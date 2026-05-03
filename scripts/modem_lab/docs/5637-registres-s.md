# Registres S — téléphonie et voix (extraits)

Source : *S-Register Summary* et définitions dans `5637-OEM.pdf`. Les valeurs par défaut peuvent **varier selon le pays** (homologation) ; le manuel le signale pour plusieurs registres.

## Les plus utilisés pour l’appel

| Registre | Description | Unité / plage | Défaut (extrait NA) |
|----------|-------------|---------------|---------------------|
| **S0** | Nombre de sonneries avant **réponse auto** | sonneries 0–255 | 0 (désactivé) |
| **S1** | Compteur de sonneries (lecture seule) | 0–255 | 0 |
| **S6** | Attente avant composition | s (min. 2 s) | 2 |
| **S7** | Time-out fin de connexion / attente porteuse | s | 50 |
| **S8** | Pause pour `,` dans la chaîne de numérotation | s | 2 |
| **S9** | DTMF « off » entre impulsions | ms | 95 |
| **S10** | Délai avant raccrochage après perte de porteuse | 0,1 s | 20 |
| **S11** | Durée / vitesse composition DTMF | ms | 95 |
| **S12** | Garde autour du caractère d’échappement | 20 ms | 50 |

## Voix / sonnerie synthétique

| Registre | Description | Défaut (manuel) |
|----------|-------------|-----------------|
| **S32** | Volume de sonnerie synthétique | 10 dB |
| **S33** | Fréquence de sonnerie synthétique | 0 |

## Silence (lié à `+VSD` / qualité ligne)

| Registre | Description | Défaut |
|----------|-------------|--------|
| **S71** | Sensibilité silence | 128 |
| **S72** | Timer détection silence | 50 ms |

## Autres (aperçu)

- **S30** : timer d’inactivité (minutes).
- **S82** : rapport de sonnerie distinctive (ms).
- **S127** : impédance / activation caller-ID.

Pour la liste complète et le bit-mapping (S14, S21, S22, …), se reporter au PDF (*S-Register Definitions*).
