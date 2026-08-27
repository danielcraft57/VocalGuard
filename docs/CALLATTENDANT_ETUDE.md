# Etude Call Attendant (emxsys/callattendant)

Reference upstream : [github.com/emxsys/callattendant](https://github.com/emxsys/callattendant)

Call Attendant est un repondeur / filtre d'appels Python pour Raspberry Pi, concu autour du modem **US Robotics 5637** (ou Zoom 3095 / Conexant). Il intercepte les appels entrants en **parallele** du telephone fixe, sans empecher le fixe de sonner tant que le modem **ne decroche pas**.

---

## Objectif produit

- Bloquer robocalls, spam et numeros blacklistes **avant ou au premier ring** (selon config).
- Laisser passer les numeros **autorises** vers le telephone domestique (sonnerie normale).
- Gerer messagerie vocale, enregistrement, menu DTMF pour les appels filtres.
- Interface web Flask (port 5000) : journal, listes blanche/noire, messages.

Materiel typique : Raspberry Pi 3B+ + modem USB USR5637, branchement **en parallele** sur la ligne analogique (splitter RJ11).

---

## Principe cle : le fixe sonne parce que le modem reste **on-hook**

C'est le point le plus important pour VocalGuard.

Call Attendant **ne decroche jamais au RING**. Le thread modem lit le port serie, accumule le Caller ID (`DATE`, `TIME`, `NAME`, `NMBR`), et ne met l'appel en file **qu'une fois le CID complet**.

Ensuite seulement :

1. Screening (whitelist / blacklist / patterns / Nomorobo).
2. Choix des actions selon la categorie (permitted / screened / blocked).
3. **`wait_for_rings(n)`** si `n > 0` et action `answer`.
4. **`pick_up()`** uniquement si action contient `answer` et que les conditions sont OK.

Pour les appels **autorises**, la config par defaut est :

```python
PERMITTED_ACTIONS = ("ignore",)
```

`ignore_call()` ne fait **rien** : le modem ne touche pas la ligne. Le telephone parallele sonne et tu peux decrocher normalement.

---

## Flux entrant (resume)

```
RING + CID sur serie
        |
        v
Modem thread : lit DATE/TIME/NAME/NMBR
        |
        v
CID complet -> queue caller
        |
        v
CallAttendant.run() : screening
        |
        +-- Permitted + ignore ----> PAS de pick_up() -> fixe sonne
        |
        +-- Screened / Blocked + answer
                |
                v
        wait_for_rings(N)  (0 = immediat)
                |
                v
        pick_up() : FCLASS=8, VSD off, VLS=1
                |
                v
        greeting / record_message / voice_mail
                |
                v
        hang_up() : ATH0
```

**Delai naturel** : entre le premier RING et `pick_up()`, le CID doit arriver + le screening s'execute. Pendant ce temps, le modem est **on-hook** : le fixe continue de sonner.

---

## Configuration des sonneries (app.cfg)

Trois profils independants, chacun avec `*_RINGS_BEFORE_ANSWER` et `*_ACTIONS` :

| Profil | Usage typique | Rings (exemple) | Actions (exemple) |
|--------|---------------|-----------------|-------------------|
| `PERMITTED_*` | Numero whitelist | 6 (README) ou 0 (app.cfg.example) | `("ignore",)` = laisser sonner le fixe |
| `SCREENED_*` | Inconnu, a filtrer | 0 | `answer`, `greeting`, `record_message` |
| `BLOCKED_*` | Spam / blacklist | 0 | `answer`, `greeting`, `voice_mail` |

Extrait `app.cfg.example` :

```python
BLOCKED_RINGS_BEFORE_ANSWER = 0
SCREENED_RINGS_BEFORE_ANSWER = 0
PERMITTED_RINGS_BEFORE_ANSWER = 0   # exemple fichier ; README montre 6 pour laisser sonner
PERMITTED_ACTIONS = ("ignore",)
```

`wait_for_rings()` (dans `app.py`) :

- Cadence NA : ~6 s par cycle ring (2 s sonnerie + 4 s silence).
- Compte les `RING` via `modem.ring_event`.
- Si la sonnerie s'arrete avant N rings -> suppose que **quelqu'un a decroche** ou que l'appelant a raccroche -> **ne pas repondre** (`ok_to_answer = False`).

---

## Module modem (`hardware/modem.py`)

### Initialisation

- Auto-detection port `/dev/tty*`.
- ATI0 : USR 5637 (`5601`) ou Conexant (`56000`).
- ATZ, ATE0, AT+VCID=1, AT&W0.

### Decrochage : `pick_up()` / `hang_up()`

**Pas de commande ATA** dans Call Attendant. Sequence :

1. `AT+FCLASS=8` (mode voix)
2. `AT+VSD=128,0` (USR) ou `AT+VSD=0,0` (Conexant) — silence detection off
3. `AT+VLS=1` (TAD off-hook)

Raccrochage : `ATH0`, flush buffers, release lock.

### Audio

- **VTX** : lecture WAV 8 kHz 8-bit mono (`play_audio`).
- **VRX** : enregistrement + bip `AT+VTS=[900,900,120]` (`record_audio`).
- Fin flux : DLE ETX / DLE ! selon modele.
- Detection fin : DLE `-s` silence, `-h` hook local, busy tone, etc.

### Thread modem

- Boucle `readline()` sur serie.
- `RING` -> `ring()` (LED + `ring_event` pour `wait_for_rings`).
- CID partiel gere si `NMBR` present avant timeout / RING suivant.

---

## Screening (`screening/`)

| Module | Role |
|--------|------|
| `callscreener.py` | Orchestration whitelist / blacklist / patterns / Nomorobo |
| `whitelist.py` | Liste blanche SQLite |
| `blacklist.py` | Liste noire SQLite |
| `nomorobo.py` | Lookup USA (hors scope FR) |
| `calllogger.py` | Journal appels en base |

Ordre dans `app.py` :

1. Whitelist -> `caller_permitted`
2. Sinon blacklist -> `caller_blocked`
3. Sinon -> `caller_screened`

---

## Messagerie (`messaging/voicemail.py`)

- Menu DTMF optionnel (`voice_mail` action).
- Fichiers WAV dans `resources/` (greeting, goodbye, please_leave_message, etc.).
- Dossier messages : `~/.callattendant/messages/`.

---

## Interface web

- Flask `userinterface/webapp`, port **5000**.
- Dashboard, journal, gestion numeros, ecoute messages.

---

## Limites connues (projet upstream)

- Oriente **USA** (Nomorobo, format CID, cadence ring NA).
- Pas de gestion operateur FR (SFR messagerie reseau, CID ETSI apres 1er ring).
- Pas de `ATA` explicite : peut suffire sur ligne US, insuffisant sur certaines lignes FR.
- Un seul processus monolithique (modem + Flask meme machine).
- Flask dev server en prod (wiki recommande WSGI pour deploy serieux).

---

## Liens utiles

- [Wiki Home](https://github.com/emxsys/callattendant/wiki/Home)
- [User Guide](https://github.com/emxsys/callattendant/wiki/User-Guide)
- [Developer Guide](https://github.com/emxsys/callattendant/wiki/Developer-Guide)
- [PyPI callattendant](https://pypi.org/project/callattendant/)
- [Forum groups.io](https://groups.io/g/callattendant)

---

## Fichiers source a lire en priorite

| Fichier | Contenu |
|---------|---------|
| `callattendant/app.py` | Boucle principale, `wait_for_rings`, `ignore_call`, `answer_call` |
| `callattendant/hardware/modem.py` | Serie, pick_up, VTX/VRX, CID |
| `callattendant/app.cfg.example` | Tous les parametres |
| `callattendant/screening/callscreener.py` | Logique filtrage |
| `callattendant/messaging/voicemail.py` | Menu et enregistrement |
