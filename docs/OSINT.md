# Module OSINT pour VocalGuard

## Vue d'ensemble

Le module OSINT (Open Source Intelligence) de VocalGuard permet d'enrichir les informations sur les numéros de téléphone en utilisant des outils Linux spécialisés, particulièrement adaptés pour WSL (Windows Subsystem for Linux) avec Kali Linux.

## Fonctionnalités

- Enrichissement automatique des informations sur les appelants
- Vérification de réputation des numéros
- Détection de spam et de scams
- **Détection de numéros commerciaux et télémarketeurs** (inspiré de callattendant)
- Intégration avec des outils OSINT populaires
- Support WSL/Kali Linux
- Intégration avec des APIs externes (NumLookup, OpenCNAM, NumVerify, HLR Lookup)

## Outils OSINT supportés

### 1. PhoneInfoga

**Description** : Outil avancé d'OSINT pour les numéros de téléphone

**Installation sur WSL/Kali** :

```bash
# Via Go (recommandé)
go install -v github.com/sundowndev/phoneinfoga/v2@latest

# Ou via Docker
docker pull sundowndev/phoneinfoga:latest
```

**Utilisation** :

```bash
phoneinfoga scan -n +33123456789
```

### 2. Truecaller

**Description** : Service de recherche d'identité par numéro

**Installation** :

```bash
pip install truecallerpy
```

### 3. theHarvester

**Description** : Outil de collecte d'informations

**Installation sur Kali** :

```bash
sudo apt-get install theharvester
```

### 4. Détection Commerciale (CommercialDetector)

**Description** : Module de détection de numéros commerciaux et télémarketeurs basé sur des patterns (inspiré de callattendant)

**Fonctionnalités** :
- Détection automatique des numéros surtaxés français (08XX, 09XX)
- Détection des numéros verts, azur, indigo, kiosque
- Détection de patterns de télémarketeurs (ex: V[0-9]{15})
- Détection basée sur le nom de l'appelant
- Patterns personnalisables

**Utilisation** : Intégré automatiquement dans le service OSINT

### 5. NumLookup API

**Description** : API pour valider et enrichir les informations sur les numéros de téléphone

**Installation** : Nécessite une clé API (gratuite avec limitations)

**Configuration** : Ajouter `NUMLOOKUP_API_KEY` dans le fichier `.env`

**Site** : https://numlookupapi.com/

### 6. OpenCNAM

**Description** : Service pour obtenir le nom de l'appelant (Caller ID Name)

**Installation** : Nécessite une clé API (gratuite avec limitations)

**Configuration** : Ajouter `OPENCNAM_API_KEY` dans le fichier `.env`

**Site** : https://www.opencnam.com/

### 7. NumVerify

**Description** : API pour valider et enrichir les numéros de téléphone

**Installation** : Nécessite une clé API (gratuite avec limitations)

**Configuration** : Ajouter `NUMVERIFY_API_KEY` dans le fichier `.env`

**Site** : https://numverify.com/

### 8. HLR Lookup

**Description** : Service pour vérifier la validité et l'opérateur d'un numéro (HLR = Home Location Register)

**Installation** : Nécessite une clé API (payant)

**Configuration** : Ajouter `HLR_API_KEY` dans le fichier `.env`

**Site** : https://www.hlrlookup.com/

## Services de reputation (NOMOROBO / SHOULDIANSWER)

Pour des services de blocage/reputation de type callattendant (NOMOROBO pour les USA, SHOULDIANSWER pour le reste), voir [REPUTATION_SERVICES.md](REPUTATION_SERVICES.md). Ils sont branches dans l'OSINT et dans le blocage d'appels.

## Liste des appels et profils en base

La page **Appels** affiche pour chaque appel la reputation OSINT, le lieu et l'operateur sans appeler les APIs en direct : tout est lu depuis la table `phone_number_profiles`.

- **Endpoint** : `GET /api/v1/calls?with_osint=true&limit=500`
- Les profils sont remplis par la migration avec `--run-osint` ou par les taches Celery d'enrichissement. Si un profil a un lieu/operateur (détection française) mais aucune reputation fournie par NumLookup/phoneinfoga, le service pose `reputation: "neutral"` (affichée "Non evaluee" en UI).
- Voir aussi [APPELS_OSINT_UI.md](APPELS_OSINT_UI.md) pour les détails (filtres, recherche, colonnes).

## OSINT + Entreprises (prospection)

Les imports d’entreprises (page **Entreprises**) peuvent déclencher des tâches Celery OSINT pour chaque numéro importé.

- Les analyses sont tracées dans `entreprise_phone_analyses` (statut: `queued` / `done` / `failed`).
- Les profils persistants sont stockés dans `phone_number_profiles`.
- À chaque fin de tâche Celery, le worker notifie l’API (`POST /events/osint`), puis le backend relaie un événement temps réel sur le WebSocket `/ws/events` :
  - `osint.profile.completed`
  - `osint.profile.failed`

Le frontend utilise ces événements pour rafraîchir automatiquement la liste et afficher les informations du profil OSINT dans la modale (onglet **OSINT**).

## Utilisation dans VocalGuard

### Via l'API

#### Enrichir un numéro

```bash
# Sans nom d'appelant
curl http://localhost:8000/api/v1/osint/phone/+33123456789

# Avec nom d'appelant (pour détection commerciale)
curl "http://localhost:8000/api/v1/osint/phone/+33123456789?caller_name=V123456789012345"
```

#### Vérifier la réputation

```bash
# Sans nom d'appelant
curl http://localhost:8000/api/v1/osint/reputation/+33123456789

# Avec nom d'appelant (pour détection commerciale)
curl "http://localhost:8000/api/v1/osint/reputation/+33123456789?caller_name=TELEMARKETING"
```

