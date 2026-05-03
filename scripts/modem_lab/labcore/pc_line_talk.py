#!/usr/bin/env python3
"""
Session haut niveau "PC <-> ligne téléphonique".

Ce module encapsule la mécanique classique des scénarios live:
1) ouvrir le flux VRX modem
2) démarrer l'audio local (écoute et/ou micro)
3) gérer proprement l'arrêt pour éviter les états modem incohérents

Il sert de brique réutilisable pour des scénarios de conversation, test d'écho,
push-to-talk et supervision audio.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from loguru import logger

from labcore.live_audio import LiveAudioBridge


class PcLineTalkSession:
    """
    Orchestration compacte autour de ``ModemHandler`` + ``LiveAudioBridge``.

    - ouvre VRX côté modem
    - démarre l'audio PC (écoute seule ou full duplex)
    - expose ``push_to_talk`` quand activé
    """

    def __init__(
        self,
        modem: Any,
        *,
        input_device_index: Optional[int] = None,
        output_device_index: Optional[int] = None,
        uplink_burst_ms: int = 260,
        rx_only: bool = False,
        push_to_talk: bool = False,
        bridge_factory: Optional[Callable[..., LiveAudioBridge]] = None,
    ) -> None:
        """
        Paramètres principaux:
        - modem: instance ``ModemHandler`` déjà initialisée
        - input_device_index/output_device_index: sélection des périphériques audio PC
        - uplink_burst_ms: taille des rafales micro envoyées vers la ligne
        - rx_only: écoute seule (micro coupé)
        - push_to_talk: micro actif uniquement via ``push_to_talk()``
        - bridge_factory: injection de dépendance pour tests
        """
        self._modem = modem
        self._bridge_factory = bridge_factory or LiveAudioBridge
        self._bridge = self._bridge_factory(
            modem,
            input_device_index=input_device_index,
            output_device_index=output_device_index,
            uplink_burst_ms=uplink_burst_ms,
            rx_only=rx_only,
            push_to_talk=push_to_talk,
        )
        self._vrx_open = False
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    @property
    def bridge(self) -> LiveAudioBridge:
        return self._bridge

    async def start(self, *, already_in_voice_mode: bool = True) -> bool:
        """
        Démarre la session (VRX modem + bridge audio local).

        ``already_in_voice_mode=True`` est adapté aux scénarios où l'appel est déjà en
        contexte voix (après préparation/call setup). Si False, laisser le modem préparer
        selon la logique interne de ``start_outgoing_vrx_stream``.
        """
        if self._running:
            return True
        opened = await self._modem.start_outgoing_vrx_stream(
            already_in_voice_mode=already_in_voice_mode
        )
        if not opened:
            logger.warning("pc_line_talk: impossible d'ouvrir AT+VRX")
            return False
        self._vrx_open = True
        ok_audio = await self._bridge.start()
        if not ok_audio:
            await self._safe_close_vrx()
            return False
        self._running = True
        return True

    async def stop(self) -> None:
        """Arrête la session proprement (audio puis VRX), idempotent."""
        if self._running:
            try:
                await self._bridge.stop()
            finally:
                self._running = False
        await self._safe_close_vrx()

    async def push_to_talk(self, duration_ms: int = 1200) -> None:
        """
        Active le micro temporairement si le bridge est en mode push-to-talk.

        Sans push-to-talk côté bridge, cet appel reste sans danger (pas d'exception).
        """
        await self._bridge.push_to_talk_once(duration_ms)

    async def _safe_close_vrx(self) -> None:
        if not self._vrx_open:
            return
        self._vrx_open = False
        try:
            await self._modem.end_outgoing_vrx_stream()
        except Exception:
            logger.debug("pc_line_talk: fermeture VRX ignoree (exception)")

