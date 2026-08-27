# Modem USRobotics USR5637 (reference materiel)

Produit utilise par VocalGuard pour la ligne telephonique analogique (CID, repondeur, appels sortants, audio voix serie).

| Champ | Valeur |
|-------|--------|
| ASIN Amazon | [B0013FDLM0](https://www.amazon.com/gp/product/B0013FDLM0) |
| Nom catalogue | U.S. Robotics USR5637 56K USB Controller Dial-Up External Fax Modem with Voice |
| Modeles / refs | `USR5637` (NA), `USR805637` / `USR065637` (EMEA), OEM `64-245637-00R` |
| Type | Modem externe USB **controller-based** (pas softmodem) |
| Statut constructeur | Discontinue (remplacement NA propose : USR5639, **sans** voix / Modem on Hold / V.22 Fast Connect) |

Sources principales : [fiche produit USR](https://www.usr.com/products/usr5637/), [support USR5637](https://www.usr.com/support/usr5637/), [datasheet PDF](https://support.usr.com/download/datasheets/modem/5637/5637-ds.pdf), [User Guide HTML](https://support.usr.com/support/5637/5637-ug/ref_cmd_use.html), [OEM AT command PDF](https://support.usr.com/support/5637-oem/5637-oem-files/5637-OEM.pdf).

---

## 1. A quoi ca sert (capacites)

Le modem se branche en USB et sur une **ligne analogique PSTN** (RJ-11). Il peut :

### Donnees (dial-up)

- Connexion Internet / PPP jusqu'a ~56 kbps descendant / ~48 kbps montant (V.92), plafonne ~53.3 kbps descendant (reglementation FCC).
- Negociation V.92, V.90, V.34 et standards plus anciens (V.32bis ... V.21, Bell).
- Correction d'erreurs / compression : V.44, V.42, V.42bis, MNP 2-5.
- **Quick Connect** (V.92) : handshake plus court vers un serveur compatible.
- **V.22 Fast Connect** : connexion 1200 bps sans controle d'erreur en ~3 s (POS / ATM).
- **Modem on Hold** (V.92) : prendre un appel vocal pendant une session data si Call Waiting (appli Windows fournie historiquement).
- Videoconference V.80 (heritage).

### Fax

- Fax Groupe 3, **Class 1** (EIA-578 / ITU T.31) ; le jeu de commandes OEM documente aussi Class 1.0 / 2 / 2.0 / 2.1 selon firmware.
- Modulations fax : V.17, V.29, V.27ter, V.21 ch2 (jusqu'a 14.4 kbps typique Class 1).
- Reponse adaptative data/fax (`+FAA`).

### Voix (le coeur pour VocalGuard)

- Jeu **ITU-T V.253** (Telephone Answering Device / speakerphone).
- Decrocher / raccrocher, jouer et enregistrer du PCM sur la ligne (`+VTX` / `+VRX` / `+VTR`).
- Generation et detection DTMF (`+VTS`, evenements DLE).
- Caller ID (`+VCID` / `#CID`) et distinctive ring (`+VDR`) si l'operateur le fournit.
- Compression voix configurable : 8 ou 16 bits ; echantillonnage **7200 / 8000 / 11025 Hz**.
- Ideal pour un repondeur logiciel (TAD).

### Limites importantes

- **Ligne analogique uniquement** (pas de ligne numerique / ISDN / VoIP pure sans ATA).
- Firmware voix souvent a jour a **1.2.23** (fixes CID) ; sans ca certaines fonctions voix / CID sont foireuses.
- Sous Windows 10+, la voix depend d'updates / drivers ; sous Linux (Pi) on parle en AT via **CDC ACM**, sans Wave driver Windows.
- Le softmodem de remplacement USR5639 **ne remplace pas** ce modele pour VocalGuard (pas de voix serie).

---

## 2. Caracteristiques techniques

### Physique / electrique

| Element | Spec |
|---------|------|
| Interface hote | USB 2.0 (bus-powered, hot-plug) |
| Alimentation | USB : typ. 240 mA (1.2 W), max 360 mA (1.8 W) |
| Ligne | 1 prise RJ-11 |
| LEDs | PWR, DATA |
| Dimensions produit | ~ 3.88 x 1.5 x 0.88 in (9.86 x 3.81 x 2.24 cm) |
| Poids | ~ 0.26 lb (0.12 kg) |
| Temperature | Fonctionnement 0-50 C ; stockage -20-70 C |
| Humidite | 20-80 % (op.), 5-95 % (stock.), non condensante |
| Homologations | FCC, IC, UL/CUL, TBR-21 ; approvals multi-pays (US, CA, EU, etc.) |

Contenu boite typique : modem, cordon RJ-11, guide rapide, CD drivers / guides (historique).

### Standards data / fax / voix

- **Data** : V.92, V.90, V.34, V.32bis, V.32, V.22bis, V.22, V.23, V.21 (+ Bell 103/212A selon `ATB`)
- **Erreur / compression** : V.44 / V.42 / V.42bis, MNP 2-4 / 5
- **Fax** : EIA 578 Class 1 ; V.17, V.29, V.27ter, Groupe 3
- **Voix** : ITU-T V.253
- **Compat Hayes** : oui
- **Chipset** : famille controller USR (souvent comparee / voisine des Conexant CX930xx dans la litterature communautaire ; identification runtime via `ATI` / `ATI3`)

### Logiciel / OS

- Windows (XP ... Server 2019), Mac OS X 10.4-10.12 (fax casse a partir de Sierra 10.12), Linux kernel >= 2.4.20 avec **CDC ACM**.
- Drivers Windows : `USR5637Voice64bit.EXE` / `32bit` (support USR).
- Firmware recommande : **1.2.23** (flasher Win/Linux/Mac sur la page support).
- Garantie constructeur historique : 2 ans.

### Linux / Raspberry Pi (prod VocalGuard)

- Apparait en general comme `/dev/ttyACM0` (ou similaire) via `cdc_acm`.
- Baudrate applicatif VocalGuard : **115200** (`modem_baudrate` dans la config).
- Pas besoin du CD Windows : le noyau gere le port serie AT.
- Voir aussi [TELEPHONY_STACK.md](TELEPHONY_STACK.md) et [AUDIO_SETUP_RPI.md](AUDIO_SETUP_RPI.md).

---

## 3. Modes de service (`+FCLASS`)

| Valeur | Mode |
|--------|------|
| `0` | Data (defaut). Necessaire pour recevoir `RING` proprement en veille. |
| `1` / `1.0` | Fax Class 1 / 1.0 |
| `2` / `2.0` / `2.1` | Fax Class 2 (selon firmware / doc OEM) |
| `8` | **Voix** (TAD / speakerphone) |

VocalGuard reste en `AT+FCLASS=0` en idle (avec CID), puis passe en `8` pour audio / decrochage voix.

---

## 4. Regles d'entree des commandes AT

- Prefix `AT` sauf `+++`, `A/`, `A>`.
- Finir par CR (ENTER). Majuscules ou minuscules, pas un melange.
- Longueur max ~58 caracteres (hors `AT`, espaces, CR) ; chaine de numerotation jusqu'a **60** caracteres.
- Syntaxe etendue : `CMD=valeur`, `CMD?` (lecture), `CMD=?` (plage).
- Aide integree : `AT$`, `AT&$`, `AT+$`, `ATS$`, `AT+GCI$`.
- Defauts usine charges avec `&F` / template `&F1` selon guide.

Escape online data -> command : `+++` (garde-temps `S12`, caractere `S2`, defaut `+`).

---

## 5. Commandes data / generales (resume)

Liste issue du [guide de commandes](https://support.usr.com/support/5637/5637-ug/ref_cmd_use.html) et du PDF OEM.

### Controle de base

| Commande | Role |
|----------|------|
| `A` | Decrocher / repondre (answer) |
| `A/` | Repeter la derniere commande (sans `AT`) |
| `A>` | Repeter en boucle (S6) |
| `D...` | Composer (voir modificateurs) |
| `E0` / `E1` | Echo off / on |
| `H0` / `H` | Raccrocher (on-hook) |
| `H1` | Decrocher (off-hook) sans handshake data |
| `I` / `I0`... | Infos identification / diagnostics |
| `L0`...`L3` | Volume haut-parleur modem |
| `M0`...`M3` | Controle HP |
| `O` | Retour online data apres escape |
| `P` / `T` | Pulse / tone dial |
| `Q0` / `Q1` | Result codes on / off |
| `V0` / `V1` | Codes numeriques / texte |
| `W0`...`W2` | Options de resultats connexion |
| `X0`...`X7` | Detection dialtone / busy / resultats etendus (defaut `X4`) |
| `Z` / `Z0` / `Z1` | Reset + profil stocke |
| `S` / `Sn?` / `Sn=v` | Registres S |

### Prefixe `&`, `\`, `%`, `#`

| Commande | Role |
|----------|------|
| `&F` / `&F1` | Restaurer usine |
| `&W` | Sauver config courante en NVRAM |
| `&Zn=s` | Stocker un numero (n = 0..2) |
| `&C` | Comportement DCD |
| `&D` | Comportement DTR |
| `&K` | Flow control / compression selon variante |
| `&G` | Guard tone |
| `&T` | Self-tests |
| `&B`, `&H`, `&M`, `&N`, `&P`, `&S`, `&Y`, `&A` | Port serie, ARQ, vitesse forcee, pulse ratio, DSR, break, etc. |
| `\A` | Taille bloc MNP max |
| `\B` | Envoyer break |
| `\G` / `\X` | Flow control port / XON pass-through |
| `\N` | Mode controle d'erreur |
| `\V` | Protocol result codes |
| `%B` | Voir blacklist |
| `%E` | Auto fall-back / fall-forward |
| `%C` | Compression |
| `#CID` | Caller ID (alias historique) |
| `#UD` | Diagnostics Unimodem |

### V.8 / compression / modulation (extrait)

| Commande | Role |
|----------|------|
| `+A8E` | Controle V.8 / V.8bis |
| `+A8T` | Envoi signal / message V.8bis |
| `+DCS` | Algo compression |
| `+DR` | Reporting compression |
| `+DS` | V.42bis |
| `+DS44` | V.44 |
| `+EB` | Break en error-control |
| `+ER` / `+ESA` | Error control reporting / params |
| `+GCAP` | Capacites |
| `+GCI` | Code pays (ITU T.35) |
| `+IFC` | Flow control DTE-DCE |
| `+ILRR` / `+IPR` / `+ITF` | Rate reporting / rate fixe / seuils TX |
| `+MR` / `+MS` | Reporting / selection modulation |
| `+PCW` | Call Waiting enable |
| `+PIG` | PCM upstream ignore |
| `+PMH` / `+PMHD` / `+PMHF` / `+PMHR` / `+PMHT` | Modem on Hold |
| `+PQC` / `+PSS` | Phase courte V.92 / short sequence |

Pays utiles pour `+GCI` (hex) : France `3D`, US `B5`, UK `B4`, etc. (liste complete dans le guide data).

### Modificateurs de composition (`ATD...`)

| Modif. | Effet |
|--------|-------|
| `T` / `P` | Tone / pulse |
| `L` | Relancer le dernier numero (en debut de chaine) |
| `W` | Attendre seconde tonalite |
| `,` | Pause (`S8`) |
| `!` | Hook flash (~0.5 s) |
| `@` | Attendre 5 s de silence (sinon `NO ANSWER`) |
| `;` | Rester en command mode apres composition (**sans** raccrocher) - utilise par VocalGuard pour appels voix |
| `$` | Detection bong tone |
| `S=n` | Numeroter depuis NVRAM n |
| `^` | Desactiver data calling tone |
| `V` | Composer en mode speakerphone |

Exemple VocalGuard : `ATD0612345678;` puis session voix.

---

## 6. Commandes fax (Class 1)

| Commande | Role |
|----------|------|
| `+FAA=0/1` | Reponse adaptative fax-only / auto data-fax |
| `+FCLASS=1` | Entrer mode fax Class 1 |
| `+FLO` | Flow control fax |
| `+FMI?` / `+FMM?` / `+FMR?` | Fabricant / produit / version |
| `+FPR` | Debit port fax |
| `+FRH` / `+FRM` / `+FRS` | Reception HDLC / data / silence |
| `+FTH` / `+FTM` / `+FTS` | Emission HDLC / data / pause |

Modulations typiques `n` pour `+FRx` / `+FTx` : 3 (V.21), 24/48 (V.27ter), 72/96 (V.29), 73-146 (V.17 / short train).

Passage voix -> fax : detecter DLE-c (fax calling tone), `AT+FCLASS=1`, puis `ATA`.

---

## 7. Commandes voix (V.253) - detail

Resume officiel (Table 230 du guide) :

| Commande | Description |
|----------|-------------|
| `+FCLASS=8` | Entrer mode voix |
| `+VCID` | Caller ID |
| `+VDR` | Distinctive ring |
| `+VEM` | Masque evenements (IS-101) |
| `+VGM` | Gain micro speakerphone |
| `+VGR` | Gain reception / record |
| `+VGS` | Gain HP speakerphone |
| `+VGT` | Volume playback |
| `+VIP` | Reinit params voix (sans changer FCLASS) |
| `+VIT` | Timer inactivite DTE/DCE (secondes) |
| `+VNH` | Hang-up auto on/off |
| `+VLS` | Source / destination analogique |
| `+VPR` | Rate interface (souvent no-op, repond OK) |
| `+VRA` / `+VRN` | Timers ringback |
| `+VRX` | Reception audio (record) -> `CONNECT` puis flux |
| `+VSD` | Detection de silence |
| `+VSM` | Methode compression + sample rate |
| `+VSP` | Speakerphone on/off |
| `+VTD` | Duree bip / DTMF (0.01 s) |
| `+VTR` | Full-duplex TX+RX |
| `+VTS` | Generation DTMF / tons |
| `+VTX` | Emission audio (playback) -> `CONNECT` puis flux |

### `+VLS` (branchements analogiques)

| n | Signification (doc USR) |
|---|-------------------------|
| 0 | DCE on-hook ; telephone local branche operateur |
| 1 | **DCE off-hook**, modem sur la ligne (TAD) - utilise par VocalGuard |
| 2 | Off-hook ; telephone local vers DCE |
| 3 | Off-hook ; local + operateur + DCE |
| 4 | Speaker -> DCE, on-hook (playback messages) |
| 5 | Speaker -> DCE, off-hook (call screening / mute micro) |
| 6 | Micro -> DCE, on-hook (enregistrer greeting) |
| 7 | Micro + speaker, off-hook (speakerphone) |

### `+VSM` (compression USR5637)

| Code | Format | Rates |
|------|--------|-------|
| 128 | 8-bit linear | 7200, 8000, 11025 |
| 129 | 16-bit linear (defaut guide) | 7200, 8000, 11025 |
| 130 | 8-bit A-law | 8000 |
| 131 | 8-bit u-law | 8000 |
| 132 | IMA ADPCM | 8000 |
| 133 | G.729 | 8000 |

VocalGuard utilise **`AT+VSM=128,8000`** (PCM 8-bit mono 8 kHz) pour le USR5637.

### `+VSD` (silence)

- Forme : `AT+VSD=<sensibilite>,<intervalle>`
- `AT+VSD=128,0` : sensibilite nominale, intervalle 0 = **desactive** la detection (utilise VocalGuard).
- Intervalle non nul (ex. 50) : fin de message apres silence (ex. 5 s si unite 0.1 s selon contexte TAD).

### `+VCID`

| Valeur | Effet |
|--------|-------|
| 0 | CID off (defaut usine) |
| 1 | CID formate (`DATE=` / `TIME=` / `NMBR=` / `NAME=`) |
| 2 | CID brut / non formate |

Notes terrain (USR5637) :

- En mode data, `AT+VCID=1` suffit souvent.
- Si le CID ne sort pas : essayer avant les sonneries `AT+FCLASS=8`, `AT+PCW=0`, `AT+VCID=1` (retours communautaires), firmware **1.2.23**, et service Caller ID / Call Waiting selon le pays.
- Identifier le firmware : `ATI3`.

### `+VTS` (DTMF / tons)

Exemples :

- `AT+VTS="5"` ou `AT+VTS=5` : digit
- `AT+VTS=[933,0,120]` : bip ~1.2 s
- `AT+VTS=!` : hook flash

Duree par defaut via `+VTD` (defaut souvent 100 = 1.00 s selon table ; DTMF aussi lies a `S9` / `S11`).

### Flux audio transparent (`+VTX` / `+VRX`)

1. `AT+FCLASS=8`
2. Configurer `+VSD`, `+VSM`, eventuellement `+VGT` / `+VGR`
3. `AT+VLS=1` (off-hook TAD) si besoin
4. `AT+VTX` ou `AT+VRX` -> attendre `CONNECT`
5. Envoyer / lire des octets PCM bruts sur le port serie
6. Terminer avec sequences **DLE** (caractere `0x10`) :

Evenements DCE -> DTE (apres DLE) : digits DTMF, `a` answer, `b` busy, `c` fax tone, `d` dialtone, `e` data tone, `h`/`H` local on/off-hook, `R` ring, `s` silence, `@` CAS, etc.

Codes DTE -> DCE utiles : fin de TX, `!` fin de receive state, `u`/`d` volume +/- 1 dB.

Sequence TAD typique (guide USR) : greeting via `+VTX`, bip `+VTS`, record `+VRX`, puis `ATH`.

---

## 8. Registres S (resume)

| Registre | Role | Defaut typique |
|----------|------|----------------|
| S0 | Auto-answer apres n sonneries (0 = off) | 0 |
| S1 | Compteur de sonneries (RO) | 0 |
| S2 | Caractere escape (`+`) | 43 |
| S3 / S4 / S5 | CR / LF / backspace | 13 / 10 / 8 |
| S6 | Attente avant dial (s) | 2 |
| S7 | Timeout connexion (s) | 50 |
| S8 | Pause virgule (s) | 2 |
| S9 / S11 | DTMF off / on duration (ms) | 95 |
| S10 | Delai disconnect auto (x100 ms) | 20 |
| S12 | Escape guard time (x20 ms) | 50 |
| S28 / S37 / S38 | V.34 / dial rate / 56K downstream | - |
| S30 | Inactivity timer (min) | 0 |
| S32 / S33 | Volume / freq ring synthetique | - |
| S71 / S72 | Silence sensitivity / timer | 128 / 50 |
| S82 | Distinctive ring reporting | 0 |
| S91 | Niveau TX ligne (dB) | 10 |
| S127 | Impedance activation CID | 0 |

Lecture : `ATS0?` - ecriture : `ATS0=0`.

---

## 9. Result codes (texte, `V1`)

Courants : `OK`, `CONNECT`, `RING`, `NO CARRIER`, `ERROR`, `NO DIALTONE`, `BUSY`, `NO ANSWER`, `BLACKLISTED`, `DELAYED`, `CALL WAITING DETECTED`, `CONNECT/FAX`, etc. (selon `Xn`).

En mode voix apres `+VTX`/`+VRX` : `CONNECT` puis flux binaire (ne pas parser comme ASCII pendant le stream).

---

## 10. Sequences utiles (recettes)

### Init veille (style VocalGuard)

```text
AT
ATE0
AT+FCLASS=0
AT+VCID=1
ATI
```

### Decrocher repondeur + jouer un WAV PCM

```text
AT+FCLASS=8
AT+VSD=128,0
AT+VSM=128,8000
AT+VLS=1
AT+VTX
CONNECT
<octets PCM 8-bit 8 kHz>
<DLE fin TX>
ATH
```

### Appel sortant voix + DTMF

```text
ATD0612345678;
AT+FCLASS=8
AT+VLS=1
AT+VTS="1"
...
ATH
```

### Identifier le modem

```text
ATI
ATI3
AT+FMI?
AT+FMM?
AT+GCAP
```

---

## 11. Usage dans VocalGuard

Implementation : `backend/core/modem_handler.py`, orchestration `backend/core/call_manager.py`.
Stack runtime (daemon, ports, Pi, CID, modes) : [TELEPHONY_STACK.md](TELEPHONY_STACK.md).

| Besoin | Commandes / comportement |
|--------|--------------------------|
| Init | `AT`, `ATE0`, `AT+FCLASS=0`, `AT+PCW=0` (option), `AT+VCID=1`, `ATI` / `ATI3`, `+GCI` pays optionnel |
| Entrant | surveillance `RING` + champs CID ; fenetre `cid_wait_sec` ; `ATA` / seize rapide `FCLASS=8` + `VLS=1` |
| Sortant | `ATD<numero>;` |
| DTMF | `AT+VTS=...` |
| Playback | `+VSM=128,8000` (USR) puis `+VTX` ; PCM avec escape DLE (`0x10` double) |
| Record / live | `+VRX` (PCM 8 kHz 8-bit) ; stop hangup / silence |
| Hangup | sortir du stream transparent puis `ATH`, retour `+FCLASS=0` + `+VCID=1` |
| Gains | `+VGR` / `+VGT` si `modem_voice_vgr` / `modem_voice_vgt` en config |

Perimetre appels sortants : [MODEM_APPELS_MVP_SCOPE.md](MODEM_APPELS_MVP_SCOPE.md).

Le code gere aussi un autre modem type Conexant/Zoom (`+VSM=1,8000,0,0`, `+VSD=0,0`) ; pour le **USR5637** rester sur les variantes USR ci-dessus. Firmware recommande : **1.2.23** (`ATI3`).

Lab CID sans UI : `python scripts/modem_lab_cid_wait.py --port /dev/modem56k`.


---

## 12. Liens et documents officiels

| Ressource | URL |
|-----------|-----|
| Amazon (ASIN projet) | https://www.amazon.com/gp/product/B0013FDLM0 |
| Fiche produit | https://www.usr.com/products/usr5637/ |
| Support / drivers / firmware | https://www.usr.com/support/usr5637/ |
| Datasheet | https://support.usr.com/download/datasheets/modem/5637/5637-ds.pdf |
| Guide commandes (index) | https://support.usr.com/support/5637/5637-ug/ref_cmd_use.html |
| Data commands | https://support.usr.com/support/5637/5637-ug/ref_data.html |
| Fax commands | https://support.usr.com/support/5637/5637-ug/ref_fax.html |
| Voice commands | https://support.usr.com/support/5637/5637-ug/ref_voice.html |
| OEM AT reference (PDF complet) | https://support.usr.com/support/5637-oem/5637-oem-files/5637-OEM.pdf |
| Jeu AT 56K (FAQ support) | lie depuis la page support ("56K AT command set") |

Pour le detail exhaustif d'une commande rare (tous les parametres `+MS`, `+PMH`, etc.), se reporter au PDF OEM : c'est la reference la plus complete publiee par USR pour cette famille controller-based.
