# Plan 02 — Backend : policy engine et configuration parametrable

Principe : **chaque decision telephonie passe par la config** (YAML + env + API). Jamais de constante metier dans le code.

---

## Chaine de priorite config

```
config/config.yaml              # defauts deploiement
  ↓ override
.env / .env.prod                # secrets + overrides machine
  ↓ override
data/incoming_line_mode.yaml    # preset UI (repondeur / telephone)
  ↓ override (optionnel)
data/incoming_profile_overrides.yaml
  ↓ runtime
incoming_call_policy.resolve()  # source de verite unique
```

Priorite finale : **env > YAML > defauts Pydantic**.

---

## Schema YAML — `incoming_call`

```yaml
incoming_call:
  # --- Global ---
  cid_wait_sec: 2.5
  instant_seize_cid_grace_sec: 0.35
  ring_cycle_sec: 6.0
  ring_quiet_abort_sec: 6.0
  max_incoming_wait_sec: 45.0

  # --- Presets UI ---
  presets:
    voicemail:
      label: "Repondeur"
      default_profile: screened
      permitted_actions: [ignore]
      screened_actions: [answer, greeting, record]
      blocked_actions: [answer, greeting, hangup]
      screened_rings: 0
      blocked_rings: 0
    phone:
      label: "Telephone"
      permitted_actions: [ignore]
      screened_actions: [ignore]
      blocked_actions: [ignore]
      permitted_rings: 4
      screened_rings: 4
      blocked_rings: 4

  # --- Profils (surcharge fine) ---
  profiles:
    permitted:
      rings_before_answer: null       # null = herite du preset
      actions: null
      seize_on_ring: false
      require_cid_before_action: true
    screened:
      rings_before_answer: null
      actions: null
      seize_on_ring: null           # auto : true si rings=0 et answer
      require_cid_before_action: true
    blocked:
      rings_before_answer: 0
      actions: [answer, greeting, hangup]
      seize_on_ring: true
      require_cid_before_action: false

  # --- Whitelist / screening ---
  whitelist_ring_only: true
  whitelist_match: exact            # exact | prefix | e164_normalize
  screened_when_unknown: true

  # --- Patterns ---
  number_patterns:
    enabled: true
    rules:
      - pattern: "+338%"
        action: blocked
        reason: "numero surtaxe"
      - pattern: "P"
        action: blocked
        reason: "masque"
      - pattern: "O"
        action: screened
        reason: "inconnu operateur"

  # --- Audio ---
  audio:
    greeting_source: tts            # tts | wav
    greeting_wav_path: null
    greeting_tts_text: null
    blocked_source: wav
    blocked_wav_path: resources/voice/blocked_short.wav
    blocked_tts_text: null
    record_beep: wav                # wav | dtmf | none
    record_beep_wav_path: resources/voice/beep.wav
    edge_tts_rate: "+12%"

  # --- Messagerie / DTMF ---
  voicemail:
    require_dtmf: false
    dtmf_digit: "1"
    dtmf_prompt_source: tts
    dtmf_prompt_text: "Tapez 1 pour laisser un message."
    dtmf_timeout_sec: 8.0
    max_record_sec: 120
    silence_end_sec: 4.0

  # --- Avance ---
  advanced:
    abort_answer_if_parallel_pickup: true
    blocked_play_message: true
    blocked_message_max_sec: 5.0
    retry_greeting_on_fail: true
    prepare_voice_after_seize: true
```

---

## Variables d'environnement (miroir)

| Variable | Exemple |
|----------|---------|
| `CID_WAIT_SEC` | `2.5` |
| `WHITELIST_RING_ONLY` | `true` |
| `INCOMING_SCREENED_RINGS` | `0` |
| `VOICEMAIL_REQUIRE_DTMF` | `false` |
| `RING_CYCLE_SEC` | `6.0` |
| `GREETING_SOURCE` | `wav` |

---

## Actions parametrables (enum)

| Action | Parametres associes |
|--------|---------------------|
| `ignore` | — |
| `answer` | `seize_on_ring`, `rings_before_answer` |
| `greeting` | `audio.greeting_*` |
| `record` | `voicemail.max_record_sec`, `silence_end_sec`, `record_beep` |
| `dtmf_gate` | `voicemail.require_dtmf`, `dtmf_digit`, `dtmf_timeout_sec` |
| `hangup` | `blocked_message_max_sec` |
| `play_blocked` | `audio.blocked_*` |

