# Plans VocalGuard — ligne entrante et telephonie

Index des documents de planification (aout 2026). Ces plans couvrent l'integration des lecons Call Attendant, la configuration entierement parametrable, et l'UX/UI Material Design sur toutes les pages concernees.

## Documents

| Fichier | Contenu |
|---------|---------|
| [01_OPTIMISATIONS_CALLATTENDANT.md](01_OPTIMISATIONS_CALLATTENDANT.md) | Ce qu'on recupere de Call Attendant, ce qu'on garde / on evite |
| [02_BACKEND_POLICY_ET_CONFIG.md](02_BACKEND_POLICY_ET_CONFIG.md) | Moteur de policy, schema YAML, API, phases backend |
| [03_UI_MATERIAL_DESIGN.md](03_UI_MATERIAL_DESIGN.md) | Design system MUI, pages, composants, navigation |
| [04_ROADMAP_INTEGREE.md](04_ROADMAP_INTEGREE.md) | Planning sprints backend + frontend, tests, criteres de succes |

## Contexte

- Etude Call Attendant existante : [../CALLATTENDANT_ETUDE.md](../CALLATTENDANT_ETUDE.md)
- Comparatif : [../CALLATTENDANT_VS_VOCALGUARD.md](../CALLATTENDANT_VS_VOCALGUARD.md)
- Stack telephonie : [../TELEPHONY_STACK.md](../TELEPHONY_STACK.md)

## Objectif global

Passer d'un modele binaire **repondeur / telephone** a un **screening par profil appelant** (permitted / screened / blocked), entierement configurable via YAML, API et UI Material Design, sans regression sur le comportement actuel (ATA, zero rings, anti-messagerie SFR).

## Regle produit

Aucune fonctionnalite backend livree sans ecran Material correspondant. Aucun comportement code en dur : tout passe par la config.
