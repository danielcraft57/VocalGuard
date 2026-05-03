# Guide USR 5631 — index de référence (modem_lab)

Ce dossier regroupe une **synthèse architecturée** des chapitres « Data Command Set » du *56K Faxmodem User's Guide and Reference* publié pour la famille **USR 5631**. Les pages officielles sont la source de vérité ; les fichiers ci-dessous servent de **carte de lecture** et d’**aide-mémoire** pour le code du lab (scénarios voix, Hayes/AT, diagnostics).

## Sources officielles (même ordre que le manuel)

| Thème | URL |
|--------|-----|
| Commandes génériques | https://support.usr.com/support/5631/5631-ug/generic.htm |
| Interface DTE | https://support.usr.com/support/5631/5631-ug/dtemodem.htm |
| Contrôle d’appel | https://support.usr.com/support/5631/5631-ug/callcontrol.htm |
| Modulation | https://support.usr.com/support/5631/5631-ug/modulation.htm |
| Contrôle d’erreur | https://support.usr.com/support/5631/5631-ug/errorcontrol.htm |
| Diagnostic | https://support.usr.com/support/5631/5631-ug/diagnostic.htm |
| V.92 (+P) | https://support.usr.com/support/5631/5631-ug/v92.htm |
| Registres S | https://support.usr.com/support/5631/5631-ug/scommands.htm |

## Carte des documents locaux

| Fichier | Contenu |
|---------|---------|
| [commandes-generiques-et-profil.md](commandes-generiques-et-profil.md) | Reset, classes de service (+FCLASS), CID, identification, pays, NVRAM, tests locaux |
| [interface-dte.md](interface-dte.md) | Echo, résultats, flux, compression locale, débit fixe DTE (+IPR), +IFC, +ILRR |
| [controle-appel.md](controle-appel.md) | Numérotation (D), tonalité/pulse, réponse, raccrochage, haut-parleur, listes noires |
| [modulation.md](modulation.md) | +MS / +MR, codes +MCR / +MRR, Bell vs CCITT (B) |
| [controle-erreur.md](controle-erreur.md) | +ES / +ER, break, options &Y, MNP étendu (-K) |
| [diagnostic-et-ud.md](diagnostic-et-ud.md) | Commande **#UD**, format DIAG, clés V.58 / états d’appel |
| [v92-p-commands.md](v92-p-commands.md) | Modem-on-hold, PCM amont, phases courtes (+PQC / +PSS), sonnerie en attente (+PCW) |
| [registres-s-index.md](registres-s-index.md) | Liste indexée des registres S documentés (renvoi vers la page complète) |

## Rappels transverses (syntaxe AT)

- Préfixe **AT** obligatoire pour toutes les commandes sauf **A/** et la séquence d’échappement **+++** (voir le chapitre *syntax* du guide complet).
- Longueur max d’une ligne de commande : **58 caractères** utiles (sans compter `AT`, CR/LF ni espaces).
- Casse : tout en majuscules ou tout en minuscules, pas un mélange.
- Paramètre numérique omis : souvent interprété comme **0** (ex. `ATB` → `ATB0`).

## Lien avec la doc modem 5637 du dépôt

Les fichiers `5637-*.md` décrivent le matériel et les conventions du lab autour du **5637**. Ces fiches couvrent la **terminologie Hayes étendue** telle qu’USR la documente pour le **5631** : beaucoup de commandes sont communes à d’autres modems USR, mais les **valeurs par défaut**, **plages** et **jeux de registres** peuvent différer. En cas de doute, valider sur l’équipement avec `ATI4` / `AT&V` et les requêtes `=?`.
