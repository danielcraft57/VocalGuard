#!/bin/bash
# Script de configuration audio pour Raspberry Pi

echo "=========================================="
echo "Configuration audio pour Raspberry Pi"
echo "=========================================="
echo ""

# Vérifier les périphériques audio
echo "[1/4] Vérification des périphériques audio..."
echo ""
echo "Périphériques de lecture (aplay -l):"
aplay -l 2>&1 | grep -E "^card|^  " || echo "Aucun périphérique de lecture détecté"
echo ""
echo "Périphériques d'enregistrement (arecord -l):"
arecord -l 2>&1 | grep -E "^card|^  " || echo "Aucun périphérique d'enregistrement détecté"
echo ""

# Vérifier USB
echo "[2/4] Périphériques USB audio..."
lsusb | grep -i audio || echo "Aucun périphérique USB audio détecté"
echo ""

# Vérifier PulseAudio
echo "[3/4] État de PulseAudio..."
if systemctl --user is-active --quiet pulseaudio 2>/dev/null; then
    echo "✅ PulseAudio est actif"
    pulseaudio --check -v 2>&1 | head -5
else
    echo "⚠️ PulseAudio n'est pas actif"
    echo "   Démarrage de PulseAudio..."
    pulseaudio --start -v 2>&1 | head -5 || echo "   Impossible de démarrer PulseAudio"
fi
echo ""

# Créer un fichier de configuration ALSA pour le périphérique par défaut
echo "[4/4] Configuration ALSA..."
ALSA_CONFIG_DIR="$HOME/.asoundrc"
if [ ! -f "$ALSA_CONFIG_DIR" ]; then
    echo "   Création de ~/.asoundrc..."
    cat > "$ALSA_CONFIG_DIR" << 'EOF'
# Configuration ALSA pour périphérique USB par défaut
pcm.!default {
    type plug
    slave {
        pcm "hw:0,0"  # Carte USB (card 0)
    }
}
ctl.!default {
    type hw
    card 0
}
EOF
    echo "✅ Fichier ~/.asoundrc créé"
    echo "   ⚠️ Ajustez 'card 1' selon votre configuration (voir 'aplay -l')"
else
    echo "✅ Fichier ~/.asoundrc existe déjà"
fi
echo ""

echo "=========================================="
echo "✅ Configuration terminée"
echo "=========================================="
echo ""
echo "Pour tester l'audio:"
echo "  # Test de lecture"
echo "  aplay /usr/share/sounds/alsa/Front_Left.wav"
echo ""
echo "  # Test d'enregistrement (5 secondes)"
echo "  arecord -d 5 test.wav && aplay test.wav"
echo ""
echo "Si ça ne fonctionne pas, vérifiez:"
echo "  1. Que le micro-casque est bien branché"
echo "  2. Que le périphérique est détecté: aplay -l && arecord -l"
echo "  3. Ajustez le numéro de carte dans ~/.asoundrc"
echo ""
