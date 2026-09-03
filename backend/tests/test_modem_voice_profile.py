"""Tests profil voix USR 16-bit / 11 kHz et conversions PCM."""

from backend.core.modem_handler import _detect_is_conexant_zoom, _firmware_indicates_usr5637
from backend.voice.audio_utils import (
    pcm_chunk_peak,
    pcm_modem_to_s16le_16k,
    pcm_s16le_16k_to_modem,
    resample_s16le_mono,
)
from backend.voice.modem_profile import (
    CONEXANT_VOICE_PROFILE,
    USR_FALLBACK_PROFILE,
    USR_VOICE_PROFILE,
    parse_vsm_spec,
    resolve_voice_profile,
)


def test_parse_vsm_rollback():
    assert parse_vsm_spec("128,8000") == USR_FALLBACK_PROFILE
    assert parse_vsm_spec("AT+VSM=129,11025") == USR_VOICE_PROFILE
    assert parse_vsm_spec("") is None


def test_resolve_usr_default():
    profile = resolve_voice_profile(is_conexant=False, vsm_spec=None)
    assert profile.vsm_command == "AT+VSM=129,11025"
    assert profile.sample_rate == 11025
    assert profile.sample_width == 2
    assert profile.bytes_per_sec == 22050
    assert profile.baudrate == 230400


def test_resolve_conexant_ignores_usr_vsm():
    profile = resolve_voice_profile(is_conexant=True, vsm_spec="129,11025")
    assert profile == CONEXANT_VOICE_PROFILE


def test_resample_s16le_roundtrip_length():
    # 1 kHz tone-ish: 11025 samples of small s16
    src = (2000).to_bytes(2, "little", signed=True) * 11025
    up = resample_s16le_mono(src, 11025, 16000)
    assert abs((len(up) // 2) - 16000) <= 2
    down = resample_s16le_mono(up, 16000, 11025)
    assert abs((len(down) // 2) - 11025) <= 3


def test_pcm_modem_usr_to_16k():
    pcm = (1200).to_bytes(2, "little", signed=True) * 11025
    out = pcm_modem_to_s16le_16k(pcm, USR_VOICE_PROFILE)
    assert len(out) >= 30000
    assert len(out) % 2 == 0


def test_pcm_16k_to_usr_modem():
    src = (900).to_bytes(2, "little", signed=True) * 16000
    out = pcm_s16le_16k_to_modem(src, USR_VOICE_PROFILE)
    assert abs((len(out) // 2) - 11025) <= 3


def test_pcm_chunk_peak_s16():
    silent = b"\x00\x00" * 8
    loud = (8000).to_bytes(2, "little", signed=True) * 8
    assert pcm_chunk_peak(silent, sample_width=2) == 0
    assert pcm_chunk_peak(loud, sample_width=2) == 8000


def test_firmware_indicates_usr5637():
    assert _firmware_indicates_usr5637("U.S. Robotics 56K FAX USB V1.2.23  OK")
    assert not _firmware_indicates_usr5637("Zoom 3095")


def test_detect_usr_not_conexant_despite_chipset_string():
    ati = b"U.S. Robotics\r\nConexant HCF V.90 56K Data Fax Voice USB Modem\r\n"
    assert not _detect_is_conexant_zoom(ati, b"", "U.S. Robotics 56K FAX USB V1.2.23  OK")


def test_detect_zoom_conexant():
    ati = b"Zoom 3095 V.92 Data Fax Modem\r\nConexant\r\n"
    assert _detect_is_conexant_zoom(ati, b"", None)
