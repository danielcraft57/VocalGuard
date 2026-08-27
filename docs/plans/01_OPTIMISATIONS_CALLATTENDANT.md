# Plan 01 — Optimisations inspirees de Call Attendant

Reference upstream : [emxsys/callattendant](https://github.com/emxsys/callattendant)

Voir aussi [CALLATTENDANT_ETUDE.md](../CALLATTENDANT_ETUDE.md) et [CALLATTENDANT_VS_VOCALGUARD.md](../CALLATTENDANT_VS_VOCALGUARD.md).

---

## Objectif

Integrer les bonnes idees de Call Attendant sans casser ce qui fonctionne deja chez VocalGuard (ATA lignes FR, zero rings, mode telephone).

**Resultat vise :**

- Whitelist → fixe sonne, modem ignore
- Inconnu → repondeur apres N rings (optionnel)
- Bloque → seize immediat + message court
- Repondeur `rings=0` → comportement actuel conserve (ATA au RING, anti-SFR)

---

## Deja couvert dans VocalGuard

| Lecon Call Attendant | VocalGuard |
|----------------------|------------|
| Fixe qui sonne (permitted ignore) | Mode Telephone + `whitelist_ring_only` |
| Zero rings repondeur | Seize sync + ATA |
| VSD desactive | `AT+VSD=128,0` |
| Crochet parallele | DLE `-h` / `-H` pendant VTX |
| Listes blanche / noire | `block_service` |

---

## Gains a implementer (par priorite)

### Priorite haute

#### 1. Screening avant seize

Call Attendant : CID complet → whitelist / blacklist → puis `pick_up()`.

Probleme actuel : en repondeur `rings=0`, on seize au 1er RING avant de savoir si l'appel est bloque ou whitelist.

**Optimisation :**

- Whitelist + `ignore` → pas de seize
- Bloque → seize immediat
- Inconnu → attendre CID (0,3–1 s) sauf urgence `rings=0` anti-SFR

#### 2. Trois profils avec actions separees

| Profil | Comportement cible |
|--------|-------------------|
| `permitted` | fixe sonne, modem ignore |
| `screened` | repondeur apres N rings |
| `blocked` | seize a 0 + message court |

Remplace la bascule UI binaire par une logique fine sans tout melanger.

#### 3. `wait_for_rings` avec abort si fixe decroche

Si les RING s'arretent avant N → quelqu'un a decroche au fixe → ne pas repondre.

Partiellement present (`_wait_phone_mode_rings_end` en mode telephone) ; a generaliser au repondeur avec `rings > 0`.

### Priorite moyenne

#### 4. Messages WAV statiques

Fichiers pre-enregistres pour accueil, bip, message bloque : latence quasi nulle sur Pi.

Fallback configurable si WAV absent → TTS (cache IVR actuel).

#### 5. Menu DTMF anti-robots

« Tapez 1 pour laisser un message » avant enregistrement. `send_dtmf` existe en sortant seulement.

#### 6. Patterns de numeros

Bloquer par motif (`+338%`, masques `P`/`O`) sans entree manuelle.

#### 7. Message bloque leger

WAV court + raccrochage, pas un long TTS.

---

## A ne pas reprendre tel quel

| Call Attendant | Raison |
|----------------|--------|
| Pas de `ATA` | Messagerie operateur FR (SFR) |
| Seize seulement apres CID complet | Trop tard pour `rings=0` |
| Nomorobo | USA uniquement |
| Architecture monolithique Flask | Split API + daemon preferable |
| GPIO LEDs | Lab seulement, pas prioritaire |

---

## Regles seize (cible)

| Profil | rings | Seize au RING ? |
|--------|-------|-----------------|
| permitted + ignore | * | Non |
| screened/blocked + rings=0 | 0 | Oui (ATA, existant) |
| screened + rings>0 | N | Non avant `wait_for_rings` |

---

## Fichiers backend concernes

| Fichier | Role |
|---------|------|
| `backend/core/incoming_call_policy.py` | Nouveau — moteur de decision |
| `backend/core/call_manager.py` | Refactor `handle_incoming_call` |
| `backend/core/modem_handler.py` | `wait_for_rings`, compteur RING |
| `backend/core/config.py` | Structs profils |
| `backend/core/incoming_line_mode.py` | Presets UI |
| `config/config.example.yaml` | Schema documente |

---

## Tests fonctionnels

| Scenario | Mode | Attendu |
|----------|------|---------|
| Numero whitelist | Repondeur + ring_only | Fixe sonne, pas ATA |
| Inconnu | Repondeur rings=0 | ATA, accueil VocalGuard |
| Bloque | Repondeur | ATA, WAV court |
| Inconnu rings=2, fixe decroche ring 1 | Repondeur | Modem n'intervient pas |
| Mode telephone | Telephone | Journal seul, fixe sonne |
| Appel masque | patterns | Bloque auto |
