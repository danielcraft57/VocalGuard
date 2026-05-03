# DLE et flux audio série (`+VTX` / `+VRX`)

Source : sections *Events Reported to the DTE*, `+VRX`, `+VTX` dans `5637-OEM.pdf`.

## Rôle du préfixe DLE

En mode voix, après décroché, le modem peut envoyer des **codes événements** précédés de **DLE** (ASCII 0x10) vers le DTE. C’est le mécanisme « IS-101 style » pour distinguer **données audio** et **signaux de contrôle**.

**Note manuel :** la description détaillée des événements peut ne pas s’appliquer de la même façon aux modems **host-based** ; le texte cible explicitement les modems **controller-based**.

## Codes DLE : DCE → DTE (extrait)

| Code (après DLE) | Description |
|------------------|-------------|
| `0`–`9`, `A`–`D`, `#`, `*` | Touches DTMF |
| `a` | Tonalité de réponse (*answer tone*) |
| `b` | Occupé |
| `c` | Appel fax |
| `d` | Tonalité d’invitation à composer |
| `e` | Tonalité d’appel données |
| `h` | Téléphone local **raccroché** |
| `H` | Téléphone local **décroché** |
| `R` | Sonnerie |
| `s` | **Timer de silence** expiré |
| `<ETX>` | Fin de transmission de données vocales |
| `@` | Tonalité CAS détectée |

## Codes DLE : DTE → DCE (extrait)

| Code | Description |
|------|-------------|
| `u` / `d` | Monter / baisser le volume (~1 dB) |
| `<ETX>` | **Fin** de l’état **émission** vocale (fin de `+VTX`) |
| `!` | **Fin** de l’état **réception** vocale (sortie de `+VRX`) |

## `AT+VRX` — réception

- Entrée : `AT+VRX` → le modem répond **`CONNECT`**.
- Le flux audio (et les séquences DLE) arrive sur le **port série** (pas via driver wave si on est en mode série pur).

**Sortie de l’état réception :**

1. Le DTE envoie **`<DLE>` + `!`**, ou
2. Expiration du **timer de détection de silence** : le modem peut envoyer des codes du type **`<DLE>s`** (raccroché présumé) ou **`<DLE>q`** (fin de message présumée) selon le contexte décrit dans le manuel.

## `AT+VTX` — émission

- Entrée : `AT+VTX` → **`CONNECT`** si le DCE est en liaison avec un autre équipement **décroché**.
- Le DTE envoie les **échantillons** (format défini par `AT+VSM`).

**Sortie de l’état émission :**

1. Le modem reçoit **`<DLE>` + `<ETX>`** **dans** le flux vocal, ou
2. Expiration du **timer d’inactivité** (`+VIT`).

## Encodage côté application (VocalGuard)

**Code :** paquet ackend/core/telephony_events/ (motifs DLE, scan tampon, indices V.250).

Dans `modem_handler.py`, la fin d’émission série USR est typiquement :

- **DLE + ETX** : octets `0x10`, `0x03` (équivalent aux séquences ci-dessus).

Les modems **Conexant** (autre famille) peuvent exiger une séquence différente (ex. plusieurs DLE) — le manuel **5637** décrit le comportement **U.S. Robotics**.

## Cohérence avec `+VSD`

La détection de silence (`AT+VSD`) conditionne le déclenchement d’événements comme **`<DLE>s`** en fin d’enregistrement ou de ligne. Pour des enregistrements longs ou du debug, on désactive souvent la détection avec **`AT+VSD=128,0`** (cf. exemples TAD du PDF).

## Enchaînement type

Pour un scénario **répondeur** avec port série : `+FCLASS=8` → configuration `+VSM` / `+VSD` → `+VLS` (décroché) → `+VTX` (message) → `DLE ETX` → `+VLS` (écoute) → `+VRX` → … — voir [5637-scenarios-repondeur.md](./5637-scenarios-repondeur.md).
