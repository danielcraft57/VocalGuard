# Call Attendant vs VocalGuard — comparatif telephonie

Objectif : comprendre pourquoi **Call Attendant laisse sonner le fixe** et comment VocalGuard reproduit ou ameliore chaque comportement.

Voir aussi [TELEPHONY_STACK.md](TELEPHONY_STACK.md) et [CALLATTENDANT_ETUDE.md](CALLATTENDANT_ETUDE.md).

---

## Resume en une phrase

| | Call Attendant | VocalGuard |
|---|----------------|------------|
| **Fixe sonne** | Oui, tant que `PERMITTED_ACTIONS = ignore` et modem on-hook | Mode **Telephone** : pas de seize. Mode **Repondeur** : seize immediat (fixe coupe). |
| **Repondeur** | Modem decroche apres screening (`pick_up` = VLS=1) | Modem decroche au RING (`ATA` + VLS=1) pour battre messagerie SFR |
| **Quand decrocher** | Apres CID complet + screening + `wait_for_rings` | Repondeur : immediat (`rings=0`). Telephone : jamais (auto_answer=false). |

---

## Tableau comparatif detaille

| Sujet | Call Attendant | VocalGuard |
|-------|----------------|------------|
| Stack | Python monolithique + Flask :5000 | FastAPI :8000 + daemon telephony :8090 + Next.js |
| Modem | USR5637 / Conexant | USR5637 (meme famille AT) |
| Decrochage | `AT+FCLASS=8` + `AT+VLS=1` seulement | `ATA` puis mode voix (lignes FR / SFR) |
| Seize au RING | **Non** | **Oui** en mode repondeur (`instant_ring_seize`) |
| CID | Attend DATE+TIME+NAME+NMBR avant action | Fenetre CID configurable ; seize peut preceder NMBR |
| Laisser sonner le fixe | `PERMITTED_ACTIONS=("ignore",)` | `incoming_auto_answer=false` + `phone_mode_rings` |
| Couper sonnerie fixe | `BLOCKED/SCREENED` + `rings=0` + `answer` | `rings_before_answer=0` + seize sync |
| Messagerie | Menu DTMF, fichiers WAV statiques | Repondeur simple (bip + record) ou IVR STT |
| Blocage | Whitelist, blacklist, patterns, Nomorobo | Block service, listes, OSINT |
| UI | Flask integre | Next.js + WebSocket temps reel |
| Prod | Wiki + systemd (a configurer) | node14, systemd, nginx |

---

## Pourquoi Call Attendant ne fait pas sonner le fixe (pour les spams)

Ce n'est pas magique : pour les appels **bloques**, il decroche a `rings=0` avec `pick_up()` **avant** que le fixe ait le temps de sonner longtemps, et coupe la sonnerie parallele (off-hook sur la ligne partagee).

Pour les appels **autorises**, il **n'appelle jamais** `pick_up()` : le modem reste on-hook. Le fixe sonne comme si le Pi n'existait pas.

---

## Equivalences de configuration

### Laisser le fixe sonner (mode telephone VocalGuard)

**Call Attendant :**

```python
PERMITTED_ACTIONS = ("ignore",)
PERMITTED_RINGS_BEFORE_ANSWER = 6  # optionnel si un jour tu passes en answer
```

**VocalGuard :**

```yaml
# UI topbar : mode "Telephone"
# ou data/incoming_line_mode.yaml :
mode: phone
incoming_auto_answer: false
rings_before_answer: 4   # phone_mode_rings
```

`instant_ring_seize` = **false** (pas de `ATA`/VLS au RING).

### Repondeur qui coupe le fixe (mode voicemail VocalGuard)

**Call Attendant :**

```python
SCREENED_ACTIONS = ("answer", "greeting", "record_message")
SCREENED_RINGS_BEFORE_ANSWER = 0
```

**VocalGuard :**

```yaml
mode: voicemail
incoming_auto_answer: true
rings_before_answer: 0
instant_seize_cid_grace_sec: 0.35  # obsolete si seize immediat au RING
```

Comportement : seize sync au premier `RING` (`ATA` + voix), fixe parallele coupe.

### Whitelist : fixe sonne, inconnu -> repondeur

**Call Attendant :** natif (permitted ignore, screened answer).

**VocalGuard :** `whitelist_ring_only: true` dans config — numeros whitelist ne declenchent pas l'ATA modem (fixe gere l'appel).

---

## Lecons appliquees dans VocalGuard

1. **Ne pas decrocher en mode telephone** — aligne sur `ignore_call` Call Attendant.
2. **Separer `rings_before_answer` par mode** — repondeur 0, telephone 4+.
3. **ATA pour operateur FR** — Call Attendant n'en a pas besoin (US) ; SFR exige une vraie reponse reseau.
4. **VSD desactive pendant enregistrement** — meme idee que Call Attendant (`AT+VSD=128,0`).
5. **Detection crochet parallele** — DLE `-h` / `-H` pendant VTX (call screening).
6. **Silence logiciel** plutot que VSD agressif pendant VRX (stabilite USB Pi).

---

## Pistes d'evolution VocalGuard (inspirees Call Attendant)

| Fonctionnalite Call Attendant | Interet pour VocalGuard | Statut |
|------------------------------|-------------------------|--------|
| `wait_for_rings` avant answer | Utile si whitelist_ring_only etendu | Partiel (`_wait_phone_mode_rings_end`) |
| Actions tuple (`ignore`, `answer`, `greeting`, `vm`) | Modele flexible par profil appelant | Simplifie (voicemail / phone) |
| Menu DTMF voice mail | Anti-spam messages automatiques | Non |
| GPIO LEDs ring/blocked | Debug physique | Non |
| Profils BLOCKED/SCREENED/PERMITTED separes | Granularite fine | Partiel (block + whitelist) |
| Pas de seize au RING | Cle pour fixe qui sonne | Oui en mode phone |

---

## Fichiers VocalGuard concernes

| Fichier | Role telephonie parallele |
|---------|---------------------------|
| `backend/core/incoming_line_mode.py` | Modes voicemail / phone, rings |
| `backend/core/call_manager.py` | `handle_incoming_call`, seize, repondeur |
| `backend/core/modem_handler.py` | Seize sync, ATA, VTX/VRX |
| `config/config.example.yaml` | `rings_before_answer`, `phone_mode_rings` |
| `frontend/src/components/Topbar.tsx` | Bascule UI mode ligne |

---

## Messagerie SFR vs VocalGuard

Call Attendant (US) : la ligne est souvent "repondue" par `VLS=1` suffisamment tot.

En France (SFR, Orange, etc.) : la **messagerie operateur** prend l'appel si personne ne repond cote reseau. VocalGuard envoie **`ATA`** au seize pour que le reseau voie un decrochage reel, pas seulement un off-hook local.

Action utilisateur possible : desactiver ou retarder la messagerie SFR dans l'espace client operateur.
