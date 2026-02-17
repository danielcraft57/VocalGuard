# Optimisations Ollama pour Raspberry Pi 5

## Problème identifié

Le système était surchargé avec :
- Plusieurs processus Ollama qui tournent en parallèle
- CPU à 99%+ d'utilisation
- Mémoire saturée (2.2GB par processus)
- Réponses très lentes ou blocages

## Solutions mises en place

### 1. Configuration systemd optimisée

Fichier : `/etc/systemd/system/ollama.service.d/override.conf`

```ini
[Service]
Environment=OLLAMA_HOST=0.0.0.0:11434
Environment=OLLAMA_MAX_LOADED_MODELS=1      # Un seul modèle en mémoire
Environment=OLLAMA_NUM_PARALLEL=1          # Une seule requête à la fois
Environment=OLLAMA_MAX_QUEUE=2              # Maximum 2 requêtes en attente
Environment=OLLAMA_KEEP_ALIVE=2m            # Décharge le modèle après 2 min d'inactivité
```

### 2. Modèles optimisés créés

#### `phi-fast` - Version rapide de phi
- Contexte réduit : 512 tokens (au lieu de 2048)
- Réponses limitées : 100 tokens max
- Température réduite : 0.5 (plus déterministe)
- Prompt système : Réponses brèves (2-3 phrases max)
- ⚠️ **Note** : Phi est principalement entraîné en anglais et peut répondre en anglais malgré le prompt français

#### `phi-fast-fr` - Version française stricte de phi
- Même base que phi-fast mais avec prompt système plus strict
- Température réduite à 0.3 pour plus de cohérence
- Réponses limitées à 80 tokens
- ⚠️ **Note** : Peut encore répondre en anglais occasionnellement

#### `phi-fr` - Version française standard
- Basé sur phi avec prompt système en français
- Paramètres par défaut
- ⚠️ **Note** : Peut répondre en anglais

#### `gemma:2b` - Modèle multilingue (recommandé pour le français)
- ~1.7 GB
- Meilleur support du français que phi
- Plus performant pour les réponses en français

#### `gemma-2b-fr` - Version française standard
- Basé sur gemma:2b avec prompt système en français
- Contexte : 1024 tokens
- Réponses : 120 tokens max
- Température : 0.4

#### `gemma-2b-fast` - Version ultra-rapide
- Basé sur gemma:2b optimisé pour la vitesse
- Contexte réduit : 512 tokens (moins de mémoire)
- Réponses très courtes : 60 tokens max (1-2 phrases)
- Température réduite : 0.3 (plus déterministe)
- ⚠️ **Note** : Contexte limité, historique de conversation réduit (6 échanges max)

#### `gemma-2b-chat` - Version optimisée pour conversations (recommandé)
- Basé sur gemma:2b optimisé pour les conversations avec historique
- Contexte : 1024 tokens (meilleure mémoire)
- Réponses : 100 tokens max
- Température : 0.4
- Prompt système amélioré pour clarifier les rôles (utilisateur vs assistant)
- **Meilleur pour les conversations avec historique**

#### `tinyllama` - Modèle ultra-léger (en cours de téléchargement)
- ~637 MB (vs 1.6 GB pour phi)
- Plus rapide mais moins performant

### 3. Script Python optimisé

Le script `ollama_shell.py` a été configuré pour :
- Utiliser `gemma-2b-fast` par défaut (modèle ultra-rapide)
- Timeout augmenté à 120 secondes
- Indicateur de progression
- **Historique de conversation** : Le modèle garde en mémoire les échanges précédents
- Commande `clear` pour effacer l'historique
- Extraction automatique des informations utilisateur (nom, etc.)
- Limite l'historique selon le modèle :
  - `gemma-2b-fast` : 6 échanges (12 messages) - contexte limité
  - `gemma-2b-chat` : 20 échanges (40 messages) - meilleure mémoire
- Utilise l'API `/api/chat` pour gérer les conversations avec historique

