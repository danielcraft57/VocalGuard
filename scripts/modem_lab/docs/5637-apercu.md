# Aperçu — US Robotics 56K USB Modem (5637 OEM)

Source : *56K USB Modem User Guide* (PDF local `5637-OEM.pdf`).

## Identification

- **Produit :** modem USB 56K « controller-based » (traitement dans le modem, pas seulement dans le PC).
- **Révision document :** R46.1999.00, rev 1 (05/2008).
- **Standards données notables :** V.92 (amont PCM, *Modem on Hold*, etc.), rétrocompatibilité V.90.

## Fonctions V.92 rappelées par le manuel

- **V.PCM-Upstream :** débit amont accru lorsque le fournisseur le supporte.
- **Modem on Hold :** mise en attente d’appel (nécessite ligne et abonnement compatibles).
- **Quick Connect :** reconnexion plus rapide si le serveur le permet.

## Prérequis matériels / logiciels (extrait)

- **OS (selon manuel) :** Windows Vista / XP / 2000, **Linux noyau ≥ 2.4.20**, Mac OS X ≥ 10.4.3.
- **Matériel :** port USB libre, ligne téléphonique **analogique** 56K compatible, adaptateur pays si besoin.
- **Attention :** ne pas raccorder à une ligne **numérique** (risque d’endommagement) — précaution rappelée pour les installations professionnelles.

## LED

| LED | État | Signification |
|-----|------|----------------|
| PWR | Allumée fixe | Alimentation OK, pilote correctement installé |
| PWR | Éteinte | Pas d’alimentation |
| DATA | Clignotante | Modem actif |
| DATA | Fixe | Signal données valide d’un modem distant (transmission possible), ou CD forcé (`&C0`) |
| DATA | Éteinte | Modem inactif |

## Installation — Linux (CDC ACM)

Le manuel indique qu’avec un noyau **2.4.20 ou supérieur**, le pilote **USB CDC ACM** (noyau ou module) suffit : branchement **Plug and Play**, **sans** installation depuis le CD USR, si le support PnP est actif (défaut).

En pratique sur les noyaux récents, le modem apparaît souvent en **`/dev/ttyACM*`** (ou équivalent selon distribution).

## Raccordement ligne

- Cordon RJ-11 fourni entre la prise **téléphone** du modem et la prise murale analogique.
- Pour partager ligne téléphone + modem (ex. *Modem on Hold*), utiliser un **répartiteur** sur la prise murale.

## Référence commandes AT

Le manuel regroupe les commandes **données** (V.250), **fax** (T.31/T.32) et **voix** (**V.253**). Pour VocalGuard / modem_lab, la suite utile est surtout la **classe vocale** : voir [5637-commandes-voix.md](./5637-commandes-voix.md).
