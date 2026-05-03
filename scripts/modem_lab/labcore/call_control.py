#!/usr/bin/env python3
"""
Contrôle d'appel réutilisable : décroché, composition, DTMF, préparation voix, raccrochage.

Toutes les opérations passent par le ``ModemHandler`` sur sa boucle asyncio (verrou série).

Ce module sert de façade "métier téléphonie" : il évite de disperser des appels AT bas niveau
dans chaque scénario et centralise les conventions de timing / fallback.
"""

from __future__ import annotations

import asyncio
from enum import Enum
from typing import Any, Optional, Tuple

from loguru import logger

from labcore.answer import fast_answer_incoming
from labcore.hangup import turbo_hangup


class HangupStyle(Enum):
    """
    Stratégie de fin d'appel.

    - TURBO: séquence agressive (VLS/FCLASS/ATH/CHUP...) adaptée aux cas réels instables.
    - SIMPLE_ATH: envoi classique ATH uniquement.
    """

    TURBO = "turbo"
    SIMPLE_ATH = "simple"


class CallController:
    """
    Façade async sur les commandes d'appel les plus courantes du lab.

    Le contrôleur n'ajoute pas de protocole propre; il encapsule simplement les primitives
    ``ModemHandler`` avec des signatures homogènes et des options par défaut orientées terrain.
    """

    __slots__ = ("_modem",)

    def __init__(self, modem: Any) -> None:
        """`modem` doit être une instance initialisée de ``ModemHandler``."""
        self._modem = modem

    @property
    def modem(self) -> Any:
        return self._modem

    async def answer_fast(
        self,
        *,
        ata_attempts: int = 6,
        ata_timeout: float = 0.1,
        sleep_between: float = 0.15,
    ) -> Tuple[bool, str, str]:
        """
        Décroché entrant rapide.

        Enchaîne une rafale courte de ``ATA`` (faible latence), puis repli ``answer_call``
        si le modem n'a pas confirmé immédiatement.
        """
        return await fast_answer_incoming(
            self._modem,
            ata_attempts=ata_attempts,
            ata_timeout=ata_timeout,
            sleep_between=sleep_between,
        )

    async def answer_full(self) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Décrochage « complet » modem.

        Suit la stratégie robuste du ``ModemHandler`` (ATA répété, ATH1, variantes voix).
        """
        return await self._modem.answer_call()

    async def hangup(
        self,
        style: HangupStyle = HangupStyle.TURBO,
        *,
        turbo_console_beep: bool = True,
        turbo_cmd_timeout: float = 0.20,
    ) -> bool:
        """
        Raccroche. ``TURBO`` enchaîne +VLS=0, +FCLASS=0, ATH… (scénarios lab) ;
        ``SIMPLE_ATH`` appelle seulement ``modem.hangup()`` (ATH).
        """
        if style == HangupStyle.SIMPLE_ATH:
            return await self._modem.hangup()
        ok, _cycles = await turbo_hangup(
            self._modem,
            enable_console_beep=turbo_console_beep,
            cmd_timeout=turbo_cmd_timeout,
        )
        return ok

    async def dial(
        self,
        number: str,
        *,
        blind: bool = True,
        timeout_sec: float = 25.0,
    ) -> Tuple[bool, str]:
        """
        Composition ``ATDT``.

        ``blind=True`` => ATDT...; (retour rapide), ``blind=False`` => attente de statut de connexion.
        """
        return await self._modem.dial_number(number, timeout=timeout_sec, blind=blind)

    async def send_dtmf(
        self,
        digits: str,
        *,
        inter_digit_delay_sec: float = 0.0,
    ) -> bool:
        """
        Envoie une suite DTMF via ``AT+VTS``.

        Les espaces/tabulations sont ignorés pour faciliter les chaînes lisibles côté appelant.
        """
        for ch in digits:
            if ch in " \t\r\n":
                continue
            ok = await self._modem.send_dtmf(ch)
            if not ok:
                logger.warning("DTMF '{}' refuse par le modem", ch)
                return False
            if inter_digit_delay_sec > 0:
                await asyncio.sleep(inter_digit_delay_sec)
        return True

    async def prepare_voice_for_blind_dial(self) -> bool:
        """+FCLASS=8 + codec sans +VLS=1 (composition ``ATDT…;``)."""
        return await self._modem.enter_voice_codec_before_dial()

    async def prepare_voice_off_hook(self) -> bool:
        """+FCLASS=8 + codec + +VLS=1 (ligne déjà décrochée avant tonalités)."""
        return await self._modem.enter_voice_line_for_outbound_dial()

    async def send_at(
        self,
        command: str,
        *,
        timeout: float = 3.0,
        stop_on_ring: bool = True,
    ) -> bytes:
        """
        Pass-through AT brut pour diagnostics.

        À réserver aux scénarios avancés afin de ne pas contourner les abstractions métier.
        """
        return await self._modem.send_command_full(
            command,
            timeout=timeout,
            stop_on_ring=stop_on_ring,
        )
