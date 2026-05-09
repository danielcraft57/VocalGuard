"""Tests unitaires du paquet ``labcore.prospection_dialogue`` (sans modem ni Vosk)."""

import json
import random
import sys
import time
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from labaudio.intent_wav_pack import list_intent_variants_on_disk  # noqa: E402
from labcore.prospection_dialogue.audio_cache import build_prospection_audio_cache  # noqa: E402
from labcore.prospection_dialogue.chain import IntentChain  # noqa: E402
from labcore.prospection_dialogue.opening import infer_opening_tag_from_intent_json_paths  # noqa: E402
from labcore.prospection_dialogue.deadline import CallDeadline  # noqa: E402
from labcore.prospection_dialogue.events import DialogueEventBus, DialogueEventKind  # noqa: E402
from labcore.prospection_dialogue.opening import pick_opening_wav_from_pack  # noqa: E402
from labcore.prospection_dialogue.policy import build_dialogue_policy  # noqa: E402
from labcore.prospection_dialogue.snapshot import ConversationSnapshot  # noqa: E402
from labcore.prospection_dialogue.specification import DialogueContext, default_continue_dialogue_spec  # noqa: E402


def test_snapshot_record_reply() -> None:
    s = ConversationSnapshot()
    assert s.reply_turns_completed == 0
    s.record_reply_played("n1_exit", terminal=True)
    assert s.reply_turns_completed == 1
    assert s.played_intent_tags == ["n1_exit"]
    assert s.stop_dialogue is True


def test_infer_opening_tag_greeting_name_over_first(tmp_path: Path) -> None:
    j = tmp_path / "x.json"
    j.write_text(
        json.dumps(
            {
                "intents": [
                    {"tag": "n1_other", "patterns": ["a"], "responses": ["1"]},
                    {"tag": "greeting", "patterns": ["b"], "responses": ["2"]},
                ]
            }
        ),
        encoding="utf-8",
    )
    assert infer_opening_tag_from_intent_json_paths((j,)) == "greeting"


def test_infer_opening_tag_first_intent_if_no_greeting_name(tmp_path: Path) -> None:
    j = tmp_path / "n1.json"
    j.write_text(
        json.dumps(
            {
                "intents": [
                    {"tag": "n1_salutation_standard", "patterns": ["x"], "responses": ["1"]},
                    {"tag": "n1_other", "patterns": ["y"], "responses": ["2"]},
                ]
            }
        ),
        encoding="utf-8",
    )
    assert infer_opening_tag_from_intent_json_paths((j,)) == "n1_salutation_standard"


def test_infer_opening_tag_skips_empty_file_then_second(tmp_path: Path) -> None:
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"intents": []}), encoding="utf-8")
    j2 = tmp_path / "b.json"
    j2.write_text(
        json.dumps({"intents": [{"tag": "first_here", "patterns": ["z"], "responses": ["1"]}]}),
        encoding="utf-8",
    )
    assert infer_opening_tag_from_intent_json_paths((empty, j2)) == "first_here"


def _write_min_u8_wav(path: Path, n_frames: int = 160) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    silent = bytes([128]) * n_frames
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(1)
        wf.setframerate(8000)
        wf.writeframes(silent)


def test_intent_chain_from_payloads_matches_disk_load(tmp_path: Path) -> None:
    j = tmp_path / "i.json"
    j.write_text(
        json.dumps(
            {"intents": [{"tag": "t_one", "patterns": ["ok"], "responses": ["a"]}]},
        ),
        encoding="utf-8",
    )
    data = json.loads(j.read_text(encoding="utf-8"))
    pack = tmp_path / "pack"
    _write_min_u8_wav(pack / "t_one_01.wav")
    a = IntentChain((j,), terminal_tags=frozenset())
    b = IntentChain.from_payloads([(j, data)], terminal_tags=frozenset())
    rng = random.Random(0)
    ra = a.match("c'est ok", pack, rng)
    rb = b.match("c'est ok", pack, rng)
    assert ra is not None and rb is not None
    assert ra.intent_tag == rb.intent_tag
    assert ra.wav_path == rb.wav_path


