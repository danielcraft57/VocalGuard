# Documentation US Robotics 5637 OEM (56K USB Modem)

Ce dossier regroupe des **notes structurées** dérivées du manuel constructeur. Elles ne remplacent pas le PDF officiel ; en cas de doute, se référer à la source.

| Ressource | Description |
|-----------|-------------|
| [guide-capacites-modem-56k-complet.md](./guide-capacites-modem-56k-complet.md) | **Vue d’ensemble** : données/Internet, fax, voix, répondeur, téléphonie, V.92, diagnostics ; **§12** cartographie `modem_lab` / `backend` ; **§13** décroché distant (DLE, `remote_pickup_likely`) et volume (PCM) |
| [5637-OEM.pdf](./5637-OEM.pdf) | *User Guide* complet (R46.1999.00, rev 1, 05/2008 — copyright 2005 U.S. Robotics) |
| [5637-apercu.md](./5637-apercu.md) | Identité du produit, prérequis, LED, installation (dont Linux CDC ACM) |
| [5637-conventions-at.md](./5637-conventions-at.md) | Cadre V.250 / syntaxe AT étendue (rappel) |
| [5637-commandes-voix.md](./5637-commandes-voix.md) | Commandes vocales V.253 : `+FCLASS=8`, `+VLS`, `+VSM`, `+VTS`, etc. |
| [5637-dle-et-flux-serie.md](./5637-dle-et-flux-serie.md) | Codes DLE, `+VTX` / `+VRX`, fin de flux, silence |
| [5637-registres-s.md](./5637-registres-s.md) | Registres S utiles téléphonie / voix |
| [5637-scenarios-repondeur.md](./5637-scenarios-repondeur.md) | Séquences type TAD (répondeur) tirées du manuel |

**Téléchargement officiel :** [5637-OEM.pdf sur support.usr.com](https://support.usr.com/support/5637-oem/5637-oem-files/5637-OEM.pdf)

**Lien projet :** le code applicatif qui pilote ce modem (mode voix série) est notamment dans `backend/core/modem_handler.py` et les scénarios sous `scripts/modem_lab/`.

## Modem lab — patterns « dialogue prospection »

Documentation dédiée (GoF / hexagonal appliqués au scénario `prospection-outbound` et au paquet `labcore/prospection_dialogue`) :

| Ressource | Description |
|-----------|-------------|
| [prospection-dialogue-patterns/README.md](./prospection-dialogue-patterns/README.md) | **Index** : chaîne de responsabilité, memento, strategy, specification, observer, deadline, ports, intégration CLI |

## Référence USR 5631 (guide en ligne)

Synthèse du *56K Faxmodem User's Guide* (pages `5631-ug`) : [usr-guide-index.md](./usr-guide-index.md) — commandes génériques, DTE, appel, modulation, erreur, diagnostic `#UD`, V.92 `+P`, index des registres S.
