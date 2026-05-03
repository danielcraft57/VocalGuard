# USR 5631 — V.92 et commandes `+P` (PCM DCE)

Source : [v92.htm](https://support.usr.com/support/5631/5631-ug/v92.htm)

Prérequis : modulation **V.92** sélectionnable via **`+MS`** (voir [modulation.md](modulation.md)). Sans pair V.92, plusieurs fonctions retombent en **refus** ou **ERROR**.

## `+PCW` — sonnerie en attente (Call Waiting)

| Valeur | Comportement |
|--------|----------------|
| 0 | Si **+PMH** / **+VRID** actifs : comportement MOH + collecte CID ; bascule circuit V.24 **125** (défaut) |
| 1 | Raccrocher |
| 2 | Ignorer l’événement call waiting |

`+PCW?`, `+PCW=?` documentés.

## `+PMH` — modem-on-hold (MOH)

| Valeur | Effet |
|--------|--------|
| 0 | MOH **activé** en mode V.92 (défaut) |
| 1 | MOH **désactivé** |

## `+PMHT` — accepter ou refuser la demande MOH + temporisation

| Valeur | Signification |
|--------|-----------------|
| 0 | **Refuser** la demande MOH V.92 (défaut) |
| 1–12 | Accepter avec timeout 10 s … 16 min (échelons documentés) |
| 13 | Timeout **indéfini** |

## `+PMHR` — initier ou confirmer une procédure MOH

Commande sans paramètre. Réponse **`+PMHR:<value>`** où `value` est le **niveau de timeout accordé** (0 = refusé ou indisponible, 1–13 = mêmes échelles que **+PMHT**). Peut être **différée** selon contexte.

Si le serveur distant n’est pas V.92, le modem peut toujours rapporter **`0`** (refus).

## `+PIG` — négociation **PCM upstream**

| Valeur | Effet |
|--------|--------|
| 0 | Activer la négociation PCM amont |
| 1 | Désactiver (défaut) |

> La page source contient une coquille sur l’exemple `+PIG=?` (`+PCW:`) ; se fier aux titres de commande.

## `+PMHF` — flash hook pendant MOH

Déclenche la séquence de **flash** pour basculer vers le second appel (entrant ou sortant).  
`OK` si séquence terminée ; `ERROR` si pas en état « on hold ».

## `+PQC` — phases courtes V.92 (phase 1 et 2)

| Valeur | Effet |
|--------|--------|
| 0 | Phases 1 et 2 **courtes** activées (défaut) |
| 1 | Phase 1 courte seulement |
| 2 | Non supporté |
| 3 | Phases courtes **désactivées** |

## `+PSS` — forcer séquence courte / pleine au prochain appel

| Valeur | Effet |
|--------|--------|
| 0 | Les modems décident ; séquence courte seulement si **+PQC** l’autorise (défaut) |
| 1 | Réservé |
| 2 | **Forcer** la séquence **complète** aux connexions suivantes, **indépendamment** de **+PQC** |

---

*Diagnostics détaillés post-appel : [diagnostic-et-ud.md](diagnostic-et-ud.md).*
