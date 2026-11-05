#!/usr/bin/env python3
"""
Lab bureau : micro → STT node15 → Qdrant node15 → WAV node14 → casque.

Usage:
  set VG_STT_URL=http://node15.lan:8100
  set VG_VOICE_API=http://node14.lan:8000/api/v1
  set VG_STT_TOKEN=<meme secret que node15>
  python desktop/outbound_commercial_lab.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import numpy as np
import sounddevice as sd
import tkinter as tk
from tkinter import messagebox, ttk

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from audio_core import (  # noqa: E402
    AUDIO_RATE,
    AudioDeviceHelper,
    pcm16_from_f32,
    prepare_studio_playback,
    read_wav_mono_f32,
)

DEFAULT_STT = os.environ.get("VG_STT_URL", "http://node15.lan:8100").rstrip("/")
DEFAULT_VOICE = os.environ.get(
    "VG_VOICE_API", "http://node14.lan:8000/api/v1"
).rstrip("/")
STT_TOKEN = (os.environ.get("VG_STT_TOKEN") or os.environ.get("STT_INTERNAL_TOKEN") or "").strip()
RECORD_SEC = float(os.environ.get("VG_COMM_RECORD_SEC", "4.0"))


def _stt_headers() -> Dict[str, str]:
    """Headers optionnels pour le service STT node15."""
    if STT_TOKEN:
        return {"X-STT-Token": STT_TOKEN}
    return {}


def _play_wav_file(path: Path, device: Optional[int]) -> None:
    """
    Lit un fichier WAV sur le peripherique de sortie choisi.

    @param path Fichier WAV local.
    @param device Index sounddevice ou None (defaut).
    """
    audio, file_rate = read_wav_mono_f32(path)
    audio, play_rate = prepare_studio_playback(audio, file_rate)
    sd.play(audio, play_rate, device=device)
    sd.wait()


class OutboundCommercialLabApp:
    """
    Boucle micro / STT / predict Qdrant (node15) / lecture WAV.

    @param stt_base URL service vocal node15 (:8100).
    @param voice_base URL API node14 pour servir les ``out_kb_*.wav``.
    """

    def __init__(
        self,
        stt_base: str = DEFAULT_STT,
        voice_base: str = DEFAULT_VOICE,
    ) -> None:
        self.stt_base = stt_base
        self.voice_base = voice_base
        self.stt_client = httpx.Client(
            base_url=self.stt_base,
            timeout=180.0,
            headers=_stt_headers(),
        )
        self.voice_client = httpx.Client(base_url=self.voice_base, timeout=120.0)

        self.recent_tags: List[str] = []
        self.recent_replies: List[str] = []
        self.last_predict: Optional[Dict[str, Any]] = None
        self.busy = False

        in_names, out_names, in_map, out_map = AudioDeviceHelper.list_devices()
        self.in_map = in_map
        self.out_map = out_map
        def_in, def_out = AudioDeviceHelper.default_labels(in_map, out_map)
        hs_in, hs_out = AudioDeviceHelper.find_headset_labels(in_map, out_map)

        self.root = tk.Tk()
        self.root.title("VocalGuard — commercial (STT + Qdrant node15)")
        self.root.geometry("720x580")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.status_var = tk.StringVar(value="Prêt.")
        self.engine_var = tk.StringVar(value="")
        self.reply_var = tk.StringVar(value="")

        frm = ttk.Frame(self.root, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frm, text="Périphériques").grid(row=0, column=0, sticky="w")
        self.in_combo = ttk.Combobox(frm, values=in_names, width=55)
        self.in_combo.grid(row=1, column=0, columnspan=2, sticky="ew", pady=2)
        self.in_combo.set(hs_in or def_in or (in_names[0] if in_names else ""))

        self.out_combo = ttk.Combobox(frm, values=out_names, width=55)
        self.out_combo.grid(row=2, column=0, columnspan=2, sticky="ew", pady=2)
        self.out_combo.set(hs_out or def_out or (out_names[0] if out_names else ""))

        ttk.Label(frm, text="Transcription prospect").grid(row=3, column=0, sticky="w", pady=(8, 0))
        self.text_box = tk.Text(frm, height=3, wrap=tk.WORD)
        self.text_box.grid(row=4, column=0, columnspan=2, sticky="ew")

        btn_row = ttk.Frame(frm)
        btn_row.grid(row=5, column=0, columnspan=2, sticky="ew", pady=8)
        ttk.Button(
            btn_row,
            text=f"Micro → réponse ({RECORD_SEC:.0f} s)",
            command=self._pipeline_async,
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_row, text="Ouverture Marie", command=self._opening_async).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        ttk.Button(btn_row, text="Réinitialiser fil", command=self._reset_thread).pack(
            side=tk.LEFT
        )

        ttk.Label(frm, text="Top Qdrant (debug)").grid(row=6, column=0, sticky="w")
        self.pred_list = tk.Listbox(frm, height=7, exportselection=False)
        self.pred_list.grid(row=7, column=0, columnspan=2, sticky="ew")

        ttk.Label(frm, text="Réponse choisie").grid(row=8, column=0, sticky="w", pady=(6, 0))
        ttk.Label(frm, textvariable=self.reply_var, wraplength=680).grid(
            row=9, column=0, columnspan=2, sticky="w"
        )
        ttk.Label(frm, textvariable=self.engine_var).grid(row=10, column=0, sticky="w")
        ttk.Label(frm, textvariable=self.status_var, wraplength=680).grid(
            row=11, column=0, columnspan=2, sticky="w", pady=(4, 0)
        )

        frm.columnconfigure(0, weight=1)

    def _out_device(self) -> Optional[int]:
        label = self.out_combo.get()
        return self.out_map.get(label)

    def _in_device(self) -> Optional[int]:
        label = self.in_combo.get()
        return self.in_map.get(label)

    def _set_status(self, msg: str) -> None:
        self.root.after(0, lambda: self.status_var.set(msg))

    def _run_bg(self, fn) -> None:
        if self.busy:
            return

        def wrapper() -> None:
            self.busy = True
            try:
                fn()
            except Exception as exc:
                self.root.after(0, lambda: messagebox.showerror("Erreur", str(exc)))
            finally:
                self.busy = False

        threading.Thread(target=wrapper, daemon=True).start()

    def _reset_thread(self) -> None:
        """Efface l'historique persona (suite d'appel)."""
        self.recent_tags.clear()
        self.recent_replies.clear()
        self.last_predict = None
        self.pred_list.delete(0, tk.END)
        self.reply_var.set("")
        self.engine_var.set("")
        self._set_status("Fil dialogue réinitialisé.")

    def _pipeline_async(self) -> None:
        self._run_bg(self._pipeline)

    def _pipeline(self) -> None:
        """
        Enregistre, transcrit, predict Qdrant node15, telecharge et joue le WAV.

        @raises RuntimeError Si une etape echoue.
        """
        dev = self._in_device()
        self._set_status(f"Micro {RECORD_SEC:.0f} s…")
        n = int(AUDIO_RATE * RECORD_SEC)
        rec = sd.rec(n, samplerate=AUDIO_RATE, channels=1, dtype="float32", device=dev)
        sd.wait()
        pcm = pcm16_from_f32(rec[:, 0])
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = Path(tmp.name)
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(AUDIO_RATE)
            wf.writeframes(pcm)
        try:
            self._set_status("STT Whisper (node15)…")
            with wav_path.open("rb") as f:
                files = {"file": ("prospect.wav", f, "audio/wav")}
                stt_res = self.stt_client.post(
                    "/v1/transcribe",
                    files=files,
                    params={"mode": os.environ.get("VG_STT_TRANSCRIBE_MODE", "live")},
                )
            if stt_res.status_code >= 400:
                raise RuntimeError(stt_res.text or f"STT HTTP {stt_res.status_code}")
            prospect = (stt_res.json().get("text") or "").strip()
            if not prospect:
                raise RuntimeError("STT vide — parlez plus fort ou plus près du micro.")
            self.root.after(0, lambda: self._fill_text(prospect))

            self._set_status("Qdrant commercial (node15)…")
            pred_res = self.stt_client.post(
                "/v1/outbound-commercial/predict",
                json={
                    "text": prospect,
                    "top_k": 8,
                    "recent_tags": self.recent_tags,
                    "recent_replies": self.recent_replies,
                },
            )
            if pred_res.status_code >= 400:
                raise RuntimeError(pred_res.text or f"Predict HTTP {pred_res.status_code}")
            data = pred_res.json()
            self._apply_predict(data)
            basename = str(data.get("wav_basename") or "").strip()
            if not basename:
                raise RuntimeError("Aucun intent / WAV pour cette phrase.")
            self._download_and_play(basename)
        finally:
            try:
                wav_path.unlink(missing_ok=True)
            except OSError:
                pass

    def _opening_async(self) -> None:
        self._run_bg(self._opening)

    def _opening(self) -> None:
        """Joue une variante d'ouverture (out_presentation) sans micro."""
        self._set_status("Ouverture out_presentation…")
        pred_res = self.stt_client.post(
            "/v1/outbound-commercial/predict",
            json={
                "text": "",
                "force_tag": "out_presentation",
                "variant_index": len(self.recent_replies) % 5,
                "recent_tags": self.recent_tags,
                "recent_replies": self.recent_replies,
            },
        )
        if pred_res.status_code >= 400:
            raise RuntimeError(pred_res.text or f"Predict HTTP {pred_res.status_code}")
        data = pred_res.json()
        self._apply_predict(data)
        basename = str(data.get("wav_basename") or "").strip()
        if not basename:
            raise RuntimeError("Basename presentation manquant.")
        self._download_and_play(basename)

    def _apply_predict(self, data: Dict[str, Any]) -> None:
        """Met a jour l'UI et l'historique dialogue."""
        self.last_predict = data
        tag = data.get("tag")
        reply = str(data.get("reply") or "")
        engine = str(data.get("engine") or "")
        score = float(data.get("score") or 0.0)
        tops = list(data.get("top_predictions") or [])

        if tag:
            self.recent_tags.append(str(tag))
            if reply:
                self.recent_replies.append(reply)
            if len(self.recent_tags) > 24:
                self.recent_tags = self.recent_tags[-24:]
            if len(self.recent_replies) > 24:
                self.recent_replies = self.recent_replies[-24:]

        def ui() -> None:
            self.pred_list.delete(0, tk.END)
            for i, row in enumerate(tops[:8]):
                t = str(row.get("tag") or "")
                s = float(row.get("score") or 0.0)
                self.pred_list.insert(tk.END, f"{i + 1}. {t} ({s:.2f})")
            self.reply_var.set(reply[:500] if reply else "—")
            self.engine_var.set(
                f"intent {tag} · score {score:.2f} · moteur {engine}" if tag else f"moteur {engine}"
            )

        self.root.after(0, ui)

    def _fill_text(self, text: str) -> None:
        self.text_box.delete("1.0", tk.END)
        self.text_box.insert("1.0", text)

    def _download_and_play(self, basename: str) -> None:
        """
        Telecharge le WAV sur node14 et le lit sur le casque.

        @param basename Sans extension (out_kb_…).
        """
        self._set_status(f"Téléchargement {basename}…")
        res = self.voice_client.get(
            f"/kb/outbound-commercial/voice/{basename}",
            timeout=90.0,
        )
        if res.status_code == 404:
            raise RuntimeError(f"WAV introuvable : {basename}")
        if res.status_code >= 400:
            raise RuntimeError(res.text or f"HTTP {res.status_code}")
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            path = Path(tmp.name)
            path.write_bytes(res.content)
        try:
            self._set_status(f"Lecture {basename}…")
            _play_wav_file(path, self._out_device())
            self._set_status("Terminé.")
        finally:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    def _on_close(self) -> None:
        try:
            self.stt_client.close()
        except Exception:
            pass
        try:
            self.voice_client.close()
        except Exception:
            pass
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    OutboundCommercialLabApp().run()


if __name__ == "__main__":
    main()
