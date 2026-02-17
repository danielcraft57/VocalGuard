#!/usr/bin/env python3
"""Script pour créer le fichier ~/.asoundrc correctement"""

import os
from pathlib import Path

asoundrc_content = """# Configuration ALSA pour périphérique USB
# Désactiver les périphériques virtuels non disponibles pour éviter les warnings
pcm.!default {
    type plug
    slave {
        pcm "hw:0,0"
    }
}
ctl.!default {
    type hw
    card 0
}

# Désactiver les périphériques virtuels qui causent des warnings
pcm.front cards.pcm.front
pcm.rear cards.pcm.rear
pcm.center_lfe cards.pcm.center_lfe
pcm.side cards.pcm.side
pcm.hdmi cards.pcm.hdmi
pcm.modem cards.pcm.modem
pcm.phoneline cards.pcm.phoneline
"""

asoundrc_path = Path.home() / ".asoundrc"

try:
    with open(asoundrc_path, 'w') as f:
        f.write(asoundrc_content)
    print(f"✅ Fichier {asoundrc_path} créé avec succès")
    print("\nContenu:")
    print(asoundrc_content)
except Exception as e:
    print(f"❌ Erreur: {e}")
