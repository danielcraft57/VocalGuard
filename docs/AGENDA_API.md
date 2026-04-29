# API Agenda

Cette documentation couvre les endpoints agenda exposés sous `"/api/v1/agenda"`.

## Endpoints principaux

- `GET /api/v1/agenda` : liste des événements agenda
- `POST /api/v1/agenda` : création d'un événement
- `PATCH /api/v1/agenda/{id}` : mise à jour partielle
- `DELETE /api/v1/agenda/{id}` : suppression

## Paramètres agenda

- `GET /api/v1/agenda/settings` : lecture des réglages
- `PUT /api/v1/agenda/settings` : mise à jour des réglages

Réglages disponibles:

- `timezone` (par défaut `Europe/Paris`)
- `work_day_start` / `work_day_end`
- `slot_minutes`
- activation des jours `monday_enabled` ... `sunday_enabled`

## Jours non travaillés

- `GET /api/v1/agenda/non-working-days`
- `POST /api/v1/agenda/non-working-days`
- `DELETE /api/v1/agenda/non-working-days/{id}`

## Contexte agenda

- `GET /api/v1/agenda/context` : réglages, jours non travaillés, suggestions liées aux appels récents, contexte ML

## Conventions UI (modale agenda)

- Les créneaux sont normalisés côté UI sur les jours/heures ouvrables configurés.
- Le sélecteur de tag applique automatiquement un preset visuel:
  - tag -> icône (`display_icon`)
  - tag -> couleur (`display_color`)
- La couleur par défaut côté modale est `Bleu primaire` (`#38bdf8`).

## Compatibilité

Les anciens endpoints `"/api/v1/appointments"` restent temporairement supportés côté backend (hors schéma OpenAPI) pour éviter de casser les clients existants.
