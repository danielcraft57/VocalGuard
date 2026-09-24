# Telephonie VoIP (fondations)

## Objectif

Le modem USB (USR5637) reste **demi-duplex** en pratique (VRX / VTX). Le
full-duplex produit passera par **VoIP (SIP + RTP)**. Tant qu'il n'y a pas de
compte SIP, VocalGuard expose un **stub loopback** derriere la meme interface
transport que le modem.

`AT+VTR` (full-duplex serie modem) n'est **pas** du VoIP : c'est une amelioration
audio analogique optionnelle (`outgoing_use_vtr`), distincte de `telephony_backend`.

## Architecture

```
App mobile / dialer browser
        |
        |  REST Bearer /api/v1/public/calls/outgoing/*
        v
API (FastAPI)  --proxy-->  daemon :8090  (si USE_TELEPHONY_DAEMON)
        |
        v
OutgoingCallSession + WS /ws/outgoing-call/{id}/audio  (PCM s16le 16 kHz)
        |
        v
CallManager.transport  <--- factory selon telephony_backend
        |
        +-- ModemTransport  -> ModemHandler (PSTN)
        +-- VoipTransport   -> stub echo (pas de registre SIP)
        +-- DualTransport   -> entrant modem + sortant voip
```

Mobile (`mobile/app/(tabs)/dialer.tsx`) : start -> WS audio -> hangup/DTMF.
Ping `GET /public/mobile/ping` expose `telephony_backend`, `telephony_ws_base`,
`outgoing_ready`. Config optionnelle : `telephony_public_ws_base`.

Fichiers :

- `backend/core/telephony_transport.py` — contrat + stub
- `backend/api/routes/voip.py` — status + simulate-incoming
- Config : `telephony_backend`, placeholders `sip_*`

## Config

Dans `config.yaml` / env :

| Cle | Defaut | Role |
|-----|--------|------|
| `telephony_backend` / `TELEPHONY_BACKEND` | `modem` | `modem` \| `voip` \| `dual` |
| `sip_uri` / `SIP_URI` | null | Placeholder futur compte |
| `sip_user` / `SIP_USER` | null | Idem |
| `sip_password` / `SIP_PASSWORD` | null | Idem (via `.env`) |
| `sip_realm` / `SIP_REALM` | null | Idem |
| `outgoing_use_vtr` | false | Modem AT+VTR seulement (pas VoIP) |

Prod node14 : laisser `telephony_backend: modem`.

## Tests manuels (daemon)

1. Lancer le daemon avec `TELEPHONY_BACKEND=voip` (ou dual).
2. Status : `GET http://127.0.0.1:8090/api/v1/voip/status`
3. Entrant simule :
   `POST /api/v1/voip/simulate-incoming` body `{"phone_number":"0612345678"}`
4. Sortant : dialer web ou app mobile (appairage) — log `Full-duplex VoIP stub` ;
   micro echoe sur la ligne (full duplex natif Expo web ; natif = downlink WAV).

## Brancher un vrai compte SIP (plus tard)

1. Remplir `sip_*` / secrets `.env`.
2. Remplacer le corps de `VoipTransport` (ou sous-classe) par pjsua2 / Asterisk /
   fournisseur (INVITE, RTP G.711/Opus, BYE).
3. Garder le contrat `dial` / `answer` / `hangup` / `read_pcm` / `write_pcm`.
4. Le dialer navigateur et les events (`CALL_INCOMING`, `CALL_OUTGOING_*`) restent.

## Hors scope actuel

NAT, TLS/SRTP, codecs reels, DID public, remplacement complet de la ligne fixe.
