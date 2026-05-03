# USR 5631 — commandes génériques et profils

Source : [generic.htm](https://support.usr.com/support/5631/5631-ug/generic.htm)

## Conventions de la section « Data Command Set »

- Les valeurs par défaut indiquées correspondent au **profil usine 0** sauf mention contraire.
- Les commandes **étendues** (+…) suivent en général V.250 : `=?` (plage), `?` (valeur courante).

## Reset et profils

### `Z` — soft reset et restauration de profil

- **Syntaxe** : `Z<value>`
- **Valeurs** : `0` → reset + profil stocké 0 ; `1` → reset + profil stocké 1.
- **Résultats** : `OK` si valeur 0 ou 1, sinon `ERROR`.

> Le chapitre *DTE Interface* du même guide décrit une variante étendue de `Z` avec davantage d’options de profil au démarrage ; en cas d’écart, se référer aux deux sections ou tester sur le modem.

### `&F` — recharger la configuration usine

- **Syntaxe** : `&F[<value>]`
- **Profils usine** : `0`, `1`, `2`.
- **Contrainte** : `ERROR` si le modem est **connecté**.

### `&W` — sauver la configuration active en NVRAM

- **Syntaxe** : `&W<value>` avec `value` ∈ {0, 1} (profil utilisateur 0 ou 1).
- Échoue si NVRAM absente ou défaillante.

### `Y` — profil au démarrage (voir aussi interface DTE)

La sélection du profil au **power-up** est documentée en détail dans [interface-dte.md](interface-dte.md) (`Y<value>`).

## Classe de service active

### `+FCLASS` — mode données, fax ou voix

- **Syntaxe** : `+FCLASS=<mode>`
- **Modes usuels** :
  - `0` — données (section Data du guide)
  - `1` / `1.0` — fax classe 1 / 1.0
  - `2` — fax classe 2
  - `8` — **voix** (section Voice du guide complet)
  - `10` — réservé
- **Interrogation** : `+FCLASS?`, plage : `+FCLASS=?`

Pour le lab **répondeur / annonce**, l’alignement avec `+FCLASS=8` et les commandes voix du 5637 est l’objectif fonctionnel ; les détails voix ne sont pas tous dans `generic.htm`.

## Identification et capacités

### `I` — informations produit

Paramètre numérique ; exemples documentés :

| Valeur | Rôle |
|--------|------|
| 0 | Code produit |
| 1 | Checksum ROM |
| 2 | Test RAM |
| 3 | ID + version (texte) |
| 4 | Réglages courants (dump) |
| 5 | Réglages NVRAM / modèles |
| 6 | Diagnostics synthèse **dernier appel** |
| 7 | Configuration matérielle (options, horloge, révisions) |

### `+GCAP` — liste des familles de commandes étendues

Réponse typique listant des capacités : `+FCLASS`, `+MS`, `+ES`, `+DS`, etc. Utile pour **détecter** au runtime ce que le firmware expose.

## Pays et réglementation

### `+GCI` — pays d’exploitation (T.35)

- **Syntaxe** : `+GCI=<country_code>` (hex 8 bits, bit 8 = MSB).
- **Défaut usine** documenté : **F6** (TBR-21).
- **Exemple** : `+GCI: 3D` → France (`+GCI?`).

## Caller ID (si ligne et pays le permettent)

### `+VCID` — activer le rapport CID pour l’appel suivant

- `0` — désactivé (défaut)
- `1` — activé, présentation formatée `<Tag><Value>` (date, heure, nom, numéro attendus)
- `2` — activé, non formaté

### `+VRID` — lire le CID de **la dernière** réception

- `0` / `1` — formaté / non formaté

## Options de rapport et stockage de numéros

### `&A` — suffixe `/ARQ` sur CONNECT (modes X1–X6)

- `0` — pas de suffixe protocole
- `1` — ajoute `/ARQ` quand applicable (défaut)

### `&Z` — chaînes de numérotation en NVM

- **Écriture** : `&Z<n>=<dial string>` avec `n` ∈ {0,1,2,3}
- **Rappel dernier numéro** : `&Zn=L`
- **Lecture** : `&Zn?`, `&ZL?` (dernier composé)

### `*B` — liste des numéros « blacklistés » (selon pays)

Réponse texte structurée ou simple `OK` si liste vide.

## Tests

### `&T` — boucle analogique locale (V.54 loop 3)

- `0` — arrêt test, clear **S16**
- `1` — démarrage loopback ; impose mode **non correction d’erreur** (ex. `AT&Q6` selon doc)
- Nécessite séquence d’échappement pour sortir si besoin.

---

*Pour le contrôle DTR/DCD, echo, résultats étendus et flux DTE ↔ modem, voir [interface-dte.md](interface-dte.md). Pour D/A/H et modificateurs de dial, voir [controle-appel.md](controle-appel.md).*
