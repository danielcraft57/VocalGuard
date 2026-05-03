#!/usr/bin/env python3
"""
Banque de WAV préchargés pour lecture ultra-rapide vers la ligne modem.

La banque sert de registre de prompts métiers:
- chargement initial unique (startup)
- lecture par clé pendant l'appel
- pas d'accès disque dans la boucle opérationnelle
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, Iterator, Optional

from labcore.line_audio_player import LineAudioPlayer, PreloadedWav


class WavBank:
    """
    Stocke des WAV préchargés indexés par clé métier.

    Exemple de clés: ``welcome``, ``menu_1``, ``retry``, ``goodbye``.
    """

    def __init__(self, player: LineAudioPlayer) -> None:
        self._player = player
        self._items: Dict[str, PreloadedWav] = {}

    def preload(
        self,
        key: str,
        wav_path: Path,
        *,
        logical_name: Optional[str] = None,
    ) -> PreloadedWav:
        """Précharge un WAV et l'associe à une clé (écrase la clé si déjà présente)."""
        item = self._player.preload_wav(wav_path, logical_name=logical_name)
        self._items[key] = item
        return item

    def preload_many(self, mapping: dict[str, Path]) -> None:
        """Précharge un lot ``clé -> chemin``."""
        for key, path in mapping.items():
            self.preload(key, path)

    def get(self, key: str) -> Optional[PreloadedWav]:
        """Retourne l'entrée si présente, sinon ``None``."""
        return self._items.get(key)

    def require(self, key: str) -> PreloadedWav:
        item = self.get(key)
        if item is None:
            raise KeyError(f"WAV introuvable pour la clé '{key}'")
        return item

    def keys(self) -> Iterator[str]:
        """Itérateur sur les clés chargées (ordre d'insertion)."""
        return iter(self._items.keys())

    def clear(self) -> None:
        self._items.clear()

    async def play(self, key: str, *, prefer_already_in_voice: bool = False) -> bool:
        """Joue l'entrée liée à ``key`` en passant par ``LineAudioPlayer``."""
        item = self.require(key)
        return await self._player.play_preloaded(
            item,
            prefer_already_in_voice=prefer_already_in_voice,
        )

