# USR 5631 — contrôle d’appel (dial, answer, hook)

Source : [callcontrol.htm](https://support.usr.com/support/5631/5631-ug/callcontrol.htm)

## Numérotation : `D` (Dial)

**Syntaxe** : `D<string>`

Le modem décroche, compose, tente la négociation. Comportement selon **`+FCLASS`** :

- **Données (`+FCLASS=0`)** : handshake modem données ; délais **S6** / **S7** ; annulation possible par caractère DTE avant fin de poignée de main.
- **Fax (1, 1.0, 2)** : entrée état fax (ex. réception HDLC V.21 ch.2 comme après `+FRH=3`) ; annulation si caractère reçu **avant** fin de composition.

**Note** : si **S1** (compteur de sonneries) n’a pas été remis à zéro avant `ATD`, réponse possible **NO CARRIER** (comportement documenté).

### Modificateurs de chaîne (sélection)

| Symbole | Effet |
|---------|--------|
| `0`–`9` | DTMF |
| `*`, `#` | DTMF étoile / dièse (tonal) |
| `A`–`D` | DTMF étendu (soumis aux restrictions pays) |
| `T` / `P` | Tonal / impulsionnel jusqu’au prochain `P`/`T` |
| `L` | Recomposer le **dernier** numéro valide (`DL` immédiatement après `D`) |
| `L?` | `ATDL?` — affiche le dernier numéro composé |
| `S=n` | Composer l’entrée répertoire `n` (0–3), voir `&Z` |
| `!` | Flash (durée **S29**) |
| `W` | Selon `X` : peut se comporter comme pause `,` en X0–X2 |
| `@` | Attendre silence (~5 s bande progression) ou timeout **S7** → **NO ANSWER** / **BUSY** si détection |
| `&` | Attente tonalité carte (timeout S7 US ou S6 W-class) |
| `,` | Pause (**S8**) |
| `;` | Retour **mode commande** en restant décroché ; la suite du dial exige une nouvelle commande `D` sans `;` pour entrer en suivi d’appel |
| `^` | Active/désactive tonalité d’appel (tentative courante) |
| `( )` `-` espace | Ignorés (formatage) |
| `/` | Court délai ~125 ms |
| `>` | Impulsion terre sur relais si activé par pays |

### Commandes de mode de numérotation par défaut

- **`T`** — par défaut tonal jusqu’au prochain `P` ; efface **S14** bit 5.
- **`P`** — par défaut impulsionnel ; positionne **S14** bit 5 ; peut être interdit selon pays.

## Répétition de commande

### `A>`

Répète la dernière commande toutes les **S6** secondes jusqu’à touche ; si dernière commande était tentative de connexion (`D`, `A`, `O`), équivalent **A/**.

## Réponse : `A` (Answer)

- **Données** : réponse classique ; timeout **S7** ; caractère interrompt.
- **Fax** : tonalité V.21 ~3 s puis enchaînement comme `+FTH=3` après délai ~70 ms.

## Raccrochage : `H`

| H | Action |
|---|--------|
| 0 | Raccrocher si en ligne ; arrêter test `&T` ; traitements spécifiques pays/proto hors commande |
| 1 | Si au repos : décrocher mode commande ; US : reste décroché ; W-class : retour combiné après **S7** |

## Retour mode données : `O`

`O0`…`O5` : retrain / renégociation selon valeur ; **ERROR** si pas de connexion. Valeurs 2–5 orientées **diagnostic**.

## Audio local

### `L` — volume haut-parleur

`0`–`3` ; défaut `1` ; bits dans **S22** (0–1).

### `M` — contrôle haut-parleur

`0` toujours off … `3` schéma « answer » spécifique ; bits **S22** (2–3). Voir table complète sur la page source.

### `&G` — tonalité de garde (modes DPSK)

`0`–`2` ; `2` = 1800 Hz ; peut être interdit selon pays ; bits **S23** (6–7).

## Listes et annuaire

### `*B`

Demande la liste des numéros **blacklistés** (format colonnes) ou `OK` si vide.

---

*Modulation et débits de liaison : [modulation.md](modulation.md). Interface série et CONNECT : [interface-dte.md](interface-dte.md).*
