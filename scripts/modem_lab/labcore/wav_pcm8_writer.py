#!/usr/bin/env python3
"""Écriture incrémentale WAV PCM 8-bit mono 8 kHz (unsigned)."""

from __future__ import annotations

import struct
from pathlib import Path


class WavPcm8MonoWriter:
    """
    Ouvre un fichier WAV, réserve l'en-tête, puis accepte des blocs PCM u8.

    finalize() met à jour les champs taille/data dans l'en-tête.
    """

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._f = self._path.open("wb")
        self._f.write(b"\x00" * 44)
        self._data_bytes = 0

    @property
    def path(self) -> Path:
        return self._path

    @property
    def bytes_written(self) -> int:
        return self._data_bytes

    def write_pcm_u8(self, pcm: bytes) -> None:
        if not pcm:
            return
        self._f.write(pcm)
        self._data_bytes += len(pcm)

    def _write_header(self) -> None:
        self._f.seek(0)
        riff_size = 36 + self._data_bytes
        self._f.write(
            struct.pack(
                "<4sI4s4sIHHIIHH4sI",
                b"RIFF",
                riff_size,
                b"WAVE",
                b"fmt ",
                16,
                1,
                1,
                8000,
                8000,
                1,
                8,
                b"data",
                self._data_bytes,
            )
        )

    def finalize(self) -> None:
        self._write_header()
        self._f.flush()
        self._f.close()
