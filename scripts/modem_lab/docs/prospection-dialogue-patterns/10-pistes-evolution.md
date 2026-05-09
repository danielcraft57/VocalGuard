# Pistes d’évolution (non implémentées)

Ce document recense des patrons ou pratiques **pertinents** pour VocalGuard / téléphonie, mentionnés en discussion de conception mais **pas** codés dans `prospection_dialogue` à ce stade. Ils servent de feuille de route ou de critères de revue.

## Saga (légère)

**Idée** : modéliser « compose → attend → joue → écoute → … » comme des **étapes** avec une **compensation** minimale si une étape échoue (ex. forcer `end_outgoing_vrx_stream` si une lecture WAV a commencé mais a échoué).

**Intérêt** : robustesse sur les lignes instables ; coût : verbosité et tests supplémentaires.

## Circuit breaker

**Idée** : si VRX ou STT échoue **N** fois de suite, arrêter les tentatives et raccrocher proprement.

**Intérêt** : éviter les boucles agressives sur matériel dégradé.

## Actor / file unique « ligne »

**Idée** : une file de messages unique pour **toutes** les actions modem (VRX, play, hangup) pour sérialiser l’accès et réduire les courses entre tâches asyncio et threads.

**Intérêt** : sûreté sur drivers série capricieux ; coût : refactor des scénarios existants.

## Registry de niveaux d’intent

**Idée** : enregistrer `niveau1`, `niveau2`, … avec métadonnées (prérequis, priorité) plutôt que de passer une longue liste de chemins en CLI.

**Intérêt** : configuration centralisée (fichier YAML/JSON de campagne).

## Specification métier avancée

**Exemples** :

- ne pas rejouer le même tag deux fois de suite ;
- après `n1_refus_poli`, n’autoriser qu’un intent « mail » ;
- combiner avec un **Specification** externe injecté dans `build_dialogue_policy(..., continue_rule=...)`.

## Export d’événements

Brancher un `subscribe` qui écrit du **NDJSON** ou envoie vers OpenTelemetry pour corréler avec les métriques modem (`metrics.csv`).

## Tests de charge / simulation

Utiliser `IntentMatcherProtocol` avec une implémentation **fake** pour simuler des conversations entières sans modem.
