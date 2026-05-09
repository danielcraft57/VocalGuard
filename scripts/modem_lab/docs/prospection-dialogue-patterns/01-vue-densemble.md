# Vue d’ensemble

## Problème métier

En **sortant** vers un correspondant, on veut :

1. Jouer une **ouverture** audio (souvent tirée au hasard parmi plusieurs variantes).
2. **Écouter** (STT Vosk) puis, si la transcription contient des formulations connues, jouer une **réponse** WAV issue d’un pack généré depuis des JSON d’intents.
3. Répéter sur **plusieurs tours** sans dépasser des limites (nombre de tours, temps total, arrêt sur certains tags comme RGPD ou au revoir).

## Solution architecturale

Le paquet `labcore/prospection_dialogue` isole tout ce qui **n’est pas** modem/Vosk :

| Besoin | Patron (famille) | Module principal |
|--------|------------------|------------------|
| Plusieurs fichiers JSON + ordre de priorité | Chaîne de responsabilité | `chain.py` |
| État de l’appel exportable / loggable | Memento (léger) | `snapshot.py` |
| Paramètres + règles d’une « campagne » | Strategy | `policy.py` |
| « Peut-on lancer le tour N ? » | Specification + Composite | `specification.py` |
| Découpler logs / métriques du cœur de boucle | Observer | `events.py` |
| Borner le temps réel | Deadline / budget | `deadline.py` |
| Tester ou remplacer le matcher sans toucher au scénario | Port (Protocol) | `ports.py` |
| Fichiers immuables par session | Value object / config | `config.py` |
| Premier WAV par tag | Service simple | `opening.py` |

## Flux simplifié (après décroché + greeting)

```text
[Policy + Deadline + Bus]
        │
        ▼
   pour chaque tour (si Specification OK)
        │
        ├──► STT (durée = min(listen_sec, temps restant deadline))
        ├──► Matcher.match(transcription)
        ├──► si match : lecture WAV + Memento.record + Observer.emit
        └──► si terminal ou pas de match : sortie
```

## Pour aller plus loin

- Détail du câblage modem : [09-integration-prospection-outbound.md](./09-integration-prospection-outbound.md)
- Idées futures (sans implémentation obligatoire) : [10-pistes-evolution.md](./10-pistes-evolution.md)
