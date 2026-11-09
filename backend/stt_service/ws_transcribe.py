"""
WebSocket de transcription Whisper (service STT node15).

Protocole ``/ws/v1/transcribe`` :

- Query : ``mode=live|final`` (defaut live), ``token`` (si ``STT_INTERNAL_TOKEN``),
  ``window_sec`` (fenetre du partiel, defaut 4), ``max_sec`` (plafond buffer, defaut 30).
- Le client envoie du PCM s16le mono 16 kHz en trames binaires.
- Le client envoie du JSON texte :
  ``{"op":"transcribe"}`` partiel (rapide si mode live),
  ``{"op":"final"}`` passage complet,
  ``{"op":"reset"}`` vide le buffer,
  ``{"op":"end"}`` final puis fermeture,
  ``{"op":"ping"}``.
- Le serveur repond en JSON : ``ready``, ``partial``, ``final``, ``reset``, ``pong``, ``error``.

Un seul passage Whisper a la fois (verrou) : le modele n'est pas reentrant.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect
from loguru import logger

from backend.stt_service import engine as stt_engine

SAMPLE_RATE = 16000
BYTES_PER_SEC = SAMPLE_RATE * 2
MIN_AUDIO_SEC = 0.25
_OPS = frozenset({"transcribe", "final", "reset", "end", "ping"})

# Whisper (serveur ou modele) n'accepte qu'un job a la fois.
_infer_lock = asyncio.Lock()


class PcmWindow:
    """
    Buffer PCM 16-bit mono, borne en duree, aligne sur les echantillons.

    @param max_sec Duree max conservee (les plus vieux octets sont jettes).
    """

    def __init__(self, max_sec: float) -> None:
        self.max_bytes = _even_bytes(max_sec * BYTES_PER_SEC)
        self._buf = bytearray()
        self._odd = b""

    def append(self, chunk: bytes) -> None:
        """
        Ajoute une trame. Un octet orphelin est garde pour la trame suivante.

        @param chunk Octets PCM bruts.
        """
        if not chunk:
            return
        if self._odd:
            chunk = self._odd + chunk
            self._odd = b""
        if len(chunk) % 2:
            self._odd = chunk[-1:]
            chunk = chunk[:-1]
        if not chunk:
            return
        self._buf.extend(chunk)
        overflow = len(self._buf) - self.max_bytes
        if overflow > 0:
            if overflow % 2:
                overflow += 1
            del self._buf[:overflow]

    def snapshot(self, window_sec: Optional[float]) -> bytes:
        """
        Copie le buffer, ou seulement les dernieres ``window_sec`` secondes.

        @param window_sec Fenetre. None = tout le buffer.
        @returns PCM s16le.
        """
        if window_sec is None:
            return bytes(self._buf)
        keep = _even_bytes(window_sec * BYTES_PER_SEC)
        if len(self._buf) <= keep:
            return bytes(self._buf)
        return bytes(self._buf[-keep:])

    def clear(self) -> None:
        """Vide le buffer et l'octet en attente."""
        self._buf.clear()
        self._odd = b""

    def __len__(self) -> int:
        """@returns Nombre d'octets PCM alignes."""
        return len(self._buf)


def _even_bytes(n: float) -> int:
    """
    Arrondit un nombre d'octets vers le bas, pair (echantillons 16-bit).

    @param n Octets souhaites.
    @returns Entier pair >= 0.
    """
    out = int(n)
    if out < 0:
        return 0
    if out % 2:
        out -= 1
    return out


def _clamp(value: float, low: float, high: float) -> float:
    """Borne un flottant."""
    return max(low, min(high, value))


def _query_float(raw: Optional[str], default: float, low: float, high: float) -> float:
    """
    Lit un float de query string, sinon le defaut, puis le borne.

    @param raw Valeur brute.
    @param default Valeur si absente ou illisible.
    @param low Borne basse.
    @param high Borne haute.
    @returns Float borne.
    """
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return _clamp(float(raw), low, high)
    except ValueError:
        return default


def _expected_token() -> Optional[str]:
    """Token interne LAN, ou None si non configure."""
    return (os.environ.get("STT_INTERNAL_TOKEN") or "").strip() or None


def _presented_token(websocket: WebSocket) -> str:
    """
    Token presente par le client (query ``token`` ou header ``X-STT-Token``).

    @param websocket Connexion entrante.
    @returns Token, eventuellement vide.
    """
    query = (websocket.query_params.get("token") or "").strip()
    if query:
        return query
    return (websocket.headers.get("x-stt-token") or "").strip()


