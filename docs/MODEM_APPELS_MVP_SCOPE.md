# Périmètre technique — Appels sortants modem (MVP)

Périmètre fonctionnel des appels sortants / modale composeur. **Configuration runtime (API + daemon, dev PC + Pi)** : [TELEPHONY_STACK.md](TELEPHONY_STACK.md).

## Inclus dans ce MVP

- Page `Appels` avec bouton `Composer`.
- Modale de composition:
  - saisie du numero,
  - demarrage d'appel sortant,
  - raccrochage,
  - clavier DTMF (`0-9`, `*`, `#`).
- Endpoints backend pour:
  - demarrer un appel sortant,
  - envoyer une touche DTMF,
  - terminer un appel.
- Evenements realtime websocket:
  - etat d'appel sortant (`dialing`, `connected`, `ended`),
  - transcription partielle et finale.
- STT Vosk en boucle par chunks audio pendant l'appel (best effort selon modem/device).
- Persistance en base:
  - appel cree comme appel sortant,
  - statut mis a jour,
  - transcription finale sauvegardee.

## Hors périmètre initial (document historique)

Les éléments ci‑dessous étaient « hors MVP » au moment de la rédaction ; une partie a depuis été couverte (écoute live via WebSocket audio sur le daemon — voir TELEPHONY_STACK).

- ~~Streaming audio navigateur~~ → WebSocket `/ws/outgoing-call/{id}/audio` (daemon) + `NEXT_PUBLIC_TELEPHONY_WS_BASE` si API et modem ne sont pas sur le même hôte.
- Synchronisation mot-à-mot audio/transcription.
- Gestion multi-appels simultanes.
- Durcissement production (retries avances, supervision systemd, QoS RTC fine).

## Hypothèses techniques

- Soit **tout sur le Pi** : FastAPI + modem local ; soit **API sur PC** et modem sur Pi via **`USE_TELEPHONY_DAEMON=1`** (voir TELEPHONY_STACK).
- Le moteur Vosk est present et charge.
- Le modem accepte `ATD` pour la composition et `AT+VTS` pour les tonalites DTMF.
- L'acquisition audio line-in est disponible via le chemin deja configure dans VocalGuard.

## Prochaines étapes (post-MVP)

- Améliorer l’écoute live (qualité, jitter, indicateurs).
- Fiche détail d’appel avec lecteur et transcription historisée.
- Ajouter des tests d'integration Pi (147 + sequence DTMF `0`, `2`).
