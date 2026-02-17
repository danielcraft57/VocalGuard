# Configuration des Patterns de Réponses

Ce fichier explique comment personnaliser les réponses de VocalGuard en modifiant le fichier `responses.yaml`.

## Structure du fichier

Le fichier `config/responses.yaml` contient deux sections principales :

### 1. Patterns de réponses

Chaque pattern contient :
- **keywords** : Liste de mots-clés à rechercher dans le texte de l'utilisateur
- **responses** : Liste de réponses possibles (une sera choisie aléatoirement)
- **priority** : Priorité du pattern (plus élevé = vérifié en premier, défaut: 0)
- **exact_match** : Si `true`, tous les mots-clés doivent être présents (défaut: `false`)

### 2. Réponses par défaut

Réponses utilisées si aucun pattern ne correspond. Utilisez `{text}` pour insérer le texte de l'utilisateur.

## Exemples

### Pattern simple (au moins un mot-clé)

```yaml
- keywords: ['bonjour', 'salut', 'hello']
  responses:
    - "Bonjour ! Comment puis-je vous aider ?"
    - "Salut ! Que puis-je faire pour vous ?"
  priority: 10
```

Si l'utilisateur dit "bonjour" ou "salut" ou "hello", une des réponses sera choisie aléatoirement.

### Pattern avec exact_match (tous les mots-clés requis)

```yaml
- keywords: ['bloquer', 'numéro', 'spam']
  responses:
    - "Je vais bloquer ce numéro de spam pour vous."
  priority: 9
  exact_match: true
```

Ce pattern ne correspondra que si l'utilisateur mentionne les trois mots : "bloquer", "numéro" et "spam".

### Réponse par défaut avec variable

```yaml
default_responses:
  - "J'ai bien entendu : {text}. Comment puis-je vous aider ?"
```

Le `{text}` sera remplacé par le texte de l'utilisateur.

## Priorité des patterns

Les patterns sont vérifiés dans l'ordre décroissant de priorité. Le premier pattern qui correspond est utilisé.

**Conseil** : Donnez une priorité élevée (10+) aux patterns importants comme les salutations et au revoir.

## Ajouter de nouveaux patterns

1. Ouvrez `config/responses.yaml`
2. Ajoutez un nouveau pattern dans la section `patterns` :

```yaml
- keywords: ['votre', 'mot', 'clé']
  responses:
    - "Réponse 1"
    - "Réponse 2"
  priority: 5
```

3. Redémarrez l'application ou utilisez l'endpoint `/api/v1/voice/test/reload-patterns` pour recharger les patterns

## Emplacement du fichier

Le fichier est cherché dans cet ordre :
1. `config/responses.yaml` (dans le répertoire du projet)
2. `~/.vocalguard/responses.yaml` (dans le répertoire de configuration utilisateur)

Si le fichier n'existe pas, il sera créé automatiquement avec des patterns par défaut.

## Rechargement des patterns

Pour recharger les patterns sans redémarrer l'application :

```bash
curl -X POST http://localhost:8000/api/v1/voice/test/reload-patterns
```

Ou via l'interface web, utilisez l'endpoint de rechargement.

## Bonnes pratiques

1. **Variété** : Ajoutez plusieurs réponses pour chaque pattern pour rendre la conversation plus naturelle
2. **Priorités** : Utilisez des priorités élevées pour les patterns importants
3. **Mots-clés** : Ajoutez des variantes (singulier/pluriel, synonymes) pour améliorer la détection
4. **Test** : Testez vos patterns avec l'interface de test vocal avant de les utiliser en production

