#!/usr/bin/env python3
"""
Lecture audio pour le lab : **ligne** (``AT+VTX`` / WAV) et **aperçu local** (haut-parleurs PC).

- Ligne : réutilise ``play_wav_line_fallback`` / ``play_wav_via_serial`` (8 kHz, mono, u8 attendu côté modem).
- Local : ``sounddevice`` ou ``pyaudio`` si disponibles (même convention PCM que ``live_audio``).

Ce module couvre deux usages complémentaires:
1) lecture opérationnelle sur la ligne téléphonique (temps réel, contrainte modem)
2) pré-écoute locale d'un prompt sans passer par la ligne.
"""

from __future__ import annotations

import asyncio
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from labcore.live_audio import u8_pcm_to_s16le
from labcore.pcm_file import read_wav_mono_u8
from labcore.voice_line import play_wav_line_fallback


@dataclass(frozen=True)
class PreloadedWav:
    """
    WAV préchargé en PCM u8 pour envoi rapide vers la ligne.

    Champs:
    - source_path: fichier d'origine (traçabilité / logs)
    - pcm_u8: payload déjà converti au format modem
    - sample_rate_hz: fréquence source (idéalement 8000)
    - logical_name: nom utilisé dans les logs modem
    """

    source_path: Path
    pcm_u8: bytes
    sample_rate_hz: int
    logical_name: str


class LineAudioPlayer:
    """
    Joue de l'audio vers la **ligne téléphonique** via le modem.

    Point clé: toutes les lectures ligne passent par les méthodes ``ModemHandler`` afin de
    conserver la synchronisation série/AT déjà gérée ailleurs dans le projet.
    """

    __slots__ = ("_modem",)

    def __init__(self, modem: Any) -> None:
        """`modem` est une instance ``ModemHandler`` déjà initialisée."""
        self._modem = modem

    @property
    def modem(self) -> Any:
        return self._modem

    async def play_wav(
        self,
        wav_path: Path,
        *,
        prefer_already_in_voice: bool = False,
    ) -> bool:
        """
        Joue un fichier WAV vers la ligne.

        Utilise la stratégie fallback des scénarios (ordre d'essais avec/sans already_in_voice_mode).
        """
        return await play_wav_line_fallback(
            self._modem,
            wav_path,
            prefer_already_in_voice=prefer_already_in_voice,
        )

    async def play_pcm_u8(
        self,
        pcm_u8: bytes,
        *,
        sample_rate_hz: float = 8000.0,
        prefer_already_in_voice: bool = False,
        logical_name: str = "<buffer>",
    ) -> bool:
        """
        Envoie un buffer PCM 8-bit unsigned (centré 128) vers la ligne, sans fichier WAV.

        ``logical_name`` sert uniquement aux journaux (le modem attend un ``Path`` pour les messages).
        """
        if not pcm_u8:
            logger.warning("play_pcm_u8: buffer vide")
            return False
        return await self._modem.play_wav_via_serial(
            Path(logical_name),
            already_in_voice_mode=prefer_already_in_voice,
            pcm_u8=pcm_u8,
            pcm_rate=float(sample_rate_hz),
        )

    def preload_wav(
        self,
        wav_path: Path,
        *,
        logical_name: Optional[str] = None,
    ) -> PreloadedWav:
        """
        Charge un WAV en mémoire (PCM u8) pour un envoi quasi immédiat.

        Retourne un objet immutable prêt à être passé à :meth:`play_preloaded`.
        """
        pcm_u8, rate = read_wav_mono_u8(wav_path)
        if not pcm_u8:
            raise ValueError(f"WAV vide: {wav_path}")
        return PreloadedWav(
            source_path=wav_path,
            pcm_u8=pcm_u8,
            sample_rate_hz=int(rate),
            logical_name=logical_name or wav_path.name,
        )

    async def play_preloaded(
        self,
        wav: PreloadedWav,
        *,
        prefer_already_in_voice: bool = False,
    ) -> bool:
        """
        Joue un WAV préchargé (sans I/O disque au moment de l'appel).

        C'est le chemin recommandé en campagne d'appels avec prompts répétés.
        """
        return await self.play_pcm_u8(
            wav.pcm_u8,
            sample_rate_hz=float(wav.sample_rate_hz),
            prefer_already_in_voice=prefer_already_in_voice,
            logical_name=wav.logical_name,
        )


def _play_s16_blocking(int16_pcm: bytes, sample_rate: int) -> None:
    """
    Joue du PCM S16LE mono sur la sortie par défaut (bloquant jusqu'à la fin).

    Préférence backend:
    1) sounddevice (si numpy + sounddevice présents)
    2) pyaudio en repli
    """
    try:
        import numpy as np
        import sounddevice as sd

        arr = np.frombuffer(int16_pcm, dtype=np.int16)
        sd.play(arr, sample_rate)
        sd.wait()
        return
    except ImportError:
        pass
    try:
        import pyaudio  # type: ignore
    except ImportError as e:
        raise RuntimeError("sounddevice ou pyaudio requis pour la lecture locale") from e
    pa = pyaudio.PyAudio()
    stream = pa.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=sample_rate,
        output=True,
    )
    try:
        stream.write(int16_pcm)
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()


async def preview_wav_on_host(
    wav_path: Path,
    *,
    max_rate_warn: bool = True,
) -> bool:
    """
    Lit un WAV mono (8 ou 16 bits) et le joue sur les haut-parleurs de la machine (aperçu).

    Utile pour vérifier un message avant ``play_wav`` vers la ligne. Non disponible sans
    **sounddevice** ni **pyaudio**.
    """
    if not wav_path.is_file():
        logger.error("WAV introuvable: {}", wav_path)
        return False
    try:
        pcm_u8, rate = read_wav_mono_u8(wav_path)
    except (wave.Error, ValueError, OSError) as e:
        logger.warning("preview: lecture {}: {}", wav_path, e)
        return False
    if max_rate_warn and rate != 8000:
        logger.warning(
            "preview: {} Hz — lecture à la vitesse fichier ; pour la ligne, viser 8 kHz",
            rate,
        )
    s16 = u8_pcm_to_s16le(pcm_u8)
    try:
        await asyncio.to_thread(_play_s16_blocking, s16, rate)
    except Exception as e:
        logger.warning("preview locale impossible: {}", e)
        return False
    return True