def parse_client_op(raw: str) -> str:
    """
    Decode une commande JSON client.

    @param raw Texte recu.
    @returns Une op parmi transcribe, final, reset, end, ping.
    @raises ValueError Si le JSON ou l'op est invalide.
    """
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("JSON objet attendu.")
    op = str(data.get("op") or data.get("type") or "").strip().lower()
    if op == "partial":
        op = "transcribe"
    if op not in _OPS:
        raise ValueError(f"op inconnue: {op or '?'}")
    return op


async def _infer(pcm: bytes, *, fast: bool) -> tuple[str, list]:
    """
    Lance Whisper hors de la boucle, un job a la fois.

    @param pcm PCM 16 kHz s16le.
    @param fast True pour un partiel (sans cues).
    @returns Texte et cues (vides si fast).
    """
    async with _infer_lock:
        text = await asyncio.to_thread(
            stt_engine.transcribe_pcm16,
            pcm,
            SAMPLE_RATE,
            fast=fast,
        )
        cues = [] if fast else list(stt_engine.last_cues())
        return text, cues


async def websocket_transcribe(websocket: WebSocket) -> None:
    """
    Session de transcription streaming.

    Refuse la connexion (code 4401) si ``STT_INTERNAL_TOKEN`` est defini
    et que le client ne le presente pas.

    @param websocket Connexion FastAPI.
    """
    expected = _expected_token()
    if expected and _presented_token(websocket) != expected:
        logger.warning("WebSocket STT refuse: token invalide")
        await websocket.close(code=4401)
        return

    mode = (websocket.query_params.get("mode") or "live").strip().lower()
    if mode not in ("live", "final"):
        mode = "live"
    window_sec = _query_float(websocket.query_params.get("window_sec"), 4.0, 0.4, 20.0)
    max_sec = _query_float(websocket.query_params.get("max_sec"), 30.0, 2.0, 60.0)
    if window_sec > max_sec:
        window_sec = max_sec

    await websocket.accept()
    window = PcmWindow(max_sec)
    await websocket.send_json(
        {
            "type": "ready",
            "engine": stt_engine.engine_name() or "",
            "mode": mode,
            "sample_rate": SAMPLE_RATE,
            "window_sec": window_sec,
            "max_sec": max_sec,
        }
    )
    logger.info("WebSocket STT ouvert mode={}", mode)

    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            payload_bytes = message.get("bytes")
            if payload_bytes is not None:
                window.append(payload_bytes)
                continue
            payload_text = message.get("text")
            if payload_text is None:
                continue
            try:
                op = parse_client_op(payload_text)
            except (ValueError, json.JSONDecodeError) as exc:
                await websocket.send_json({"type": "error", "detail": str(exc)})
                continue
            if op == "ping":
                await websocket.send_json({"type": "pong"})
                continue
            if op == "reset":
                window.clear()
                await websocket.send_json({"type": "reset"})
                continue
            fast = op != "final" and op != "end" and mode == "live"
            snap_window = window_sec if fast else None
            pcm = window.snapshot(snap_window)
            if len(pcm) < int(MIN_AUDIO_SEC * BYTES_PER_SEC):
                await websocket.send_json(
                    {
                        "type": "final" if op in ("final", "end") else "partial",
                        "text": "",
                        "bytes_pcm": len(pcm),
                        "buffered": len(window),
                        "mode": "final" if op in ("final", "end") else mode,
                        "engine": stt_engine.engine_name() or "",
                        "cues": [],
                    }
                )
            else:
                try:
                    text, cues = await _infer(pcm, fast=fast)
                except Exception as exc:
                    logger.exception("WebSocket STT echoue: {}", exc)
                    await websocket.send_json(
                        {"type": "error", "detail": f"Transcription impossible: {exc}"}
                    )
                    if op == "end":
                        await websocket.close()
                        return
                    continue
                kind = "final" if op in ("final", "end") else "partial"
                await websocket.send_json(
                    {
                        "type": kind,
                        "text": text,
                        "bytes_pcm": len(pcm),
                        "buffered": len(window),
                        "mode": "final" if kind == "final" else mode,
                        "engine": stt_engine.engine_name() or "",
                        "cues": cues,
                    }
                )
            if op == "end":
                await websocket.close()
                return
    except WebSocketDisconnect:
        logger.info("WebSocket STT ferme par le client")
    except Exception as exc:
        logger.warning("WebSocket STT interrompu: {}", exc)
        try:
            await websocket.close()
        except Exception:
            pass