### 4. Service de préchargement automatique

Un service systemd `ollama-preload.service` a été créé pour :
- Précharger automatiquement le modèle au démarrage d'Ollama
- Éviter les délais de chargement lors de la première requête
- Garder le modèle en mémoire plus longtemps (OLLAMA_KEEP_ALIVE=10m)

## Utilisation recommandée

### Pour des réponses rapides
```bash
python ollama_shell.py "Ta question"
# Utilise phi-fast automatiquement
```

### Pour des réponses plus complètes
```bash
# Dans le shell interactif
model phi-fr
# Puis pose ta question
```

### Vérifier l'état du système
```bash
ssh pi@node15.lan "htop"
# Vérifier que CPU < 50% et RAM < 3GB
```

## Commandes utiles

### Vérifier les modèles disponibles
```bash
ssh pi@node15.lan "ollama list"
```

### Arrêter/démarrer Ollama
```bash
ssh pi@node15.lan "sudo systemctl stop ollama"
ssh pi@node15.lan "sudo systemctl start ollama"
```

### Voir les logs
```bash
ssh pi@node15.lan "sudo journalctl -u ollama -f"
```

### Vérifier les processus
```bash
ssh pi@node15.lan "ps aux | grep ollama"
```

## Performance attendue

Avec les optimisations :
- **gemma-2b-fast** : 3-8 secondes par réponse (recommandé, français garanti)
- **gemma-2b-fr** : 8-15 secondes par réponse (meilleur français, réponses plus longues)
- **phi-fast** : 5-15 secondes par réponse (peut répondre en anglais)
- **phi-fast-fr** : 5-15 secondes par réponse (meilleur français mais pas garanti)
- **phi-fr** : 15-30 secondes par réponse (peut répondre en anglais)
- **tinyllama** : 3-10 secondes par réponse (mais qualité moindre)

## Problème connu : Réponses en anglais avec phi

Le modèle `phi` est principalement entraîné en anglais et peut ignorer les instructions de répondre uniquement en français. Solutions :

1. **Utiliser `gemma:2b`** (recommandé) - Meilleur support multilingue
2. **Forcer le français dans le prompt utilisateur** : "Réponds UNIQUEMENT en français: [ta question]"
3. **Post-traiter les réponses** pour détecter et traduire si nécessaire

## Dépannage

### Si le système est encore bloqué

1. Arrêter Ollama :
```bash
ssh pi@node15.lan "sudo systemctl stop ollama"
```

2. Tuer les processus restants :
```bash
ssh pi@node15.lan "sudo pkill -9 ollama"
```

3. Redémarrer :
```bash
ssh pi@node15.lan "sudo systemctl start ollama"
```

### Si les réponses sont toujours lentes

- Utiliser `phi-fast` au lieu de `phi-fr`
- Réduire encore `num_predict` dans le modelfile
- Vérifier qu'aucun autre service ne consomme trop de ressources

## Configuration dans VocalGuard

Dans `env.example` :
```env
OLLAMA_BASE_URL=http://node15.lan:11434
OLLAMA_MODEL=gemma:2b  # Recommandé pour le français, ou phi-fast-fr
OLLAMA_TIMEOUT=30
```

## Modèles recommandés par usage

### Pour des conversations avec historique
- **gemma-2b-chat** (recommandé) - Optimisé pour conversations, historique fonctionnel, français garanti

### Pour des réponses rapides en français (sans historique)
- **gemma-2b-fast** - Ultra-rapide, français garanti, 1-2 phrases, historique limité
- **gemma-2b-fr** - Bon compromis qualité/vitesse, réponses plus longues
- **phi-fast-fr** - Rapide mais peut répondre en anglais

### Pour des réponses complètes
- **phi-fr** - Plus long mais meilleure qualité (peut répondre en anglais)

### Pour des tests/expérimentation
- **tinyllama** - Très rapide mais qualité moindre