L'ordre dans la liste `actions` du profil definit le pipeline (composable comme Call Attendant).

Exemple :

```yaml
screened:
  actions: [answer, greeting, dtmf_gate, record, hangup]
```

---

## Moteur de policy

Nouveau module : `backend/core/incoming_call_policy.py`

```
RING → collecte CID (fenetre configurable)
     → classify(permitted | screened | blocked)
     → merge preset + profile_overrides
     → apply number_patterns (si enabled)
     → resolve CallDecision
     → si ignore : journaliser, wait_rings_end, return
     → si answer + rings>0 : wait_for_rings(N), abort si fixe decroche
     → si answer + rings=0 : seize sync (existant)
     → pipeline audio selon actions
```

### `CallDecision` (log + health)

```json
{
  "profile": "screened",
  "actions": ["answer", "greeting", "record"],
  "rings": 0,
  "seize_on_ring": true,
  "source": "preset:voicemail"
}
```

Aucune branche `if mode == "phone"` dans `call_manager` : uniquement `decision.actions`.

---

## API REST

| Methode | Route | Role |
|---------|-------|------|
| `GET` | `/api/v1/settings/incoming-call` | Config effective complete |
| `PUT` | `/api/v1/settings/incoming-call` | Patch partiel (merge profond) |
| `GET` | `/api/v1/settings/incoming-line-mode` | Preset actif (topbar) |
| `PUT` | `/api/v1/settings/incoming-line-mode` | Bascule repondeur / telephone |
| `GET` | `/api/v1/settings/incoming-call/presets` | Liste presets |
| `PUT` | `/api/v1/settings/incoming-call/presets/{name}` | Editer un preset |
| `GET` | `/api/v1/settings/number-patterns` | Regles patterns |
| `PUT` | `/api/v1/settings/number-patterns` | CRUD patterns |

**Reload live :** `call_manager.reload_incoming_policy()` apres chaque `PUT` (comme `_refresh_instant_ring_seize` aujourd'hui).

### DTO Pydantic (`backend/api/models.py`)

- `IncomingCallConfigResponse`
- `IncomingProfileConfig`
- `IncomingAudioConfig`
- `IncomingVoicemailConfig`
- Validation : `rings >= 0`, actions dans enum fermee, chemins WAV (warning si absent)

---

## Phases backend

| Phase | Contenu | Livrable |
|-------|---------|----------|
| **0** | Cadrage, schema YAML, modeles Pydantic, env mapping | `config.example.yaml` commente |
| **1** | Policy engine + refactor `call_manager` | Profils, actions, rings, seize |
| **1b** | API GET/PUT + reload live | Obligatoire dans le MVP |
| **2** | `wait_for_rings` parametrable | `ring_cycle_sec`, abort parallele |
| **3** | Audio WAV/TTS | `audio.*` par message |
| **4** | Patterns | `number_patterns.rules[]` + API CRUD |
| **5** | DTMF entrant | `voicemail.*`, `wait_dtmf_digit` |
| **6** | Health decision fields | `/health` daemon enrichi |
| **7** | Doc + tests lab | `scripts/modem_lab/` scenarios |

---

## Ce qu'on ne hardcode jamais

- Nombre de sonneries
- Delai CID / cadence ring
- Quels profils repondent ou ignorent
- Texte / WAV des messages
- DTMF obligatoire ou non
- Seize au RING ou apres CID
- Comportement si fixe decroche en parallele

---

## Tests config (non-regression)

| Test | Verifie |
|------|---------|
| `screened_rings: 2` via API | Daemon recharge sans restart |
| Preset phone | Tous `ignore`, pas d'ATA |
| Override `blocked.rings: 0` | Seize immediat |
| `greeting_source: wav` + fichier manquant | Warning + fallback TTS configurable |
| `number_patterns.enabled: false` | Patterns ignores |
| `GET incoming-call` | Config effective = runtime reel |

---

## Risques

| Risque | Mitigation |
|--------|------------|
| Regression anti-SFR | Ne jamais retarder ATA si `rings=0` + answer |
| CID tardif FR | `cid_wait_sec` ; seize apres CID si `rings>0` |
| Race handlers RING | `_incoming_handling` + lock serie |
| TTS vs WAV | Feature flag, rollback facile |
