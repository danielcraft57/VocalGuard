#!/usr/bin/env python3
"""
Benchmark local de conversation vocale (micro/casque) pour tester:
- latence STT (VOSK/Whisper)
- latence ML intents (CommercialMlConversationBrain)
- latence génération réponse (patterns / intents)
- latence TTS (pyttsx3 / gTTS / edge-tts)

Objectif: itérer rapidement sur les intents et mesurer la réactivité réelle.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import queue
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, AsyncIterator, Any

from loguru import logger

# Ajouter la racine du projet au path pour importer backend
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.config import Config  # noqa: E402
from backend.core.response_patterns import ResponsePatternManager  # noqa: E402
from backend.ml.ml_intents import CommercialMlConversationBrain  # noqa: E402
from backend.voice.recognition import VoiceRecognition  # noqa: E402
from backend.voice.synthesis import VoiceSynthesis  # noqa: E402
from backend.voice.intents_loader import load_intents_ivr, find_intent  # noqa: E402

from scripts.voice_test_utils import setup_logging, check_sounddevice, play_audio_file  # noqa: E402


@dataclass
class TurnMetrics:
    turn_index: int
    started_at_ms: int
    user_text: str
    stt_engine: str
    tts_engine: str
    ml_enabled: bool
    ml_best_intent: Optional[str]
    ml_best_score: float
    chosen_mode: str  # ml | intents | patterns
    chosen_intent: Optional[str]
    response_text: str
    timings_ms: dict[str, int]


async def microphone_stream(
    sample_rate: int,
    channels: int,
    chunk_size: int,
    max_seconds: float,
    device: Optional[int] = None,
) -> AsyncIterator[bytes]:
    """
    Flux async de chunks PCM 16-bit depuis sounddevice.
    """
    import sounddevice as sd

    audio_q: "queue.Queue[bytes]" = queue.Queue()

    def callback(indata, frames, time_info, status):  # noqa: ANN001, ARG001
        try:
            audio_q.put_nowait(bytes(indata))
        except Exception:
            pass

    start = time.monotonic()
    with sd.RawInputStream(
        samplerate=sample_rate,
        blocksize=chunk_size,
        dtype="int16",
        channels=channels,
        callback=callback,
        device=device,
    ):
        while True:
            if time.monotonic() - start > max_seconds:
                break
            try:
                chunk = audio_q.get(timeout=0.5)
            except queue.Empty:
                continue
            if chunk:
                yield chunk


def now_ms() -> int:
    return int(time.time() * 1000)


def monotonic_ms() -> int:
    return int(time.monotonic() * 1000)


def format_ms(ms: int) -> str:
    return f"{ms}ms"


def pick_response(
    user_text: str,
    ml_brain: CommercialMlConversationBrain,
    intents_payload: tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]],
    pattern_manager: ResponsePatternManager,
) -> tuple[str, dict[str, Any]]:
    """
    Stratégie:
    1) ML si confiant -> réponse ML
    2) intents YAML -> response
    3) patterns -> response
    """
    ml_reply = ml_brain.generate_reply_if_confident(user_text)
    if ml_reply:
        ctx = ml_brain.build_context(user_text, top_k=3)
        return ml_reply, {"mode": "ml", "ml": ctx}

    intents, default_intent, exit_intent = intents_payload
    chosen = find_intent(user_text, intents, default_intent, exit_intent)
    if chosen and chosen.get("response"):
        return str(chosen["response"]), {"mode": "intents", "intent": chosen}

    return pattern_manager.generate_response(user_text), {"mode": "patterns"}


async def main() -> None:
    setup_logging()
    try:
        check_sounddevice()
    except SystemExit:
        logger.info("")
        logger.info("Installation rapide (Windows/conda): conda install -c conda-forge python-sounddevice")
        logger.info("Installation rapide (pip): pip install sounddevice")
        return

    parser = argparse.ArgumentParser(description="Benchmark conversation vocale (latence STT/ML/TTS).")
    parser.add_argument("--stt", choices=["vosk", "whisper"], default=None, help="Moteur STT (sinon .env).")
    parser.add_argument("--tts", choices=["pyttsx3", "gtts", "edgetts"], default=None, help="Moteur TTS (sinon .env).")
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--chunk", type=int, default=4000)
    parser.add_argument("--max-seconds", type=float, default=9.0)
    parser.add_argument("--device", type=int, default=None, help="Index sounddevice (entrée).")
    parser.add_argument("--turns", type=int, default=12)
    parser.add_argument("--log-jsonl", action="store_true", help="Ecrit un fichier JSONL de métriques dans logs/.")
    args = parser.parse_args()

    config = Config()
    if args.stt:
        config.voice_recognition_engine = args.stt
    if args.tts:
        config.voice_synthesis_engine = args.tts

    recognition = VoiceRecognition(config)
    synthesis = VoiceSynthesis(config)
    await recognition.initialize()
    await synthesis.initialize()

    pattern_manager = ResponsePatternManager()
    intents_payload = load_intents_ivr(base_path=PROJECT_ROOT)
    ml_brain = CommercialMlConversationBrain(PROJECT_ROOT)

    logger.info("=== Benchmark intent vocal (local) ===")
    logger.info("STT={} | TTS={} | ML_enabled={} (threshold={})", recognition.engine, synthesis.engine, ml_brain.enabled, getattr(ml_brain, "threshold", None))
    logger.info("Parle normalement dans ton micro. Dis 'au revoir' pour arrêter.")

    log_path: Optional[Path] = None
    log_fh = None
    if args.log_jsonl:
        logs_dir = PROJECT_ROOT / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_path = logs_dir / f"voice_benchmark_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"
        log_fh = log_path.open("w", encoding="utf-8")
        logger.info("Logs JSONL: {}", log_path)

    all_turns: list[TurnMetrics] = []

    try:
        for turn in range(args.turns):
            logger.info("")
            logger.info("🎤 Tour {} / {} — écoute (max {:.1f}s)...", turn + 1, args.turns, args.max_seconds)
            t0 = monotonic_ms()

            # STT en flux si VOSK (meilleure latence)
            user_text = ""
            if recognition.engine == "vosk":
                audio_stream = microphone_stream(
                    sample_rate=args.sample_rate,
                    channels=1,
                    chunk_size=args.chunk,
                    max_seconds=args.max_seconds,
                    device=args.device,
                )
                stt_start = monotonic_ms()
                utterances = await recognition.stream_vosk(audio_stream=audio_stream, sample_rate=args.sample_rate, max_utterances=1)
                stt_end = monotonic_ms()
                user_text = utterances[0] if utterances else ""
            else:
                # Whisper: capture brute puis transcribe (plus lent)
                stt_start = monotonic_ms()
                chunks: list[bytes] = []
                async for chunk in microphone_stream(args.sample_rate, 1, args.chunk, args.max_seconds, args.device):
                    chunks.append(chunk)
                audio_bytes = b"".join(chunks)
                user_text = await recognition.transcribe(audio_bytes, sample_rate=args.sample_rate)
                stt_end = monotonic_ms()

            user_text = (user_text or "").strip()
            if not user_text:
                logger.warning("Aucune transcription obtenue.")
                continue

            logger.info("Vous: {}", user_text)
            if any(x in user_text.lower() for x in ["au revoir", "bye", "à bientôt", "quitter", "terminer"]):
                bye = "Au revoir. Fin du test."
                logger.info("VocalGuard: {}", bye)
                tts_audio = await synthesis.speak(bye)
                if tts_audio:
                    await play_audio_file(tts_audio)
                break

            ml_start = monotonic_ms()
            response_text, meta = pick_response(user_text, ml_brain, intents_payload, pattern_manager)
            ml_end = monotonic_ms()

            chosen_mode = meta.get("mode", "unknown")
            ml_ctx = meta.get("ml") or {}
            ml_best_intent = ml_ctx.get("best_intent")
            ml_best_score = float(ml_ctx.get("best_score") or 0.0)
            chosen_intent = None
            if chosen_mode == "intents":
                chosen_intent = (meta.get("intent") or {}).get("name")

            logger.info("Mode réponse: {}", chosen_mode)
            if ml_best_intent:
                logger.info("ML best: {} (score={})", ml_best_intent, ml_best_score)
            logger.info("VocalGuard: {}", response_text)

            tts_start = monotonic_ms()
            audio_path = await synthesis.speak(response_text)
            tts_end = monotonic_ms()

            play_start = monotonic_ms()
            if audio_path:
                await play_audio_file(audio_path)
            play_end = monotonic_ms()

            t1 = monotonic_ms()
            timings = {
                "stt": stt_end - stt_start,
                "ml_reply": ml_end - ml_start,
                "tts": tts_end - tts_start,
                "play": play_end - play_start,
                "total_turn": t1 - t0,
            }

            logger.info(
                "Latences: STT={} | ML/choix={} | TTS={} | Play={} | Total={}",
                format_ms(timings["stt"]),
                format_ms(timings["ml_reply"]),
                format_ms(timings["tts"]),
                format_ms(timings["play"]),
                format_ms(timings["total_turn"]),
            )

            metrics = TurnMetrics(
                turn_index=turn,
                started_at_ms=now_ms(),
                user_text=user_text,
                stt_engine=str(recognition.engine or ""),
                tts_engine=str(synthesis.engine or ""),
                ml_enabled=bool(ml_brain.enabled),
                ml_best_intent=ml_best_intent,
                ml_best_score=ml_best_score,
                chosen_mode=str(chosen_mode),
                chosen_intent=chosen_intent,
                response_text=response_text,
                timings_ms=timings,
            )
            all_turns.append(metrics)

            if log_fh:
                log_fh.write(json.dumps(asdict(metrics), ensure_ascii=False) + "\n")
                log_fh.flush()

        if all_turns:
            avg = {k: int(sum(t.timings_ms[k] for t in all_turns) / len(all_turns)) for k in all_turns[0].timings_ms.keys()}
            logger.info("")
            logger.info("=== Résumé (moyennes) ===")
            logger.info("Tours: {}", len(all_turns))
            logger.info("STT={} | ML/choix={} | TTS={} | Play={} | Total={}",
                        format_ms(avg["stt"]), format_ms(avg["ml_reply"]), format_ms(avg["tts"]), format_ms(avg["play"]), format_ms(avg["total_turn"]))
    finally:
        if log_fh:
            log_fh.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