def test_build_prospection_audio_cache_greeting_and_intent(tmp_path: Path) -> None:
    j = tmp_path / "intents.json"
    j.write_text(
        json.dumps(
            {"intents": [{"tag": "t_tag", "patterns": ["oui"], "responses": ["x"]}]},
        ),
        encoding="utf-8",
    )
    pack = tmp_path / "p"
    pack.mkdir()
    _write_min_u8_wav(pack / "greet.wav")
    _write_min_u8_wav(pack / "t_tag_01.wav")
    cache = build_prospection_audio_cache(
        pack_dir=pack,
        greeting_wav=pack / "greet.wav",
        intent_json_paths=(j,),
    )
    assert cache.pcm_u8_for_path(pack / "greet.wav") is not None
    assert len(cache.pcm_u8_for_path(pack / "greet.wav") or b"") > 0
    assert cache.pcm_u8_for_path(pack / "t_tag_01.wav") is not None
    assert len(cache.intent_payloads) == 1


def test_intent_chain_first_file_priority(tmp_path: Path) -> None:
    """Le premier JSON « gagne » si deux intents pourraient matcher."""
    low = tmp_path / "low.json"
    high = tmp_path / "high.json"
    low.write_text(
        json.dumps(
            {
                "intents": [
                    {"tag": "late", "patterns": ["bonjour"], "responses": ["x"]},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    high.write_text(
        json.dumps(
            {
                "intents": [
                    {"tag": "early", "patterns": ["bonjour"], "responses": ["y"]},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    pack = tmp_path / "pack"
    pack.mkdir()
    (pack / "early_01.wav").write_bytes(b"RIFF")
    (pack / "late_01.wav").write_bytes(b"RIFF")

    chain = IntentChain((high, low), terminal_tags=frozenset())
    rng = random.Random(0)
    out = chain.match("bonjour tout le monde", pack, rng)
    assert out is not None
    assert out.intent_tag == "early"


def test_list_intent_variants_on_disk_order(tmp_path: Path) -> None:
    pack = tmp_path / "p"
    pack.mkdir()
    (pack / "n1_test_01.wav").write_text("a", encoding="utf-8")
    (pack / "n1_test_03.wav").write_text("b", encoding="utf-8")
    v = list_intent_variants_on_disk(pack, "n1_test")
    assert [i for i, _ in v] == [1, 3]


def test_pick_opening_random_is_stable_with_seed(tmp_path: Path) -> None:
    pack = tmp_path / "p2"
    pack.mkdir()
    (pack / "n1_salutation_standard_01.wav").write_bytes(b"x")
    (pack / "n1_salutation_standard_02.wav").write_bytes(b"y")
    a = pick_opening_wav_from_pack(pack, "n1_salutation_standard", random.Random(42))
    b = pick_opening_wav_from_pack(pack, "n1_salutation_standard", random.Random(42))
    assert a == b


def test_call_deadline_remaining_and_expired() -> None:
    d = CallDeadline(0.15)
    assert not d.expired()
    assert d.remaining_sec() > 0.0
    time.sleep(0.2)
    assert d.expired()
    assert d.remaining_sec() == 0.0


def test_policy_truncates_listen_against_deadline(tmp_path: Path) -> None:
    j = tmp_path / "i.json"
    j.write_text(json.dumps({"intents": [{"tag": "a", "patterns": ["x"], "responses": ["y"]}]}), encoding="utf-8")
    pack = tmp_path / "pk"
    pack.mkdir()
    (pack / "a_01.wav").write_bytes(b"x")
    pol = build_dialogue_policy(
        intent_json_paths=(j,),
        pack_dir=pack,
        max_reply_turns=3,
        terminal_tags=frozenset(),
        rng_seed=0,
        listen_sec_per_turn=30.0,
        wall_budget_sec=100.0,
        attach_default_log_sink=False,
    )
    dl = CallDeadline(0.8)
    eff = pol.effective_listen_seconds(dl)
    assert eff <= 0.8 + 1e-6
    assert eff >= 0.5


def test_default_spec_blocks_after_stop() -> None:
    snap = ConversationSnapshot()
    snap.stop_dialogue = True
    spec = default_continue_dialogue_spec()
    ctx = DialogueContext(next_turn_index=1, max_turns=5, deadline=None)
    assert not spec.is_satisfied_by(snap, ctx)


def test_event_bus_delivers_to_subscriber() -> None:
    seen: list[str] = []
    bus = DialogueEventBus()

    def h(ev):
        seen.append(ev.kind)

    bus.subscribe(h)
    bus.emit(DialogueEventKind.TURN_STT_START, turn=1)
    assert seen == [DialogueEventKind.TURN_STT_START]
