# Services de reputation (type callattendant)

VocalGuard integre des services externes de reputation pour les numeros, inspires de [callattendant](https://github.com/emxsys/callattendant) (BLOCK_SERVICE, Nomorobo, Should I Answer). Ils alimentent a la fois le **blocage en temps reel** et l'**enrichissement OSINT** (reputation affichee sur la page Appels).

## Vue d'ensemble

| Service         | Zone      | Role                    | Configuration                    |
|-----------------|-----------|-------------------------|----------------------------------|
| **NOMOROBO**    | USA only  | Robocalls / spam        | `BLOCK_SERVICE=NOMOROBO` + `NOMOROBO_API_KEY` |
| **SHOULDIANSWER** | Hors USA | Communaute (stub)     | `BLOCK_SERVICE=SHOULDIANSWER` + `SHOULDIANSWER_API_KEY` |

Si `BLOCK_SERVICE` est vide, seuls les regles de blocage locales, la liste noire et l'OSINT (NumLookup, phoneinfoga, etc.) sont utilises.

## Configuration

### Fichier .env (recommandé)

```bash
# Activer un service de reputation
BLOCK_SERVICE=NOMOROBO

# Nomorobo (USA) - clé API sur https://www.nomorobo.com/api/
NOMOROBO_API_KEY=votre_cle_api

# Optionnel: compatibilité config callattendant (legacy)
NOMOROBO_USERNAME=
NOMOROBO_PASSWORD=

# Should I Answer (hors USA) - pas d'API publique pour l'instant
SHOULDIANSWER_API_KEY=
```

### Fichier config.yaml

```yaml
block_enabled: true
block_service: "NOMOROBO"   # ou "SHOULDIANSWER" ou ""
```

Les clés sensibles (NOMOROBO_API_KEY, etc.) doivent rester dans `.env` ou variables d'environnement, pas dans le YAML versionné.

## NOMOROBO (USA)

- **Site** : https://www.nomorobo.com/api/
- **Usage** : numeros americains (+1). Requete `GET https://api.nomorobo.com/v2/check?From=...&To=...` avec header `X-API-Key`.
- **Effet** : si le numero est signale comme robocall/spam, la reputation est mise a "low", `is_spam`/`is_robocall` a True, et le blocage peut etre declenche (BlockService + affichage "Risque" sur la page Appels).
- **OSINT** : lors de l'enrichissement (migration `--run-osint`, taches Celery, ou API), le resultat Nomorobo est fusionne dans le profil (reputation, is_spam, etc.).

## SHOULDIANSWER (hors USA)

- **Site** : https://www.shouldianswer.net/ (appli communaute)
- **Etat** : pas d'API REST publique documentee. Le code contient un **stub** : si `BLOCK_SERVICE=SHOULDIANSWER` et qu'une cle est fournie, la structure est prete pour une future integration (partenaire ou API communaute).
- Pour l'instant, la reputation "hors USA" repose sur NumLookup, phoneinfoga, detection française, etc.

## Flux dans VocalGuard

1. **Blocage d'un appel entrant**  
   `BlockService.is_blocked()` appelle `_check_external_service()` : si `BLOCK_SERVICE` est NOMOROBO ou SHOULDIANSWER et que le fournisseur retourne "bloquer", l'appel est bloque.

2. **Enrichissement OSINT**  
   `OSINTService.enrich_phone_number()` lance en parallele `_query_nomorobo_reputation()` ou `_query_shouldianswer_reputation()` selon la config. Le resultat est fusionne (reputation, is_spam, is_scam) et peut etre persiste dans `phone_number_profiles` (migration `--run-osint` ou Celery).

3. **Page Appels**  
   Les profils en base (avec reputation fournie par Nomorobo ou autres sources) affichent "Bonne" / "Risque" / "Non evaluee" / "Inconnue". Voir [APPELS_OSINT_UI.md](APPELS_OSINT_UI.md).

## Fichiers concernes

| Role | Fichier |
|------|--------|
| Config | `backend/core/config.py` (block_service, nomorobo_api_key, shouldianswer_api_key) |
| Providers | `backend/services/reputation_providers.py` (check_nomorobo, check_shouldianswer) |
| OSINT | `backend/services/osint_service.py` (_query_nomorobo_reputation, _query_shouldianswer_reputation) |
| Blocage | `backend/services/block_service.py` (_check_external_service) |
| Exemple env | `env.example` |
| Exemple YAML | `config/config.example.yaml` |

## Equivalence callattendant (app.cfg)

Dans callattendant, on avait par exemple :

```python
BLOCK_SERVICE = "NOMOROBO"  # ou "SHOULDIANSWER" ou ""
NOMOROBO_USERNAME = ""
NOMOROBO_PASSWORD = ""
```

Dans VocalGuard :

- `BLOCK_SERVICE` : meme idee, valeurs `NOMOROBO`, `SHOULDIANSWER` ou vide.
- L'API Nomorobo actuelle utilise une **X-API-Key** ; on utilise donc `NOMOROBO_API_KEY`. Les champs `NOMOROBO_USERNAME` et `NOMOROBO_PASSWORD` sont gardes en config pour compatibilite/scripts legacy mais ne sont pas utilises par l'API v2.
