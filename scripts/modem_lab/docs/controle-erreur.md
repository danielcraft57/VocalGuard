# USR 5631 — contrôle d’erreur (LAPM, MNP, modes spéciaux)

Source : [errorcontrol.htm](https://support.usr.com/support/5631/5631-ug/errorcontrol.htm)

## `+ES` — mode demandé et repli (originateur / answerer)

**Syntaxe** :

```text
+ES=[<orig_rqst>[,<orig_fbk>[,<ans_fbk>]]]
```

### `orig_rqst` — comportement **appelant**

| Valeur | Signification |
|--------|----------------|
| 0 | Direct mode |
| 1 | Normal (buffered) seulement |
| 2 | V.42 **sans** phase de détection |
| 3 | V.42 **avec** phase de détection (défaut) |
| 4 | MNP |
| 6 | **V.80** synchronous access à l’entrée en état données (voir `+ESA`, `+ITF`) |
| 7 | Frame tunneling à l’entrée en données |

### `orig_fbk` — repli **appelant**

| Valeur | Repli |
|--------|--------|
| 0 | LAPM, MNP ou normal optionnels (défaut) |
| 1 | LAPM, MNP ou **direct** optionnels |
| 2 | LAPM ou MNP **requis** |
| 3 | LAPM seul **requis** |
| 4 | MNP seul **requis** |

### `ans_fbk` — repli / mode **répondeur**

| Valeur | Signification |
|--------|----------------|
| 0 | Direct |
| 1 | Sans correction, normal |
| 2 | LAPM, MNP ou normal optionnels (défaut) |
| 3 | LAPM, MNP ou direct optionnels |
| 4–6 | Exiger LAPM/MNP (variantes) |
| 8 | V.80 synchronous access côté réponse |
| 9 | Frame tunneling côté réponse |

Exemples documentés : `+ES=6`, `+ES=,,8`, `+ES=6,,8`, `+ES=3,,2`, etc.

### Interrogation

- `+ES?` → `+ES:<orig_rqst>,<orig_fbk>,<ans_fbk>`
- `+ES=?` → plages (avec 6, 7, 8, 9 selon support)

## `+ER` — rapport du type de correction négocié

- `0` — pas de `+ER:` (défaut) ; `1` — activer.
- **S95** bit 3 ; interaction avec **`W`**.

### Code `+ER:<type>`

| type | Protocole |
|------|-----------|
| NONE | Aucune correction |
| LAPM | V.42 LAPM |
| ALT | MNP |

Émis **après** `+MCR`/`+MRR` et **avant** `+DR` (compression).

## Break et options associées

### `\B` — envoyer break au distant

- En mode **sans** correction : durée = N × 100 ms, N ∈ 1–9 (défaut 3), lié à `\K`.
- En mode **avec** correction : signal break via protocole ; longueur ignorée côté durée.

Résultats : `OK` si mode données approprié ; `NO CARRIER` si non connecté ou fax.

### `&Y` — traitement du break

| &Y | Option |
|----|--------|
| 0 | Destructif |
| 1 | Destructif expédié |
| 2 | Non destructif expédié |
| 3 | Réservé |

## `-K` — extension MNP (LAPM → MNP10)

Valeurs 0–2 ; bits **S40** (0–1) : conversion V.42 LAPM vers MNP 10, avec variante inhibant l’init MNP en phase détection réponse.

---

*Compression données (+DS) est dans le chapitre *datacompression.htm* du guide (non détaillé ici). Flux DTE : [interface-dte.md](interface-dte.md).*
