# Dépannage Audio - Conversation Vocale

## Problème : Pas de son / Blocage

### Symptômes
- Le script fonctionne mais aucun son ne sort
- Le système semble bloquer après la génération de la réponse
- Message "Aucune bibliothèque de lecture audio trouvée"

## Solutions

### 1. Installer pygame (recommandé)

```bash
pip install pygame
```

### 2. Utiliser winsound (Windows natif)

Sur Windows, `winsound` est inclus par défaut et devrait fonctionner automatiquement pour les fichiers WAV.

### 3. Installer playsound (alternative)

```bash
pip install playsound
```

### 4. Vérifier le format audio

Le système génère des fichiers WAV. Vérifiez que :
- Le fichier existe : `C:\Users\...\.vocalguard\audio_cache\temp_*.wav`
- Le fichier n'est pas corrompu
- Les permissions sont correctes

### 5. Test manuel

Ouvrez manuellement un fichier audio généré pour vérifier qu'il fonctionne :
```bash
# Le chemin est affiché dans les logs
# Ouvrez-le avec votre lecteur audio par défaut
```

### 6. Vérifier les permissions audio

- Vérifiez que le volume système n'est pas coupé
- Vérifiez que les haut-parleurs/casque sont bien connectés
- Testez avec un autre programme audio

## Ordre de priorité des méthodes de lecture

1. **winsound** (Windows) - Natif, fonctionne pour WAV
2. **pygame** - Multi-plateforme, très fiable
3. **playsound** - Simple mais peut bloquer
4. **Ouvrir avec lecteur par défaut** (Windows) - Fallback

## Commandes de test

```bash
# Test simple de lecture
python -c "import winsound; winsound.Beep(440, 1000)"

# Test avec un fichier WAV
python -c "import winsound; winsound.PlaySound('test.wav', winsound.SND_FILENAME)"
```

## Si rien ne fonctionne

Le système affichera quand même la réponse textuelle. Vous pouvez :
1. Lire la réponse à l'écran
2. Installer pygame : `pip install pygame`
3. Utiliser un autre script de test sans audio
