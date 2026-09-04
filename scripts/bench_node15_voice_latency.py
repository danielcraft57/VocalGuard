"""
Bench latence node15 : STT (tiny/base/small) + TTS + intent-predict.

Usage (LAN) :
  python scripts/bench_node15_voice_latency.py --url http://node15.lan:8100

Hors LAN / service absent : exit 0 (ne casse pas la CI).
"""

from __future__ import annotations

import argparse
import asyncio
import io
import statistics
import sys
import time
import wave
from pathlib import Path
from typing import List, Optional

import httpx

# Ajoute la racine repo
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PHRASES = [
    "bonjour je voudrais prendre rendez-vous",
    "merci beaucoup au revoir",
    "je laisse un message s il vous plait",
    "pouvez vous m envoyer un email",
    "je vous laisse mon numero de telephone",
]


def _silence_wav(seconds: float = 2.5, sample_rate: int = 16000) -> bytes:
    """WAV PCM silence (placeholder si pas d'audio reel)."""
    n = int(seconds * sample_rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * n)
    return buf.getvalue()


async def _timed(coro):
    t0 = time.perf_counter()
    result = await coro
    return result, (time.perf_counter() - t0) * 1000.0


async def bench(url: str, token: Optional[str], rounds: int) -> int:
    """
    Execute le bench.

    @returns 0 toujours (skip soft si down).
    """
    headers = {}
    if token:
        headers["X-STT-Token"] = token
    base = url.rstrip("/")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{base}/health")
            if r.status_code != 200:
                print(f"SKIP: health HTTP {r.status_code}")
                return 0
            print("health:", r.json())
    except Exception as exc:
        print(f"SKIP: node15 injoignable ({exc})")
        return 0

    wav = _silence_wav(2.5)
    stt_ms: List[float] = []
    intent_ms: List[float] = []
    tts_ms: List[float] = []

    async with httpx.AsyncClient(timeout=180.0) as client:
        for i in range(rounds):
            phrase = PHRASES[i % len(PHRASES)]
            files = {"file": ("bench.wav", wav, "audio/wav")}
            (_, ms) = await _timed(
                client.post(
                    f"{base}/v1/transcribe",
                    files=files,
                    headers=headers,
                    params={"mode": "live"},
                )
            )
            stt_ms.append(ms)
            print(f"STT live #{i+1}: {ms:.0f} ms")

            (_, ms) = await _timed(
                client.post(
                    f"{base}/v1/intent-predict",
                    json={"text": phrase, "top_k": 5},
                    headers=headers,
                )
            )
            intent_ms.append(ms)
            print(f"intent #{i+1}: {ms:.0f} ms ({phrase[:40]})")

            if i == 0:
                (_, ms) = await _timed(
                    client.post(
                        f"{base}/v1/tts",
                        json={
                            "text": "Bonjour, merci de votre appel.",
                            "voice": "fr-FR-DeniseNeural",
                            "rate": "-4%",
                            "pitch": "+3Hz",
                        },
                        headers=headers,
                    )
                )
                tts_ms.append(ms)
                print(f"TTS froid: {ms:.0f} ms")
            else:
                (_, ms) = await _timed(
                    client.post(
                        f"{base}/v1/tts",
                        json={
                            "text": "Bonjour, merci de votre appel.",
                            "voice": "fr-FR-DeniseNeural",
                        },
                        headers=headers,
                    )
                )
                tts_ms.append(ms)
                print(f"TTS #{i+1}: {ms:.0f} ms")

    def summary(name: str, values: List[float]) -> None:
        if not values:
            return
        p95 = sorted(values)[max(0, int(len(values) * 0.95) - 1)]
        print(
            f"{name}: mean={statistics.mean(values):.0f} ms "
            f"p95={p95:.0f} ms min={min(values):.0f} max={max(values):.0f}"
        )

    print("--- resume ---")
    summary("STT", stt_ms)
    summary("intent", intent_ms)
    summary("TTS", tts_ms)
    if stt_ms:
        p95 = sorted(stt_ms)[max(0, int(len(stt_ms) * 0.95) - 1)]
        if p95 > 2500:
            print(
                "GATE: STT p95 > 2.5 s — rester en semi-conversation / modele plus petit."
            )
        else:
            print("GATE: STT p95 OK pour conversation.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Bench latence voix node15")
    parser.add_argument("--url", default="http://node15.lan:8100")
    parser.add_argument("--token", default="")
    parser.add_argument("--rounds", type=int, default=5)
    args = parser.parse_args()
    raise SystemExit(
        asyncio.run(bench(args.url, args.token or None, max(1, args.rounds)))
    )


if __name__ == "__main__":
    main()
