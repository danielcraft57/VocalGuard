# USR 5631 — index des registres S

Source : [scommands.htm](https://support.usr.com/support/5631/5631-ug/scommands.htm)

Ce fichier liste les **registres S nommés** dans le guide 5631. Les **valeurs par défaut**, **unités**, **bits** et **interdépendances** (avec `&M`, `+ES`, etc.) sont sur la page officielle — trop longues pour une copie exhaustive ici.

## Liste (ordre documentaire)

| Registre | Titre (manuel USR 5631) |
|----------|-------------------------|
| S0 | Number of Rings to Auto-Answer |
| S1 | Ring Counter |
| S2 | Escape Character |
| S3 | Carriage Return Character |
| S4 | Line Feed Character |
| S5 | Backspace Character |
| S6 | Wait Time before Blind Dialing or for Dial Tone |
| S7 | Wait Time for Carrier, Silence, or Dial Tone |
| S8 | Pause Time For Dial Delay |
| S9 | Carrier Detect Response Time |
| S10 | Lost Carrier To Hang Up Delay |
| S11 | DTMF Tone Duration |
| S12 | Escape Prompt Delay (EPD) |
| S14 | General Bit Mapped Options Status |
| S16 | Test Mode Bit Mapped Options Status |
| S19 | Reserved |
| S20 | Reserved |
| S21 | V.24/General Bit Mapped Options Status |
| S22 | Speaker/Results Bit Mapped Options Status |
| S23 | General Bit Mapped Options Status |
| S24 | Sleep Inactivity Timer |
| S25 | Delay To DTR Off |
| S26 | RTS to CTS Delay |
| S27 | Bit mapped register |
| S28 | Bit Mapped Options Status |
| S29 | Flash Dial Modifier Time |
| S30 | Disconnect Inactivity Timer |
| S31 | Bit Mapped Options Status |
| S32 | Bit mapped register |
| S36 | LAPM Failure Control |
| S38 | Delay Before Forced Hang Up |
| S39 | Flow Control Bit Mapped Options Status |
| S40 | General Bit Mapped Options Status |
| S46 | Data Compression Control |
| S48 | V.42 Negotiation Control |
| S86 | Call Failure Reason Code |
| S91 | PSTN Transmit Attenuation Level |
| S92 | Fax Transmit Attenuation Level |
| S95 | Extended Result Codes Control |
| S210 | V.34 Symbol Rates |

## Croisement rapide lab

- **S0 / S1 / S6 / S7** : répondeur, délais dial et porteuse — voir aussi [controle-appel.md](controle-appel.md).
- **S2 / S12** : échappement `+++` — aligner avec votre doc flux série [5637-dle-et-flux-serie.md](5637-dle-et-flux-serie.md) si vous travaillez sur le 5637.
- **S14 / S21 / S22 / S23 / S31 / S39 / S40** : bits liés aux commandes `E`, `Q`, `V`, `&C`, `&D`, `L`, `M`, `W`, `X`, compression, MNP étendu.
- **S86** : code **échec d’appel** (lecture après échec — utile pour scripts).
- **S95** : masque des rapports intermédiaires (+MR, +ER, +DR, etc.) avec **`W`**.

## Doc interne 5637

Le dépôt contient déjà une description détaillée orientée **5637** : [5637-registres-s.md](5637-registres-s.md). Comparez les numéros et bitfields avant de supposer l’identité stricte entre 5631 et 5637.

---

[Index général 5631](usr-guide-index.md)
