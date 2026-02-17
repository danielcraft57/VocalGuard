#!/usr/bin/env python3
"""Test d'enregistrement audio avec PyAudio"""

import pyaudio
import wave
import sys

CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
# Essayer différents taux d'échantillonnage (le périphérique USB peut ne pas supporter 16kHz)
RATES = [48000, 44100, 32000, 22050, 16000, 8000]
RATE = None  # Sera déterminé automatiquement
RECORD_SECONDS = 3

try:
    p = pyaudio.PyAudio()
    
    # Utiliser le périphérique USB (device 0)
    device_index = 0
    device_info = p.get_device_info_by_index(device_index)
    print(f"Utilisation du périphérique: {device_info['name']}")
    print(f"  Inputs: {device_info['maxInputChannels']}")
    print(f"  Outputs: {device_info['maxOutputChannels']}")
    print(f"  Default sample rate: {device_info.get('defaultSampleRate', 'unknown')}")
    
    if device_info['maxInputChannels'] == 0:
        print("❌ Ce périphérique n'a pas d'entrée micro!")
        p.terminate()
        sys.exit(1)
    
    # Trouver un taux d'échantillonnage supporté
    print("\n🔍 Recherche d'un taux d'échantillonnage supporté...")
    for test_rate in RATES:
        try:
            test_stream = p.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=test_rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=CHUNK
            )
            test_stream.close()
            RATE = test_rate
            print(f"✅ Taux d'échantillonnage supporté: {RATE} Hz")
            break
        except Exception as e:
            print(f"   {test_rate} Hz: non supporté")
            continue
    
    if RATE is None:
        print("❌ Aucun taux d'échantillonnage supporté trouvé!")
        p.terminate()
        sys.exit(1)
    
    print(f"\n🎤 Enregistrement de {RECORD_SECONDS} secondes à {RATE} Hz...")
    
    stream = p.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=RATE,
        input=True,
        input_device_index=device_index,
        frames_per_buffer=CHUNK
    )
    
    frames = []
    for i in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
        data = stream.read(CHUNK)
        frames.append(data)
        if i % 10 == 0:
            print(f"  {i * CHUNK / RATE:.1f}s...", end='\r')
    
    stream.stop_stream()
    stream.close()
    p.terminate()
    
    print(f"\n✅ Enregistrement terminé ({len(frames) * CHUNK / RATE:.1f}s)")
    print(f"   {len(frames)} chunks enregistrés")
    
    # Sauvegarder dans un fichier temporaire
    output_file = "/tmp/test_record.wav"
    wf = wave.open(output_file, 'wb')
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(p.get_sample_size(FORMAT))
    wf.setframerate(RATE)
    wf.writeframes(b''.join(frames))
    wf.close()
    
    print(f"✅ Fichier sauvegardé: {output_file}")
    print(f"   Taille: {len(b''.join(frames))} bytes")
    
except Exception as e:
    print(f"❌ Erreur: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
