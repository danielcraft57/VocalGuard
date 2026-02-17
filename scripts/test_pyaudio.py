#!/usr/bin/env python3
"""Test simple de PyAudio"""

import pyaudio

try:
    p = pyaudio.PyAudio()
    print(f"PyAudio OK - {p.get_device_count()} devices")
    
    # Lister les périphériques
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        print(f"Device {i}: {info['name']} (inputs: {info['maxInputChannels']}, outputs: {info['maxOutputChannels']})")
    
    p.terminate()
    print("Test PyAudio réussi!")
except Exception as e:
    print(f"Erreur PyAudio: {e}")
    import traceback
    traceback.print_exc()
