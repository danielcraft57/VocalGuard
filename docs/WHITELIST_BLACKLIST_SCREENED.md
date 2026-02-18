# Gestion whitelist / blacklist et "screened" dans VocalGuard

## 1. Où c’est stocké

Tout passe par le modèle **Caller** (`backend/database/models.py`) :

- **`is_whitelisted`** : numéro en liste blanche (toujours accepté).
- **`is_blocked`** : numéro en liste noire (toujours bloqué).

Il n’y a pas de tables séparées "Whitelist" / "Blacklist" comme dans callattendant : un seul enregistrement par numéro avec ces deux drapeaux.

En plus, les **règles de blocage** (`block_rules`) permettent de bloquer par motif (exact, préfixe, regex) sans créer un Caller par numéro.

---

## 2. Ordre de décision à l’arrivée d’un appel

Dans `CallManager.handle_incoming_call()` on appelle `BlockService.is_blocked()`. L’ordre est :

1. **Liste blanche**  
   Si le numéro a un Caller avec `is_whitelisted=True` → **jamais bloqué** (on retourne `False`).

2. **Liste noire**  
   Si le numéro a un Caller avec `is_blocked=True` → **bloqué** (on retourne `True`).

3. **Règles de blocage**  
   Si une règle active (`block_rules`) correspond au numéro (exact / préfixe / regex) → **bloqué**.

4. **OSINT**  
   Si la réputation OSINT recommande "block", ou si télémarketing/commercial avec forte confiance → **bloqué**.

5. **Service externe**  
   Si configuré (`block_service`), vérification externe (TODO Nomorobo, etc.).

6. Sinon → **pas bloqué**, l’appel est pris en charge (décrochage, message, interaction vocale, etc.).

Fichiers concernés :

- `backend/services/block_service.py` : `is_blocked()`, `_check_block_rules()`, OSINT.
- `backend/core/call_manager.py` : appel à `is_blocked()` puis soit `block_call` + message, soit `answer_call` + flux normal.

---

## 3. Whitelist (liste blanche)

- **Modèle** : `Caller.is_whitelisted = True` (et en pratique `is_blocked = False`).
- **Création / mise à jour** :
  - `BlockService.whitelist_caller(phone_number)` → crée ou met à jour le Caller avec `is_whitelisted=True`, `is_blocked=False`.
  - `CallerRepository.whitelist_caller(phone_number)` → met à jour l’appelant existant en `is_whitelisted=True`.
- **API** :
  - `GET /api/v1/callers?is_whitelisted=true` : lister les numéros en liste blanche.
  - `POST /api/v1/callers/whitelist` (body : `phone_number`, optionnel `name`, `notes`) : ajouter à la liste blanche.
  - `PUT /api/v1/callers/{id}` avec `is_whitelisted: false` : retirer de la liste blanche.

La whitelist est prioritaire : si le numéro est whitelisté, il n’est jamais bloqué, même par une règle ou l’OSINT.

---

## 4. Blacklist / darklist (liste noire)

- **Modèle** : `Caller.is_blocked = True` (en général `is_whitelisted = False`).
- **Création / mise à jour** :
  - `BlockService.block_caller(phone_number, reason)` → crée ou met à jour le Caller avec `is_blocked=True`, `is_whitelisted=False`.
  - `CallerRepository.block_caller(phone_number)` → met à jour l’appelant existant en `is_blocked=True`.
- **Règles** : table `block_rules` (pattern exact, préfixe ou regex) pour bloquer sans créer de Caller.
- **API** :
  - `GET /api/v1/callers?is_blocked=true` : lister les numéros bloqués (callers en blacklist).
  - `POST /api/v1/callers/block` (body : `phone_number`, optionnel `name`, `notes`) : ajouter à la liste noire.
  - `PUT /api/v1/callers/{id}` avec `is_blocked: false` : retirer de la liste noire (débloquer).

Donc "blacklist" / "darklist" = soit un Caller avec `is_blocked=True`, soit une règle de blocage qui matche le numéro.

---

## 5. "Screened" (d’où ça vient et ce que ça devient)

Dans **callattendant**, "Screened" était une **action** sur l’appel : l’appel a été "filtré" / passé au filtre (souvent pris quand même). Ce n’est pas une liste à part.

Dans **VocalGuard** :

- Il n’y a pas de statut d’appel nommé "screened".
- Les statuts d’appel sont : `ringing`, `answered`, `blocked`, `completed`, `missed` (modèle `Call.status`).
- Lors de la **migration** callattendant → vocalguard (`scripts/migrate_callattendant_to_vocalguard.py`), on mappe :
  - **Blocked** → `status = "blocked"`
  - **Permitted** / **Screened** → `status = "completed"` (appel accepté / filtré et traité).

Donc "screened" côté callattendant = appel qui a passé le filtre et a été géré ; en VocalGuard ça devient un appel **completed** (pas une liste ni un type de liste).

Résumé : **whitelist / blacklist** = gestion par Caller + règles ; **screened** = ancienne action callattendant, devenue simplement un appel traité (`completed`) dans VocalGuard.

---

## 6. Règles de blocage (block_rules)

- **Table** : `block_rules` (name, pattern, pattern_type : exact | prefix | regex, is_active, description).
- **API** :
  - `GET /api/v1/block-rules` : lister les règles.
  - `POST /api/v1/block-rules` (body : `name`, `pattern`, `pattern_type`, optionnel `description`) : créer une règle.
  - `DELETE /api/v1/block-rules/{rule_id}` : supprimer une règle.

Le `BlockService` utilise ces règles dans `is_blocked()` (exact, préfixe ou regex sur le numéro / nom).

---

## 7. Interface de filtrage (frontend)

La page **Filtrage d'appels** (`/filtering`) permet de gérer :

- **Liste blanche** : tableau des numéros autorisés, formulaire d'ajout (numéro, nom optionnel), bouton Retirer.
- **Liste noire** : tableau des numéros bloqués, formulaire d'ajout (numéro, raison optionnelle), bouton Débloquer.
- **Règles de blocage** : tableau des règles (nom, pattern, type), formulaire d'ajout (nom, pattern, type exact/prefix/regex), bouton Supprimer.

Services front : `callersFilterApi.ts` (whitelist/blocklist), `blockRulesApi.ts` (règles). Lien dans la sidebar : "Filtrage d'appels".
