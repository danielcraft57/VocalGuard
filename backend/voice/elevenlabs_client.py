"""
Client ElevenLabs TTS (accueil / apercu) + catalogue de voix.

La clef gratuite n'a souvent pas ``voices_read`` : on expose alors un catalogue
curate (voix predefinies) + possibilite de coller un voice_id custom.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from backend.core.config import Config


@dataclass(frozen=True)
class ElevenLabsVoiceInfo:
    """Une voix selectionnable dans l'UI."""

    voice_id: str
    name: str
    labels: str = ""
    recommended_fr: bool = False


# Catalogue offline (premade ElevenLabs) — usable sans permission voices_read.
# Les voix multilingual_v2 parlent le francais ; ``recommended_fr`` = bons candidats FR.
_CURATED_VOICES: tuple[ElevenLabsVoiceInfo, ...] = (
    ElevenLabsVoiceInfo("JBFqnCBsd6RMkjVDRZzb", "George", "homme, UK / multi", True),
    ElevenLabsVoiceInfo("onwK4e9ZLuTAKqWW03F9", "Daniel", "homme, UK / multi", True),
    ElevenLabsVoiceInfo("nPczCjzI2devNBz1zQrb", "Brian", "homme, US / multi", True),
    ElevenLabsVoiceInfo("TX3LPaxmHKxFdv7VOQHJ", "Liam", "homme, US / multi", False),
    ElevenLabsVoiceInfo("pNInz6obpgDQGcFmaJgB", "Adam", "homme, US / multi", False),
    ElevenLabsVoiceInfo("VR6AewLTigWG4xSOukaG", "Arnold", "homme, US / multi", False),
    ElevenLabsVoiceInfo("ErXwobaYiN019PkySvjV", "Antoni", "homme, US / multi", False),
    ElevenLabsVoiceInfo("yoZ06aMxZJJ28mfd3POQ", "Sam", "homme, US / multi", False),
    ElevenLabsVoiceInfo("pqHfZKP75CvOlQylNhV4", "Bill", "homme, US / multi", False),
    ElevenLabsVoiceInfo("EXAVITQu4vr4xnSDxMaL", "Sarah", "femme, US / multi", True),
    ElevenLabsVoiceInfo("XrExE9yKIg1WjnnlVkGX", "Matilda", "femme, US / multi", True),
    ElevenLabsVoiceInfo("XB0fDUnXU5powFXDhCwa", "Charlotte", "femme, SE / multi", True),
    ElevenLabsVoiceInfo("pFZP5JQG7rkQXXWNsC5V", "Lily", "femme, UK / multi", True),
    ElevenLabsVoiceInfo("Xb7hH8MSUJpSbSDYk0k2", "Alice", "femme, UK / multi", True),
    ElevenLabsVoiceInfo("FGY2WhTYpPnrIDTdsKH5", "Laura", "femme, US / multi", True),
    ElevenLabsVoiceInfo("cgSgspJ2msm6clMCkdW9", "Jessica", "femme, US / multi", False),
    ElevenLabsVoiceInfo("9BWtsMINqrJLrRacOk9x", "Aria", "femme, US / multi", False),
    ElevenLabsVoiceInfo("iP95p4xoKVk53GoZ742B", "Chris", "homme, US / multi", False),
    ElevenLabsVoiceInfo("cjVigY5qzO86Huf0OWal", "Eric", "homme, US / multi", False),
    ElevenLabsVoiceInfo("SAz9YHcvj6GT2YYXdXww", "River", "neutre / multi", True),
)


# Voix Marie (commercial sortant) — ElevenLabs premade.
ELEVENLABS_VOICE_MATILDA = "XrExE9yKIg1WjnnlVkGX"


def curated_elevenlabs_voices(*, fr_first: bool = True) -> list[dict[str, Any]]:
    """
    Catalogue local de voix ElevenLabs.

    @param fr_first Met les voix recommandees FR en tete.
    @returns Liste dict pour l'API JSON.
    """
    rows = list(_CURATED_VOICES)
    if fr_first:
        rows.sort(key=lambda v: (0 if v.recommended_fr else 1, v.name.lower()))
    return [
        {
            "voice_id": v.voice_id,
            "name": v.name,
            "labels": v.labels,
            "recommended_fr": v.recommended_fr,
            "source": "curated",
        }
        for v in rows
    ]


def resolve_elevenlabs_api_key(config: Config) -> Optional[str]:
    """
    Lit la clef API active (pool multi-clefs ou clef unique).

    @param config Configuration VocalGuard.
    @returns Clef ou None.
    """
    try:
        from backend.voice.elevenlabs_key_pool import resolve_active_api_key

        pooled = resolve_active_api_key()
        if pooled:
            return pooled
    except Exception as exc:
        logger.debug("Pool ElevenLabs ignore: {}", exc)

    key = getattr(config, "elevenlabs_api_key", None)
    if key:
        return str(key).strip() or None
    import os

    return (os.environ.get("ELEVENLABS_API_KEY") or "").strip() or None


