"""
Enregistrement local des WAV micro apres filtre ambiance (Commercial Studio).
"""

from __future__ import annotations

import os
import re
import wave
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

from desktop.audio_core import AUDIO_RATE, pcm16_from_f32


def _recordings_root() -> Path:
    """
    Racine des enregistrements bureau.

    @returns Dossier (cree si besoin).
    """
    raw = (
        os.environ.get("VG_STUDIO_RECORDINGS")
        or str(Path.home() / "Documents" / "VocalGuard" / "recordings" / "commercial_studio")
    )
    root = Path(raw).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _env_save_enabled() -> bool:
    """True si sauvegarde WAV filtre active (defaut : oui)."""
    raw = (os.environ.get("VG_STUDIO_SAVE_FILTERED_WAV") or "1").strip().lower()
    return raw not in ("0", "false", "off", "no")


def write_mono_wav(path: Path, mono: np.ndarray, *, sample_rate: int = AUDIO_RATE) -> None:
    """
    Ecrit un mono float32 en WAV PCM 16 bits.

    @param path Fichier destination.
    @param mono Echantillons.
    @param sample_rate Hz (16 kHz par defaut).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = pcm16_from_f32(mono)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)


def _safe_label(label: str) -> str:
    """Nom de fichier court et sur."""
    s = re.sub(r"[^\w\-+]", "_", label.strip())[:48]
    return s or "clip"


class FilteredWavArchive:
    """
    Session d'enregistrements : un fichier par segment + piste continue concat.

    @param root Dossier parent (defaut Documents/VocalGuard/...).
    """

    def __init__(self, root: Optional[Path] = None) -> None:
        self._root = root or _recordings_root()
        self._session_dir: Optional[Path] = None
        self._counter = 0
        self._roll_path: Optional[Path] = None
        self.enabled = _env_save_enabled()
        self.new_session()

    @property
    def session_dir(self) -> Optional[Path]:
        """Dossier de la session en cours."""
        return self._session_dir

    def new_session(self) -> Path:
        """
        Nouveau sous-dossier horodate (nouveau fil dialogue).

        @returns Chemin session.
        """
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self._session_dir = self._root / stamp
        self._session_dir.mkdir(parents=True, exist_ok=True)
        self._counter = 0
        self._roll_path = self._session_dir / "session_filtre_concat.wav"
        return self._session_dir

    def _append_roll(self, mono: np.ndarray) -> None:
        """Ajoute a la piste continue de la session."""
        if self._roll_path is None or len(mono) < 1:
            return
        pcm = pcm16_from_f32(mono)
        if not self._roll_path.is_file():
            write_mono_wav(self._roll_path, mono)
            return
        with wave.open(str(self._roll_path), "rb") as rf:
            params = rf.getparams()
            frames = rf.readframes(rf.getnframes())
        with wave.open(str(self._roll_path), "wb") as wf:
            wf.setparams(params)
            wf.writeframes(frames)
            wf.writeframes(pcm)

    def save_filtered(self, mono: np.ndarray, label: str) -> Optional[Path]:
        """
        Sauvegarde un buffer deja filtre (gate / bandpass STT).

        @param mono Mono float32 16 kHz.
        @param label Prefixe (live_utterance, record_4s, ...).
        @returns Fichier ecrit ou None si desactive / vide.
        """
        if not self.enabled or self._session_dir is None or len(mono) < 1:
            return None
        self._counter += 1
        name = f"{self._counter:04d}_{_safe_label(label)}.wav"
        path = self._session_dir / name
        write_mono_wav(path, mono)
        self._append_roll(mono)
        return path
