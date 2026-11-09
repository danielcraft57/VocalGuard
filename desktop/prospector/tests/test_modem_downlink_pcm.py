"""
Prospector : conversion VRX modem vers 16 kHz (profil USR 16-bit vs u8 legacy).
"""

from desktop.modem_local_call import u8_pcm_to_s16le
from backend.voice.audio_utils import pcm_modem_to_s16le_16k
from backend.voice.modem_profile import USR_VOICE_PROFILE
import numpy as np


def test_usr_s16_vrx_must_not_use_u8_decode():
    """Flux AT+VSM=129,11025 : traiter en u8 produit des saturations fantomes."""
    # Echantillon s16le faible (parole type)
    src = (1200).to_bytes(2, "little", signed=True) * 512
    wrong = u8_pcm_to_s16le(src)
    ok = pcm_modem_to_s16le_16k(src, USR_VOICE_PROFILE)
    arr_bad = np.frombuffer(wrong, dtype=np.int16)
    arr_ok = np.frombuffer(ok, dtype=np.int16)
    peak_ok = int(np.max(np.abs(arr_ok)))
    peak_bad = int(np.max(np.abs(arr_bad)))
    assert peak_ok < 5000
    assert peak_bad > peak_ok * 4
