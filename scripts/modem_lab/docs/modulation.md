# USR 5631 — contrôle de modulation

Source : [modulation.htm](https://support.usr.com/support/5631/5631-ug/modulation.htm)

## `+MS` — sélection de modulation (6 sous-paramètres)

**Syntaxe** :

```text
+MS=[<carrier>[,<automode>[,<min_tx_rate>[,<max_tx_rate>[,<min_rx_rate>[,<max_rx_rate>]]]]]]
```

### Porteuses `<carrier>` (extraits de la table 3-2)

| Code | Modulation |
|------|------------|
| B103 / B212 | Bell 103 / 212 |
| V21, V22, V22B, V23C | ITU-T V série |
| V32, V32B | V.32 / V.32bis |
| V34 | V.34 |
| K56 | K56flex |
| V90 | V.90 |
| V92 | V.92 (amont / aval selon négociation) |

Certaines combinaisons **K56** vs **V92** dépendent du modèle exact.

### Sous-paramètres

- **`automode`** : `0` désactivé, `1` activé (défaut) — négociation automatique (V.8, annexes, etc.).
- **`min_*` / `max_*`** : bornes **débit** en bit/s pour TX et RX ; par défaut min = plus bas supporté, max = plus haut pour la porteuse choisie.
- Débits possibles par porteuse : voir la **table complète** sur la page source (V.90/V.92 listent de nombreux paliers).

### Interrogation

- `+MS?` → ligne `+MS:` avec valeurs courantes.
- `+MS=?` → plages supportées (exemples documentés avec ou sans K56 selon firmware).

## `+MR` — rapport de modulation pendant la négociation

| Valeur | Effet |
|--------|--------|
| 0 | Pas de `+MCR` / `+MRR` (défaut) |
| 1 | Rapport avec débits TX et RX |
| 2 | Rapport avec débit RX seulement |

Interaction avec **S95** bit 2 et commande **`W`** (voir interface DTE).

### Formes de réponse

- `+MCR: <carrier>` — codes B103, V34, V90, V92, etc.
- `+MRR: <tx_rate>, <rx_rate>` — débits en bit/s.

Ordre d’émission : **avant** les rapports correction/compression et le **CONNECT** final.

## `B` — Bell vs CCITT à 300 / 1200 bit/s

- `0` — CCITT en phase établissement et connexion à 300 ou 1200 bps (défaut).
- `1` — Bell dans les mêmes conditions.

Bit associé : **S27** bit 6.

---

*Couche erreur et compression modem-modem : [controle-erreur.md](controle-erreur.md). Choix V.92 et mise en attente : [v92-p-commands.md](v92-p-commands.md).*
