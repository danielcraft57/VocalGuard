# Commandes vocales (V.253) — 5637 OEM

Source : *Voice Commands* et *Table 230. AT Voice Commands Summary* dans `5637-OEM.pdf`.

Le modem suit **ITU-T V.253**. Les commandes passent par le port série ; le **chemin audio** peut être soit le **port COM** (flux PCM), soit un canal DMA via **pilote wave** (Windows) — les applis « série » n’utilisent pas `+VRX`/`+VTX` lorsqu’elles passent par le driver audio.

## Entrée en mode voix

| Commande | Rôle |
|----------|------|
| `AT+FCLASS=8` | Passe en **mode voix**. Le haut-parleur mains-libres et le mode **TAD** (répondeur) sont des sous-ensembles de ce mode. |

Le contrôleur gère l’état global (contexte speakerphone vs TAD).

## Identification / sonnerie

| Commande | Rôle |
|----------|------|
| `AT+VCID=<pmode>` | Active / désactive l’affichage **caller-ID** (`0` désactivé, `1` formaté, `2` brut). |
| `AT+VDR=<enable>,<report>` | Sonnerie distinctive et **cadence** (codes `DROF` / `DRON`). |

## Niveaux et réinitialisation

| Commande | Rôle |
|----------|------|
| `AT+VGM=<gain>` | Gain **micro** mains-libres (0–255, 128 = nominal). |
| `AT+VGR=<gain>` | Gain **réception** (plage significative 121–134 selon manuel ; en TAD, enregistrement local micro). |
| `AT+VGS=<gain>` | Gain **haut-parleur** mains-libres. |
| `AT+VGT=<level>` | **Volume** haut-parleur (0–255). |
| `AT+VIP` | Réinitialise les **paramètres vocaux** aux défauts (sans changer `+FCLASS`). |
| `AT+VIT=<timer>` | Timer d’**inactivité** DTE/DCE en mode voix fixe (secondes, 0–255). |

## Discrimination d’appel

| Commande | Rôle |
|----------|------|
| `AT+VNH=<hook>` | Raccrochage automatique en modes **données/fax** : `0` comportement normal, `2` pas de raccrochage auto DCE (hangup « logique » côté DTE). |

## Sélection analogique `+VLS` (essentiel)

`AT+VLS=<label>` attache les sources / destinations analogiques en mode voix.

### Valeurs speakerphone (extrait)

| Valeur | Fonction |
|--------|----------|
| `0` | Mains-libres off |
| `5` | Détache le micro (sourdine téléphone) |
| `7` | Mains-libres on — HP + micro, **décroché** |

### Configurations générales (TAD / ligne)

| # | Description |
|---|-------------|
| 0 | DCE **en ligne**, téléphone local relié au réseau |
| 1 | DCE **décroché**, DCE relié au réseau |
| 2 | DCE décroché, téléphone local au DCE |
| 3 | DCE décroché, téléphone au réseau, DCE vers téléphone local |
| 4 | Haut-parleur au DCE, **en ligne** (lecture messages) |
| 5 | Haut-parleur au DCE, **décroché** (écoute d’appel) |
| 6 | Micro au DCE, **en ligne** (enregistrement message d’accueil) |
| 7 | Micro + HP, décroché (mains-libres) |

**Lecture capacités :** `AT+VLS=?` — rapporte configurations et codes d’événements pour speakerphone / répondeur.

**Note projet :** le code VocalGuard utilise typiquement **`AT+VLS=1`** pour être décroché sur la ligne avant émission audio (`modem_handler.py`).

## Débit interface

| Commande | Rôle |
|----------|------|
| `AT+VPR=<rate>` | Sur ce produit, renvoie **OK** mais **sans effet** (selon manuel). |

## Timers sonnerie (origination)

| Commande | Rôle |
|----------|------|
| `AT+VRA=<interval>` | Timer « sonnerie partie » (défaut 50, pas de 0,1 s). |
| `AT+VRN=<interval>` | Timer « sonnerie jamais apparue » (défaut 10, pas 1 s). |

## Compression et échantillonnage `+VSM`

`AT+VSM=<cml>,<vsr>` — méthode de compression + fréquence d’échantillonnage.

**Valeurs `<cml>` (méthode) :**

| `<cml>` | Méthode | Fréquences `<vsr>` supportées (manuel) |
|---------|---------|----------------------------------------|
| 128 | Linéaire 8 bits | 7200, **8000**, 11025 |
| 129 | Linéaire 16 bits (défaut fabricant) | 7200, **8000** (défaut), 11025 |
| 130 | A-law 8 bits | 8000 |
| 131 | μ-law 8 bits | 8000 |
| 132 | IMA ADPCM | 8000 |
| 133 | G.729 | 8000 |

**Lecture :** `AT+VSM?` ; **capacités :** `AT+VSM=?` (défaut rapporté **129,8000** — 16-bit linéaire 8 kHz).

**Lien projet :** pour le flux PCM 8-bit 8 kHz linéaire (callattendant / VocalGuard), le manuel autorise **`AT+VSM=128,8000`**.

## Détection de silence `+VSD`

`AT+VSD=<sds>,<sdi>` :

- **`<sds>`** : sensibilité « silence » (dB, échelle centrée sur **128** = nominal ≈ −40 dBm ; >128 plus agressif, <128 moins).
- **`<sdi>`** : durée avant de signaler le silence (défaut **50** = **5 s** dans le tableau ; incrément décrit dans le manuel pour fin d’enregistrement / raccroché présumé).

Plage OK : `0–255` pour les deux paramètres.

**Lien projet :** **`AT+VSD=128,0`** est utilisé côté USR pour **désactiver** la détection de silence dans certains scénarios (cf. exemples TAD du manuel et `modem_handler.py`).

## Mains-libres `+VSP`

| Valeur | Effet |
|--------|--------|
| 0 | Mains-libres off (défaut) |
| 1 | Mains-libres on |

## Durée tonalités `+VTD`

`AT+VTD=<dur>` — durée par défaut des DTMF / bips (incrément **0,01 s**), plage **0–400**.

## Full duplex `+VTR`

`AT+VTR` — démarre émission/réception **full duplex** ; le DCE choisit source/puits via `+VLS`. **CONNECT** si OK. Pas d’obligation d’annulation d’écho côté modem.

## Génération DTMF / tonalités `+VTS`

`AT+VTS=<string>` — séquence de tonalités ; éléments séparés par des virgules. Inclut chiffres DTMF, `!` (*hook flash*), groupes `[]` (dual tone + durée), `{}` (durée explicite). Détails en **V.253 § 10.1.5.1.1** (référence manuel).

## Émission / réception de parole sur le port série

| Commande | Rôle |
|----------|------|
| `AT+VTX` | **Émission** : flux vocal envoyé au modem via le port ; réponse **CONNECT**. |
| `AT+VRX` | **Réception** : flux reçu du modem via le port ; réponse **CONNECT**. |

Sortie de ces états : voir [5637-dle-et-flux-serie.md](./5637-dle-et-flux-serie.md).

## Table récapitulative (manuel)

Le PDF liste toutes les commandes `+V*` en **Table 230** (page « Command Reference - 121 » du guide) avec renvois V.253 / IS-101.
