# Page Appels et OSINT (VocalGuard)

Documentation des fonctionnalites ajoutees ou modifiees pour la liste des appels, l'affichage OSINT et les filtres.

## Vue d'ensemble

- **API** : `GET /api/v1/calls?with_osint=true&limit=500` retourne les appels avec reputation, lieu et operateur issus de la table `phone_number_profiles` (un seul appel, pas d'appel OSINT en direct au chargement).
- **Ordre** : les appels sont tries du **plus recent au plus ancien** (backend : `CallRepository.get_all` avec `order_by(desc(Call.call_time))`).
- **Colonnes** : Date, Numero, Statut, Reputation OSINT, Lieu, Operateur.
- **Reputation** : valeurs possibles en base puis affichage : `high` -> Bonne, `low` / spam/scam -> Risque, `neutral` -> Non evaluee (quand on a lieu/operateur mais pas de reputation externe), sinon Inconnue.

## Backend

### Route des appels

- Fichier : `backend/api/routes/calls.py`
- Parametre `with_osint` : si `true`, jointure sur `PhoneNumberProfile` par numero, construction de `OsintReputationResponse` pour chaque appel.
- Modele `OsintReputationResponse` (dans `backend/api/models.py`) : `phone_number`, `reputation`, `is_spam`, `is_scam`, etc., et champs optionnels `city`, `region`, `operator` pour lieu et operateur.

### Reputation "neutral"

- Si le profil a un lieu ou un operateur (détection française) mais **aucune** reputation fournie par les APIs externes (NumLookup, phoneinfoga), l'API renvoie `reputation: "neutral"` pour que l'UI affiche "Non evaluee" au lieu de "Inconnue".
- Cote service OSINT (`backend/services/osint_service.py`) : en fin de `enrich_phone_number`, si `result["reputation"]` est vide et qu'on a au moins `region`, `city` ou `operator`, on pose `result["reputation"] = "neutral"`. Ainsi la migration avec `--run-osint` peut persister une reputation pour ces numeros.

### Repository

- `backend/repositories/call_repository.py` : surcharge de `get_all` pour trier par `call_time` decroissant.

## Frontend (page Appels)

- Fichier : `frontend/src/app/calls/page.tsx`
- Donnees : `fetchCallsWithOsint()` (un seul GET avec `with_osint=true`).

### Filtres et recherche

- **Barre de recherche** : champ toujours visible ; interprete le texte (numero, operateur, lieu, ou mots-cles : repondu, manque, bloque, bonne, risque, non evaluee, inconnue). Combinaison possible (ex. "repondu Orange").
- **Filtres avances** : bouton "Filtres avances" ouvre un panneau depliable contenant les filtres Statut (Tous, Repondu, Manque, Bloque) et Reputation (Tous, Bonne, Risque, Non evaluee, Inconnue). Un badge sur le bouton indique le nombre de filtres actifs. Interface allegee : les filtres ne s'affichent qu'au clic.
- **Filtres actifs** : ligne de chips sous la barre (statut, reputation, texte saisi) quand au moins un filtre est applique. Bouton "Tout effacer" pour tout reinitialiser.
- **Compteur** : sous le tableau, "X appels" ou "X resultats sur Y appels" selon les filtres.

## Migration et profils OSINT

- Script : `scripts/migrate_callattendant_to_vocalguard.py`
- Option `--run-osint` : apres la migration des appels, enrichit chaque numero distinct via `OSINTService.enrich_phone_number()` et persiste les profils dans `phone_number_profiles` (reputation, lieu, operateur, etc.).
- Sans `--run-osint`, les profils ne sont pas crees : la page Appels affichera "Inconnue" (ou "Non evaluee" uniquement si un autre flux a rempli des profils avec lieu/operateur).
- La reputation en base est remplie par le service OSINT : `high`/`low` si une API externe ou le detecteur commercial le fournit, sinon `neutral` quand on a au moins lieu/operateur (détection FR).

## Fichiers concernes (resume)

| Role | Fichier |
|------|--------|
| API appels + OSINT | `backend/api/routes/calls.py` |
| Modeles reponse | `backend/api/models.py` (CallResponse, OsintReputationResponse) |
| Tri appels | `backend/repositories/call_repository.py` |
| Reputation neutral | `backend/services/osint_service.py` |
| Migration + OSINT | `scripts/migrate_callattendant_to_vocalguard.py` |
| Page + filtres + recherche | `frontend/src/app/calls/page.tsx` |
| Client API | `frontend/src/services/callsApi.ts` |
