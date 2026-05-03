# Conventions AT — rappel (V.250)

Source : section *Command Reference* du PDF `5637-OEM.pdf`.

## Portée

Le jeu de commandes US Robotics pour modems « controller-based » couvre :

- **Données :** ITU-T **V.250** (05/99) pour une grande partie des extensions courantes.
- **Fax :** classes 1 / 2 selon **T.31** / **T.32**.
- **Voix :** **V.253** (02/98) — voir [5637-commandes-voix.md](./5637-commandes-voix.md).

Certaines commandes sont **propriétaires** ou réservées au debug ; un modem donné peut ne pas implémenter tout le manuel (cf. fiche produit).

## Syntaxe de base

`<commande>[<paramètre>]` — paramètre décimal optionnel selon la commande.

## Syntaxe étendue (`+...`)

Trois formes usuelles :

- Sans paramètre : `+<nom>`
- Un paramètre : `+<nom>[=<paramètre>]`
- Plusieurs : `+<nom>[=<p1>][,<p2>]`

**Lecture / test** (interrogation du modem) :

- `+<nom>?` — valeur courante.
- `+<nom>=?` — plages ou valeurs supportées.

## Résultats (DCE → DTE)

Pour chaque ligne de commande, le modem renvoie au moins un **code résultat** ; les plus fréquents sont **`OK`** et **`ERROR`**. Les conditions exactes sont détaillées commande par commande dans le PDF.

## Suite

Pour la téléphonie applicative (décroché, audio série, DTMF), enchaîner avec :

- [5637-commandes-voix.md](./5637-commandes-voix.md)
- [5637-dle-et-flux-serie.md](./5637-dle-et-flux-serie.md)