def resolve_elevenlabs_model_id(config: Config) -> str:
    """
    Modele TTS ElevenLabs.

    @param config Configuration.
    @returns Identifiant modele.
    """
    raw = getattr(config, "elevenlabs_model_id", None)
    if raw:
        return str(raw).strip()
    import os

    return (os.environ.get("ELEVENLABS_MODEL_ID") or "eleven_multilingual_v2").strip()


def resolve_elevenlabs_default_voice_id(config: Config) -> str:
    """
    Voice id par defaut.

    @param config Configuration.
    @returns Voice id.
    """
    raw = getattr(config, "elevenlabs_voice_id", None)
    if raw:
        return str(raw).strip()
    import os

    return (os.environ.get("ELEVENLABS_VOICE_ID") or "JBFqnCBsd6RMkjVDRZzb").strip()


def fetch_elevenlabs_voices_from_api(api_key: str) -> Optional[list[dict[str, Any]]]:
    """
    Tente ``GET /v1/voices`` (necessite permission voices_read).

    @param api_key Clef ElevenLabs.
    @returns Liste ou None si permission / reseau KO.
    """
    req = urllib.request.Request(
        "https://api.elevenlabs.io/v1/voices",
        headers={"xi-api-key": api_key, "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        logger.warning("ElevenLabs voices_read refuse ({}): {}", exc.code, body)
        return None
    except Exception as exc:
        logger.warning("ElevenLabs voices list KO: {}", exc)
        return None

    out: list[dict[str, Any]] = []
    for row in data.get("voices") or []:
        vid = str(row.get("voice_id") or "").strip()
        if not vid:
            continue
        labels = row.get("labels") or {}
        label_bits = [
            str(labels.get(k))
            for k in ("language", "accent", "gender", "age", "description")
            if labels.get(k)
        ]
        out.append(
            {
                "voice_id": vid,
                "name": str(row.get("name") or vid),
                "labels": ", ".join(label_bits),
                "recommended_fr": "french" in " ".join(label_bits).lower()
                or "français" in " ".join(label_bits).lower()
                or "france" in " ".join(label_bits).lower(),
                "source": "api",
            }
        )
    out.sort(key=lambda v: (0 if v.get("recommended_fr") else 1, str(v.get("name", "")).lower()))
    return out


def list_elevenlabs_voices(config: Config) -> dict[str, Any]:
    """
    Liste les voix pour l'UI (API si possible, sinon catalogue curate).

    @param config Configuration.
    @returns Payload {voices, source, configured, warning?}.
    """
    api_key = resolve_elevenlabs_api_key(config)
    if not api_key:
        return {
            "configured": False,
            "source": "none",
            "voices": curated_elevenlabs_voices(),
            "warning": "ELEVENLABS_API_KEY manquante dans .env — ecoute impossible.",
            "default_voice_id": resolve_elevenlabs_default_voice_id(config),
            "model_id": resolve_elevenlabs_model_id(config),
        }

    api_voices = fetch_elevenlabs_voices_from_api(api_key)
    if api_voices:
        return {
            "configured": True,
            "source": "api",
            "voices": api_voices,
            "default_voice_id": resolve_elevenlabs_default_voice_id(config),
            "model_id": resolve_elevenlabs_model_id(config),
        }

    return {
        "configured": True,
        "source": "curated",
        "voices": curated_elevenlabs_voices(),
        "warning": (
            "La clef n'a pas la permission voices_read : catalogue VocalGuard. "
            "Active « Voices » sur la clef ElevenLabs, ou colle un voice_id custom."
        ),
        "default_voice_id": resolve_elevenlabs_default_voice_id(config),
        "model_id": resolve_elevenlabs_model_id(config),
    }


def synthesize_elevenlabs_mp3(
    *,
    api_key: str,
    text: str,
    voice_id: str,
    model_id: str = "eleven_multilingual_v2",
    out_path: Path,
) -> Path:
    """
    Genere un MP3 via ElevenLabs Text-to-Speech.

    @param api_key Clef API.
    @param text Texte a lire (court recommande pour le quota gratuit).
    @param voice_id Identifiant voix.
    @param model_id Modele (multilingual_v2 / flash_v2_5).
    @param out_path Destination MP3.
    @returns Chemin ecrit.
    @raises RuntimeError Si l'API echoue.
    """
    speak = (text or "").strip()
    if not speak:
        raise RuntimeError("Texte ElevenLabs vide")
    # Garde-fou quota gratuit : apercu court.
    if len(speak) > 500:
        speak = speak[:500].rstrip() + "…"

    body = json.dumps(
        {
            "text": speak,
            "model_id": model_id or "eleven_multilingual_v2",
        }
    ).encode("utf-8")
    url = (
        "https://api.elevenlabs.io/v1/text-to-speech/"
        f"{urllib.parse.quote(voice_id, safe='')}"
        "?output_format=mp3_44100_128"
    )
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"ElevenLabs TTS HTTP {exc.code}: {detail}") from exc
    except Exception as exc:
        raise RuntimeError(f"ElevenLabs TTS echoue: {exc}") from exc

    if not data or len(data) < 200:
        raise RuntimeError("ElevenLabs TTS: reponse audio vide")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(data)
    logger.info("ElevenLabs TTS OK voice={} bytes={}", voice_id, len(data))
    return out_path
