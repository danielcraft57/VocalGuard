#!/usr/bin/env python3
"""Lecture WAV vers la ligne téléphonique (mode voix série), réutilisable."""

from pathlib import Path
from typing import Optional

from loguru import logger


async def play_wav_line_fallback(
    modem,
    wav_path: Path,
    *,
    prefer_already_in_voice: bool = False,
    pcm_u8: Optional[bytes] = None,
    pcm_rate: Optional[float] = None,
) -> bool:
    """
    Joue un WAV 8 kHz sur la ligne avec deux stratégies.

    Par défaut (appel entrant / composition aveugle) : séquence voix complète d'abord
    (souvent plus fiable sur USB), puis repli « déjà en voix ».

    prefer_already_in_voice=True (appel sortant après CONNECT) : tenter d'abord sans
    FCLASS/VLS — renvoyer toute la séquence sur une ligne déjà établie provoque souvent
    des tonalités aiguës et pas de PCM audible.
    """
    if not wav_path.is_file():
        logger.error("WAV introuvable: {}", wav_path)
        return False
    first, second = (True, False) if prefer_already_in_voice else (False, True)
    ok = await modem.play_wav_via_serial(
        wav_path,
        already_in_voice_mode=first,
        pcm_u8=pcm_u8,
        pcm_rate=pcm_rate,
    )
    if ok:
        return True
    logger.warning(
        "Lecture WAV (already_in_voice_mode={}) KO, retry avec already_in_voice_mode={}",
        first,
        second,
    )
    return await modem.play_wav_via_serial(
        wav_path,
        already_in_voice_mode=second,
        pcm_u8=pcm_u8,
        pcm_rate=pcm_rate,
    )


async def record_wav_line_fallback(
    modem,
    duration_sec: float,
    out_path: Path,
    *,
    prefer_already_in_voice: bool = False,
    stop_on_remote_hangup: bool = True,
) -> bool:
    """Enregistrement ligne (VRX) avec le même ordre de repli que play_wav_line_fallback."""
    first, second = (True, False) if prefer_already_in_voice else (False, True)
    ok = await modem.record_wav_via_serial(
        duration_sec,
        out_path,
        already_in_voice_mode=first,
        stop_on_remote_hangup=stop_on_remote_hangup,
    )
    if ok:
        return True
    logger.warning(
        "Enregistrement WAV (already_in_voice_mode={}) KO, retry avec already_in_voice_mode={}",
        first,
        second,
    )
    return await modem.record_wav_via_serial(
        duration_sec,
        out_path,
        already_in_voice_mode=second,
        stop_on_remote_hangup=stop_on_remote_hangup,
    )
