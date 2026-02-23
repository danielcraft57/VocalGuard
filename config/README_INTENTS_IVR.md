# Intents IVR (test patterns)

Le fichier `intents_ivr.yaml` definit les strategies question-reponse utilisees par le script `scripts/test_patterns_voice.py`. Chaque intent associe des mots-cles a une reponse TTS et a un fichier WAV telephonique (8 kHz).

## Structure

- **intents** : liste d'intents, chacun avec `name`, `keywords`, `response`, `filename`, optionnellement `priority` et `exact_match`.
- **default_intent** : reponse si aucun intent ne matche.
- **exit_intent** : intent "au revoir" (keywords + response + filename).

Les intents sont tries par `priority` (plus eleve = teste en premier). Pour chaque intent, soit au moins un mot-cle doit etre present (defaut), soit tous si `exact_match: true`.

## Packages NLU / ML

Pour un IVR avec peu d'options et des formulations previsibles, des **mots-cles + priorite** (comme dans ce fichier) suffisent : pas de dependance lourde, edition a la main, comportement explicable.

Des librairies dediees permettent d'aller plus loin :

- **Rasa** : framework NLU complet, entrainement sur des exemples de phrases, extraction d'entites. Adapte si tu veux un chatbot ou un assistant avec beaucoup d'intents et des tournures variees.
- **Snips NLU** : moteur NLU leger (intent + slots), deterministe ou probabiliste. Bien pour des commandes vocales avec parametres.

**Coupler du machine learning** devient interessant quand :

- tu as beaucoup d'intents et des formulations tres variables ;
- tu veux extraire des entites (dates, noms, numeros) dans la phrase ;
- tu veux un score de confiance par intent.

Pour un serveur vocal type telephone (quelques options : horaires, message, contact), le fichier YAML reste en general le meilleur compromis.
