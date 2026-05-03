# USR 5631 — interface DTE ↔ modem

Source : [dtemodem.htm](https://support.usr.com/support/5631/5631-ug/dtemodem.htm)

Ce chapitre couvre l’**écho**, les **codes résultats**, le **format CONNECT**, le **flux local** (matériel / logiciel), la **compression** (côté lien avec correction d’erreur), le **mode « reliable »**, et les extensions **+IPR**, **+IFC**, **+ILRR**.

## Résultats et verbosité

### `E` — echo des commandes

- `0` — echo off ; `1` — echo on (défaut).  
- Bit correspondant : **S14** bit 1.

### `Q` — suppression des codes résultat

- `0` — codes envoyés (défaut) ; `1` — silencieux.  
- **S14** bit 2.

### `V` — forme courte / longue des résultats

- `0` — forme courte ; `1` — verbose (défaut).  
- **S14** bit 3.

### `W` — contenu du message CONNECT

Interagit avec **S95** et les rapports **+MR**, **+ER**, **+DR** (modulation, erreur, compression).

| W | Comportement (résumé) |
|---|------------------------|
| 0 | Seulement vitesse **DTE** (ex. `CONNECT 19200`) ; pas de rapports intermédiaires supplémentaires (défaut). |
| 1 | Modulation, débit ligne, protocole de correction, débit DTE. |
| 2 | Débit **DCE** (ex. `CONNECT 14400`). |

Bits cibles : **S31** bits 2–3.

### `X` — codes étendus et détection de tonalités

`ATX<n>` pilote la détection **dial tone**, **busy**, et ce qui est rapporté avec **CONNECT**. Le guide fournit une **table** (résultats courts/long vs `n`). Les valeurs `n` documentées vont au-delà de 0–2 selon la révision du firmware.

**Point d’attention lab** : en numérotation « aveugle » ou sur ligne PBX, un `X` trop strict peut produire **NO DIAL TONE** ou **BUSY** alors que la ligne est utilisable.

## Profils au démarrage et reset étendu

### `Y` — profil utilisé au power-up

| Valeur | Profil |
|--------|--------|
| 0 | NVM profil 0 |
| 1 | NVM profil 1 |
| 2 | Usine profil 0 |
| 3 | Usine profil 1 |
| 4 | Usine profil 2 |

### `Z` — reset / restauration (variante interface DTE)

Le guide *DTE* liste un `Z` avec **plus** d’options que la section *generic* (profil power-up, NVM, usine). Vérifier le comportement réel avec `ATZ?` / tests si le firmware fusionne les deux sens.

## Signaux V.24 (DTR, DCD, DSR)

### `&C` — option RLSD (**DCD**)

- `0` — DCD toujours actif ; `1` — DCD suit la porteuse (défaut).  
- **S21** bit 5.

### `&D` — interprétation de la chute **DTR**

Valeurs 0–3+ selon doc : interaction forte avec **&Q** (mode buffered / reliable) et **S25** (délai avant prise en compte DTR off). À lire en entier sur la page source pour votre variante matérielle (US vs « W-class »).

### `&S` — comportement **DSR**

- `0` — DSR toujours ON (défaut) ; `1` — DSR actif après tonalité réponse, inactif après perte de porteuse.  
- **S21** bit 6.

## Flux et compression « locale » (DTE ↔ modem)

### `&H` — contrôle de flux **émission** (vers le modem)

| &H | Rôle |
|----|------|
| 0 | Aucun |
| 1 | **CTS** matériel |
| 2 | **XON/XOFF** logiciel |
| 3 | Variante CTS documentée (voir page complète) |

### `&I` — flux logiciel **réception** (du modem vers DTE)

- `0` — ignore XOFF DTE  
- `1` — DC1/DC3 avec **transparence** vers le distant  
- `2` — DC1/DC3 **consommés** localement sans relais (résumé ; détails sur la source)

### `&R` — flux matériel **réception**

- `1` — RTS ignoré ; `2` — RTS/CTS sur chemin réception (modem suspend si RTS off).

### `&K` — compression des données (si correction d’erreur active)

| &K | Effet |
|----|--------|
| 0 | Pas de compression |
| 1–2 | Compression activée (MNP5 / V.42bis selon négociation) |
| 3 | Non supporté |

### `&M` — correction d’erreur et mode synchrone

| &M | Mode |
|----|------|
| 0 | Buffered normal, **sans** correction |
| 4 | Auto-reliable : fallback normal si échec LAPM/MNP |
| 5 | Reliable : tentative LAPM puis MNP, sinon échec connexion |

Les valeurs 1–3 sont réservées dans l’extrait consulté.

## Extensions V.250 (débit et flux « modernisés »)

### `+IPR` — débit série fixe côté DTE

- `+IPR=<rate>` avec `rate` ∈ {0, 300, 1200, …, 230400} selon support.
- `0` = **autodétection** ; force aussi `+ICF=0` (format caractère auto) selon la doc.

### `+IFC` — flux local composé

**Syntaxe** : `+IFC=[<modem_by_DTE>[,<DTE_by_modem>]]`

- Contrôle comment le **DTE** arrête le flux **depuis** le modem, et comment le **modem** arrête le flux **vers** le DTE en phase données (souvent avec V.42 ou mode bufferisé).
- Défaut documenté : `+IFC: 2,2` (circuit 133 / Ready for Receiving des deux côtés — vérifier la table complète sur la page).

### `+ILRR` — rapport du débit de port local

- `0` — pas de `+ILRR:` ; `1` — émission de `+ILRR:<rate>[,<rx_rate>]` avant le `CONNECT` final, après les rapports modulation / erreur / compression si activés.

---

*Enchaînement typique avec la couche modem-modem : [modulation.md](modulation.md), [controle-erreur.md](controle-erreur.md). Pour la numérotation : [controle-appel.md](controle-appel.md).*
