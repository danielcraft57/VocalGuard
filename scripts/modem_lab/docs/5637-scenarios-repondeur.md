# Scénarios TAD (répondeur) — extraits du manuel

Source : *Voice Modem Command Examples* (exemples #7 et #8), pages ~119–121 du PDF `5637-OEM.pdf`.

Ces séquences illustrent le mode **TAD** (*Telephone Answering Device*) : message d’accueil, bip, enregistrement, détection de fin par silence.

## Différence exemple #7 vs #8

- **#7 — IS-101 / port série :** émission et réception des échantillons via le **port COM** (`+VTX` / `+VRX`), avec événements **DLE**.
- **#8 — Pilote audio Windows :** émission / réception via **wave driver** (`WAVE_OUT_*`, `WAVE_IN_*`) ; pas d’usage de `+VTX`/`+VRX` pour le flux PCM.

Pour **Linux / VocalGuard** sans driver wave dédié, l’analogue pratique est l’approche **#7** (flux série).

## Séquence type (extrait #7 — simplifié)

Ordre logique tel que documenté (réponses `OK` / `CONNECT` omises ici) :

1. **`RING`** — appel entrant.
2. **`AT+FCLASS=8`** — entrée mode voix.
3. **`AT+VGT=128`** — volume haut-parleur nominal.
4. **`AT+VSM=132,8000`** — dans l’exemple du manuel : **IMA ADPCM** 8 kHz (à adapter : **`AT+VSM=128,8000`** pour PCM 8-bit linéaire comme dans le projet).
5. **`AT+VSD=128,0`** — sensibilité nominale, **intervalle 0** → **désactive** la détection de silence (pour ne pas couper avant le message).
6. **`<DLE>R`** — le modem signale la sonnerie au DTE.
7. **`AT+VLS=1`** — **décroché**, lien vers le réseau.
8. **`AT+VTX`** → **`CONNECT`** — émission du message d’accueil ; envoi des données audio.
9. **`<DLE><ETX>`** — fin d’émission vocale.
10. **`AT+VTS=[933,0,120]`** — bip d’annotation (~1,2 s dans l’exemple : tonalités 933 Hz + durée).
11. **`AT+VSD=128,50`** — réactive silence : **50** → **5 s** avant fin présumée (selon échelle du manuel pour cet exemple).
12. **`AT+VLS=5`** — haut-parleur attaché, modem reste décroché (écoute / *call screening*).
13. **`AT+VRX`** → **`CONNECT`** — enregistrement / flux vers le DTE.
14. Données + codes DLE ; puis **`<DLE>s`** — fin de message présumée après silence.
15. **`<DLE>!`** — le DTE sort de l’état réception.
16. **`ATH`** — raccrochage ; retour mode données (`+FCLASS=0`).

## Points d’attention pour une implémentation

- **Format audio :** aligner `+VSM` sur ce que le code envoie (8-bit linéaire 8 kHz monophonique pour `modem_handler.py`).
- **`+VSD` :** basculer entre **0** (pas de coupure) pendant le prompt et une valeur **> 0** pendant l’enregistrement pour détecter la fin d’appel.
- **`+VLS` :** choisir la configuration selon que l’on veut ligne seule (`1`), écoute HP (`5`), ou autre (table en [5637-commandes-voix.md](./5637-commandes-voix.md)).
- **Fin de `+VTX` :** envoyer **DLE + ETX** comme dans le manuel et le code USR.

## Voir aussi

- [5637-dle-et-flux-serie.md](./5637-dle-et-flux-serie.md) — détail des codes DLE.
- [5637-commandes-voix.md](./5637-commandes-voix.md) — référence des commandes `+V*`.
