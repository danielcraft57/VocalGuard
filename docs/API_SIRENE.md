# Guide d'accès à l'API Sirene

## Changements récents

L'API Sirene a changé de localisation. Elle est maintenant accessible via le **portail API de l'INSEE** au lieu de l'ancien portail api.gouv.fr.

## Comment obtenir l'accès à l'API Sirene

### Étape 1 : Accéder à la page de l'API

1. Aller sur [data.gouv.fr/dataservices](https://www.data.gouv.fr/dataservices)
2. Rechercher "Sirene" ou cliquer sur "API Sirene open data" dans la sélection du moment
3. Ou accéder directement : [https://www.data.gouv.fr/dataservices/api-sirene-open-data](https://www.data.gouv.fr/dataservices/api-sirene-open-data)

### Étape 2 : Accéder à la documentation

1. Cliquer sur le bouton **"Documentation métier"**
2. Cela redirige vers le portail API de l'INSEE : [https://portail-api.insee.fr/](https://portail-api.insee.fr/)

### Étape 3 : Souscrire à l'API

1. Sur la page de l'API Sirene, cliquer sur le bouton **"Souscrire"**
2. Choisir **"connexion-pour-les-externes"** (si vous n'êtes pas agent INSEE)
3. Créer un compte ou se connecter avec un compte existant

### Étape 4 : Générer la clé API

1. Une fois connecté, vous pouvez souscrire à l'API Sirene
2. Aller dans l'onglet **"Souscriptions"** de votre application
3. Sélectionner votre souscription à "API Sirene 3.11"
4. Dans la section **"Clés d'API"**, vous verrez votre clé API générée automatiquement
5. Copier cette clé API (format UUID, ex: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`)
6. Cette clé est nécessaire pour authentifier les requêtes

## Informations importantes

- **Gratuit** : L'API Sirene open data est gratuite
- **Limite** : 30 requêtes par minute pour les usages open data
- **Disponibilité** : 99.5%
- **URL de l'API** : `https://api.insee.fr/api-sirene/3.11`
- **Version actuelle** : 3.11 (depuis le 30 avril 2024)

## Configuration dans VocalGuard

Une fois que vous avez obtenu votre clé API, ajoutez-la dans votre fichier `.env` :

```env
# API Sirene (portail-api.insee.fr)
# Obtenir la clé : https://portail-api.insee.fr/ → Applications → VocalGuard → Souscriptions
SIRENE_API_KEY=votre_cle_api_ici
```

**Note** : L'API Sirene utilise une authentification par clé API simple (header `Authorization: Bearer <cle>`). La recherche par numéro de téléphone n'est pas directement disponible - il faut d'abord obtenir un SIRET ou SIREN via d'autres moyens.

## Documentation officielle

- **Portail API INSEE** : [https://portail-api.insee.fr/](https://portail-api.insee.fr/)
- **Documentation API Sirene** : [https://portail-api.insee.fr/catalog/api/2ba0e549-5587-3ef1-9082-99cd865de66f](https://portail-api.insee.fr/catalog/api/2ba0e549-5587-3ef1-9082-99cd865de66f)
- **Support** : sirene@insee.fr

## Alternatives

Si vous cherchez des informations sur les entreprises par numéro de téléphone, l'API Sirene n'est pas la solution idéale car elle ne permet pas de rechercher directement par téléphone. Considérez plutôt :

- **Twilio Lookup** : Pour identifier l'opérateur et le type de ligne
- **Reverse phone lookup services** : Pour identifier le propriétaire du numéro
- **Bases de données d'annuaires** : Pour les numéros publics

