# USR 5631 — diagnostics et rapport `#UD`

Source : [diagnostic.htm](https://support.usr.com/support/5631/5631-ug/diagnostic.htm)

## Rôle de `#UD`

`#UD` est une **commande d’action** sans paramètre : elle doit être la **dernière** de la ligne. Elle retourne un ou plusieurs lignes de texte au format **V.250**, puis un **`OK`**.

Le modem conserve un **journal** par appel jusqu’à effacement par :

- coupure alimentation ;
- reset matériel (ex. DTR avec `&D3`, bouton) ;
- **soft reset** `ATZ` ou `AT&F` ;
- **`ATD`** ou **`ATA`** ;
- **réponse automatique** (ex. **S0** > 0 et sonnerie).

> Changer **DTR** avec `&D0`, `&D1` ou `&D2` **ne** vide **pas** le log (selon la doc).

## Modèle d’états (appel données)

1. **Call setup** — tonalité, numérotation, progression, sonnerie, CID…
2. **Negotiation** — V.25, V.8/V.8bis, porteuses, V.42, etc.
3. **Data transfer** — BER, renégociation, retrain…
4. **Termination** — déconnexion, perte porteuse, erreurs excessives…

## Format de ligne

Chaque ligne ressemble à :

```text
DIAG <token key=value [key=value ...]>
```

- **`DIAG`** : 5 octets ASCII fixes.
- **`token`** : identifiant 32 bits en **hex** (ex. `2A4D3263` dans les exemples).
- Paires **`clé=valeur`** : clés en **hex** 1–2 chiffres ; valeurs souvent **hex** (MSD first, zéros non significatifs omis), alignées sur tables **ITU V.58** quand applicable.

## Clés principales (aperçu)

| Clé | Contenu (résumé) |
|-----|-------------------|
| 0 | Révision spec diagnostic (digit.digit) |
| 1 | Résultat setup d’appel (table 3-4) |
| 2 | Mode multimédia (3-5) |
| 3 | Mode interface DTE-DCE (3-6) |
| 4–5 | Chaînes octets V.8 CM / JM (quoted) |
| 10–12 | Niveaux RX / TX / bruit (−dBm) |
| 17 | Aller-retour (ms) |
| 18 | Bitmap INFO V.34 |
| 20–27 | Négociation porteuse, symboles, fréquences, débits initiaux |
| 30–35 | Événements porteuse, renégociation, retrain, débits finaux |
| 40–44 | Protocole erreur, compression, compteurs |
| 50–51 | Flux TX/RX (off, DC1/DC3, circuits 106/133) |
| 52–59 | Octets / trames I / erreurs trames |
| 60 | **Cause de fin d’appel** (table 3-11) |
| 61 | Événements appel en attente |

### Exemples de **cause de fin** (clé 60, hex)

Quelques codes documentés : `51` DTE hangup (`ATH`), `3C` perte porteuse, `3D` échec training, `42` fax détecté hors contexte fax, `50` annulation touche, etc. La table complète est sur la page source.

### Setup résultat (clé 1)

Exemples : pas de tonalité, busy, réponse données (`7`), fax (`9`/`A`), signal V.8bis (`B`), etc.

## Usage pendant une connexion

Prévu surtout **après** fin d’appel, mais certaines valeurs (ex. clé **60** = appel encore actif) permettent un **surveillance** en ligne : passer en commande en ligne, envoyer `#UD`, puis `ATO` selon doc ; pour du suivi fluide, méthodes **V.80** in-band si disponibles.

## Exemples de réponses (guide)

Le manuel montre des lignes du type :

- `DIAG <2A4D3263 1=06 2=0 3=0>` — signal réponse données, mode données async ;
- paires niveaux `10=… 11=… 12=…` ;
- négociation V.34 / V.90 sur clés 20–21, 22–27 ;
- compteurs trames 56–59 ;
- `60=51` — raccrochage initié par le PC.

---

*Identification rapide dernier appel sans parser `#UD` : commande **`I6`** (section generic). Voir [commandes-generiques-et-profil.md](commandes-generiques-et-profil.md).*