#### Détecter un numéro commercial

```bash
curl "http://localhost:8000/api/v1/osint/commercial/+33123456789?caller_name=V123456789012345"
```

#### Obtenir les patterns de détection

```bash
curl http://localhost:8000/api/v1/osint/patterns
```

#### Lister les outils disponibles

```bash
curl http://localhost:8000/api/v1/osint/tools
```

#### Installer phoneinfoga

```bash
curl -X POST http://localhost:8000/api/v1/osint/install/phoneinfoga
```

### Intégration automatique

Le service OSINT est automatiquement intégré au système de blocage :

- Lorsqu'un appel arrive, le numéro est automatiquement enrichi
- La réputation est vérifiée
- Les numéros identifiés comme spam/scam sont automatiquement bloqués

## Configuration

### Variables d'environnement

```bash
# Activer l'enrichissement OSINT automatique
OSINT_ENABLED=true

# Chemin vers les outils OSINT (adapter selon votre installation)
OSINT_TOOLS_PATH=/chemin/vers/vocalguard/osint_tools

# Clés API pour les services externes (optionnel)
NUMLOOKUP_API_KEY=your_key_here
OPENCNAM_API_KEY=your_key_here
NUMVERIFY_API_KEY=your_key_here
HLR_API_KEY=your_key_here
```

### Configuration YAML

```yaml
# Activer l'OSINT
osint:
  enabled: true
  auto_enrich: true
  tools_path: "/chemin/vers/vocalguard/osint_tools"

# Détection commerciale
commercial_detection:
  enabled: true
  # Patterns personnalisés de numéros (optionnel)
  number_patterns:
    "^(\+33|0)8[0-9]{2}[0-9]{6}$": "Numéro surtaxé personnalisé"
  # Patterns personnalisés de noms (optionnel)
  name_patterns:
    "V[0-9]{15}": "Télémarketeur (Caller ID)"
    "^(SERVICE|SERV|SRV)": "Service commercial"
```

## Structure des données OSINT

### Résultat d'enrichissement

```json
{
  "phone_number": "+33123456789",
  "sources": ["commercial_detector", "phoneinfoga", "numlookup"],
  "carrier": "Orange",
  "country": "France",
  "line_type": "mobile",
  "name": "Numéro surtaxé",
  "address": null,
  "social_media": {},
  "reputation": "low",
  "is_spam": false,
  "is_scam": false,
  "is_commercial": true,
  "is_telemarketer": false,
  "confidence": 0.8
}
```

### Résultat de détection commerciale

```json
{
  "is_commercial": true,
  "is_telemarketer": true,
  "detection_type": "name_pattern",
  "pattern_matched": "V[0-9]{15}",
  "description": "Télémarketeur (Caller ID)",
  "confidence": 0.9
}
```

### Résultat de réputation

```json
{
  "phone_number": "+33123456789",
  "reputation": "high",
  "is_spam": false,
  "is_scam": false,
  "confidence": 0.85,
  "sources": ["phoneinfoga"],
  "recommendation": "allow"
}
```

## Recommandations

- **allow** : Numéro sûr, autoriser l'appel
- **review** : Numéro à vérifier manuellement
- **block** : Numéro suspect, bloquer l'appel

## Installation sur WSL/Kali Linux

### Prérequis

```bash
# Mettre à jour le système
sudo apt update && sudo apt upgrade -y

# Installer Go (pour phoneinfoga)
sudo apt install golang-go

# Installer Python et pip
sudo apt install python3 python3-pip
```

### Installation des outils

```bash
# PhoneInfoga
go install -v github.com/sundowndev/phoneinfoga/v2@latest

# Vérifier l'installation
phoneinfoga version

# Truecaller (via Python)
pip3 install truecallerpy

# theHarvester
sudo apt install theharvester
```

### Configuration WSL

Assurez-vous que WSL peut exécuter les commandes Linux :

```bash
# Vérifier la version de WSL
wsl --version

# Tester une commande
which phoneinfoga
```

## Utilisation avancée

### Enrichissement personnalisé

Vous pouvez créer vos propres modules d'enrichissement en étendant `OSINTService` :

```python
from vocalguard.services.osint_service import OSINTService

class CustomOSINTService(OSINTService):
    async def _query_custom_tool(self, phone_number: str):
        # Votre logique personnalisée
        pass
```

### Intégration avec d'autres outils

Le module OSINT peut être étendu pour intégrer d'autres outils :

- **OSINT Framework** : Framework complet d'OSINT
- **Maltego** : Outil d'analyse de données
- **SpiderFoot** : Plateforme d'OSINT automatisée

## Sécurité et légalité

⚠️ **Important** :

- Utilisez les outils OSINT de manière responsable
- Respectez les lois locales sur la protection des données
- Ne collectez que des informations publiques
- Respectez les conditions d'utilisation des services tiers

## Dépannage

### PhoneInfoga non trouvé

```bash
# Vérifier que Go est installé
go version

# Vérifier le PATH
echo $PATH

# Ajouter Go au PATH si nécessaire
export PATH=$PATH:~/go/bin
```

### Erreurs de permissions

```bash
# Donner les permissions d'exécution
chmod +x ~/go/bin/phoneinfoga
```

### WSL ne détecte pas les outils

Vérifiez que vous êtes bien dans l'environnement WSL :

```bash
# Dans PowerShell
wsl

# Dans WSL, vérifier
which phoneinfoga
```

## Ressources

- [PhoneInfoga Documentation](https://github.com/sundowndev/phoneinfoga)
- [OSINT Framework](https://osintframework.com/)
- [Kali Linux Tools](https://www.kali.org/tools/)
- [WSL Documentation](https://docs.microsoft.com/en-us/windows/wsl/)

