# Idées et fonctionnalités futures

## Application mobile / Client-serveur smartphone ↔ RPi 5

### Concept
Créer une application mobile (Android/iOS) qui se connecte au Raspberry Pi 5 via l'API REST existante pour contrôler VocalGuard à distance.

### État actuel
- ✅ API REST FastAPI déjà en place (`/api/v1/*`)
- ✅ CORS activé (permet les requêtes depuis n'importe quelle origine)
- ✅ Endpoints existants :
  - `/api/v1/calls` - Liste et détails des appels
  - `/api/v1/callers` - Gestion des appelants
  - `/api/v1/voicemails` - Messages vocaux
  - `/api/v1/config` - Configuration
  - `/api/v1/osint` - Enrichissement OSINT

### Ce qu'il faudrait ajouter

#### 1. Authentification API
- Système d'authentification (JWT, API keys, ou Basic Auth)
- Endpoint de login `/api/v1/auth/login`
- Protection des endpoints sensibles

#### 2. WebSocket pour les notifications en temps réel
- Notifications push pour les appels entrants
- Mise à jour en temps réel de l'état du système
- Streaming audio en temps réel (optionnel)

#### 3. Application mobile
**Technologies possibles :**
- **React Native** : Une seule codebase pour Android et iOS
- **Flutter** : Alternative moderne et performante
- **Application web progressive (PWA)** : Plus simple, fonctionne sur tous les appareils

**Fonctionnalités de l'app :**
- Dashboard avec statistiques des appels
- Liste des appels récents avec filtres
- Consultation des messages vocaux
- Gestion de la liste blanche/noire
- Notifications push pour appels entrants
- Contrôle du modem (voir section suivante)

#### 4. Configuration réseau
- Exposer l'API sur le réseau local (déjà fait avec `0.0.0.0`)
- Optionnel : Reverse proxy (nginx) pour HTTPS
- Optionnel : Tunnel SSH ou VPN pour accès sécurisé depuis l'extérieur

---

## Contrôle du modem 56k à distance - Appels sortants

### Concept
Permettre d'initier des appels sortants depuis l'application mobile via l'API REST, en contrôlant le modem 56k à distance.

### État actuel
- ✅ `ModemHandler` existe avec méthodes :
  - `answer_call()` - Décrocher un appel entrant
  - `hangup()` - Raccrocher
  - `send_command()` - Envoyer des commandes AT
- ❌ Pas de méthode pour initier un appel sortant (dial)

### Ce qu'il faudrait ajouter

#### 1. Méthode `dial()` dans ModemHandler
```python
async def dial(self, phone_number: str) -> bool:
    """
    Initie un appel sortant
    
    Args:
        phone_number: Numéro à appeler (format: +33123456789 ou 0123456789)
        
    Returns:
        True si l'appel est initié avec succès
    """
    # Commande ATDT pour composer le numéro
    # Format: ATDT0123456789\r\n
    # Attendre CONNECT ou NO CARRIER
```

#### 2. Endpoint API pour initier un appel
```python
POST /api/v1/calls/outgoing
{
    "phone_number": "+33123456789",
    "auto_answer": false  # Si True, décroche automatiquement après connexion
}
```

#### 3. Gestion de l'état de l'appel sortant
- Suivre l'état : "dialing", "ringing", "connected", "failed"
- WebSocket pour notifier l'app mobile de l'évolution
- Enregistrement de l'appel dans la base de données

#### 4. Contrôle pendant l'appel
- Endpoints pour :
  - Raccrocher : `POST /api/v1/calls/{call_id}/hangup`
  - Envoyer des commandes DTMF : `POST /api/v1/calls/{call_id}/dtmf`
  - Activer/désactiver le micro : `POST /api/v1/calls/{call_id}/mute`

#### 5. Intégration avec l'audio
- Utiliser l'adaptateur USB audio (CM108) pour :
  - Capturer l'audio du micro pendant l'appel
  - Jouer l'audio reçu sur les haut-parleurs
- Streaming audio bidirectionnel via WebSocket (optionnel, complexe)

### Architecture proposée

```
Smartphone App
    ↓ HTTPS/WSS
API REST (FastAPI) sur RPi 5
    ↓
CallService → ModemHandler → Modem 56k
                ↓
            AudioHandler → USB Audio (CM108)
```

### Sécurité
- Authentification obligatoire pour initier des appels
- Limitation du nombre d'appels par période
- Validation des numéros (format, liste blanche)
- Logs de tous les appels sortants

### Cas d'usage
1. **Appel depuis l'app mobile** : L'utilisateur compose un numéro sur son téléphone, l'appel passe par le modem 56k du RPi
2. **Rappel automatique** : L'utilisateur clique sur "Rappeler" depuis l'historique des appels
3. **Appel depuis un message vocal** : "Rappelez-moi au 06..." → transcription → bouton "Rappeler"

---

## Notes techniques

### Communication smartphone ↔ RPi
- **Sur réseau local** : `http://votre-serveur:8000/api/v1/...`
- **Depuis l'extérieur** : Nécessite :
  - VPN (WireGuard, OpenVPN)
  - Tunnel SSH (`ssh -L 8000:localhost:8000 user@votre-serveur`)
  - Reverse proxy avec authentification (nginx + Let's Encrypt)

### Performance
- L'API FastAPI est déjà async, donc performante
- WebSocket pour les notifications en temps réel
- Streaming audio nécessiterait une optimisation (compression, buffers)

### Compatibilité modem
- Les modems 56k supportent généralement les commandes ATDT (dial tone)
- Vérifier la compatibilité avec le modem spécifique (US Robotics 5637, etc.)

---

## Priorités suggérées

1. **Phase 1** : Authentification API + Endpoint appels sortants basique
2. **Phase 2** : Application mobile simple (PWA ou React Native)
3. **Phase 3** : WebSocket pour notifications temps réel
4. **Phase 4** : Streaming audio et contrôle avancé

---

*Document créé le 27 janvier 2026*
