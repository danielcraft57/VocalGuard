#!/usr/bin/env python3
"""
VocalGuard Commercial Studio — GUI PySide6 (micro, STT, Qdrant, lecture WAV).

Usage dev:
  pip install PySide6
  python desktop/outbound_studio.py

Build exe:
  powershell -File scripts/build_outbound_commercial_studio.ps1
"""

from __future__ import annotations

import os
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import numpy as np

# Racine repo pour imports desktop.*
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from PySide6.QtCore import (  # noqa: E402
    Qt,
    QThread,
    QTimer,
    Signal,
)
from PySide6.QtGui import QIcon  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from desktop.audio_core import AudioDeviceHelper  # noqa: E402
from desktop.commercial_pipeline import CommercialPipeline, PipelineResult  # noqa: E402
from desktop.live_listen import LiveListenWorker, LiveSttChunkWorker  # noqa: E402
from desktop.studio_env import load_studio_env, persist_studio_env  # noqa: E402
from desktop.studio_recording import FilteredWavArchive  # noqa: E402
from desktop.studio_ui_material import (  # noqa: E402
    CallAvatarWidget,
    ChatTimelineWidget,
    CollapsibleSection,
    GradientHeroFrame,
    LogConsoleWidget,
    MotionWaveform,
    apply_card_shadow,
    material_stylesheet,
)

RECORD_SEC = 4.0
STEP_LABELS = ("Capture", "Transcription", "Intent", "Voix", "Lecture")


def _app_icon_path() -> Path:
    """
    Chemin de l'icone (dev ou bundle PyInstaller).

    @returns Fichier .ico.
    """
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", ""))
        bundled = base / "desktop" / "assets" / "commercial_studio.ico"
        if bundled.is_file():
            return bundled
    local = Path(__file__).resolve().parent / "assets" / "commercial_studio.ico"
    return local


class PipelineWorker(QThread):
    """
    Thread : enregistrement → STT → predict → WAV → lecture.

    @param pipeline Client commercial partagé (un tour à la fois).
    """

    level = Signal(float)
    step = Signal(int)
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        pipeline: CommercialPipeline,
        in_dev: Optional[int],
        out_dev: Optional[int],
        *,
        opening: bool = False,
        record_sec: float = RECORD_SEC,
        precorded_mono: Optional[np.ndarray] = None,
    ) -> None:
        super().__init__()
        self.pipeline = pipeline
        self.in_dev = in_dev
        self.out_dev = out_dev
        self.opening = opening
        self.record_sec = record_sec
        self.precorded_mono = precorded_mono
        self._wav_tmp: Optional[Path] = None

    def run(self) -> None:
        try:
            if self.opening:
                self.step.emit(2)
                result = self.pipeline.predict(
                    "",
                    force_tag="out_presentation",
                    variant_index=len(self.pipeline.recent_replies) % 5,
                )
                self.step.emit(3)
            else:
                self.step.emit(0)

                def _lvl(v: float) -> None:
                    self.level.emit(v)

                if self.precorded_mono is not None and len(self.precorded_mono) > 0:
                    mono = self.precorded_mono
                    self.level.emit(0.5)
                else:
                    mono = self.pipeline.record_pcm(
                        self.record_sec, self.in_dev, level_callback=_lvl
                    )
                self.step.emit(1)
                text = self.pipeline.transcribe_pcm(mono)
                self.step.emit(2)
                result = self.pipeline.predict(text)
                self.step.emit(3)

            basename = str(result.wav_basename or "").strip()
            if not basename:
                raise RuntimeError("Aucun WAV pour cette réponse.")
            self._wav_tmp = self.pipeline.download_wav(basename)
            self.step.emit(4)

            def _play_lvl(v: float) -> None:
                self.level.emit(v)

            self.pipeline.play_wav(self._wav_tmp, self.out_dev, level_callback=_play_lvl)
            self.finished_ok.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            if self._wav_tmp is not None:
                try:
                    self._wav_tmp.unlink(missing_ok=True)
                except OSError:
                    pass


class CommercialStudioWindow(QMainWindow):
    """Fenêtre principale Commercial Studio."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("VocalGuard — Commercial Studio")
        icon_file = _app_icon_path()
        if icon_file.is_file():
            self.setWindowIcon(QIcon(str(icon_file)))
        self.setMinimumSize(1040, 760)
        self.resize(1180, 880)
        load_studio_env()
        self.pipeline = CommercialPipeline()
        self.wav_archive = FilteredWavArchive()
        self.pipeline.attach_wav_archive(self.wav_archive)
        self.worker: Optional[PipelineWorker] = None
        self.live_worker: Optional[LiveListenWorker] = None
        self.live_stt_worker: Optional[LiveSttChunkWorker] = None
        self._live_mode = False
        self._resume_live_after = False
        self._live_start_pending = False
        self._step_labels: List[QLabel] = []
        self.in_map: dict[str, int] = {}
        self.out_map: dict[str, int] = {}

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(20)

        # Barre d'app
        header = QHBoxLayout()
        title_block = QVBoxLayout()
        t1 = QLabel("Marie")
        t1.setObjectName("AppTitle")
        t2 = QLabel("Appel commercial · simulation bureau")
        t2.setObjectName("AppSubtitle")
        title_block.addWidget(t1)
        title_block.addWidget(t2)
        header.addLayout(title_block)
        header.addStretch()
        self.lbl_state_pill = QLabel("Pret")
        self.lbl_state_pill.setObjectName("StatePill")
        header.addWidget(self.lbl_state_pill)
        self.btn_reset = QPushButton("Nouveau fil")
        self.btn_reset.setObjectName("IconGhost")
        self.btn_reset.clicked.connect(self._reset_dialogue)
        header.addWidget(self.btn_reset)
        layout.addLayout(header)

        steps_row = QHBoxLayout()
        steps_row.setSpacing(6)
        for name in STEP_LABELS:
            lb = QLabel(name)
            lb.setObjectName("StepChipIdle")
            self._step_labels.append(lb)
            steps_row.addWidget(lb)
        steps_row.addStretch()
        layout.addLayout(steps_row)

        split_main = QSplitter(Qt.Orientation.Horizontal)
        split_main.setChildrenCollapsible(False)
        self._split_main = split_main

        hero = GradientHeroFrame()
        apply_card_shadow(hero)
        hero_l = QVBoxLayout(hero)
        hero_l.setContentsMargins(24, 24, 24, 24)
        hero_l.setSpacing(14)

        avatar_row = QHBoxLayout()
        avatar_row.addStretch()
        self.avatar = CallAvatarWidget()
        avatar_row.addWidget(self.avatar)
        avatar_row.addStretch()
        hero_l.addLayout(avatar_row)

        self.wave = MotionWaveform()
        hero_l.addWidget(self.wave)

        self.lbl_status = QLabel("Appuyez sur Lancer l'appel pour simuler un decroche.")
        self.lbl_status.setObjectName("AppSubtitle")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_l.addWidget(self.lbl_status)

        actions = QHBoxLayout()
        actions.setSpacing(12)
        actions.addStretch()
        self.btn_record = QPushButton("Tour 4 s")
        self.btn_record.setObjectName("OutlinedBtn")
        self.btn_record.setToolTip("Un enregistrement fixe (hors mode appel).")
        self.btn_record.clicked.connect(self._run_mic)
        actions.addWidget(self.btn_record)
        self.btn_live = QPushButton("Lancer l'appel")
        self.btn_live.setObjectName("FabCall")
        self.btn_live.setCheckable(True)
        self.btn_live.setToolTip(
            "Micro ouvert + Marie decroche avec l'ouverture commerciale."
        )
        self.btn_live.toggled.connect(self._toggle_live_mode)
        actions.addWidget(self.btn_live)
        self.btn_cancel = QPushButton("Annuler")
        self.btn_cancel.setObjectName("TextBtn")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setToolTip("Interrompt la lecture en cours.")
        self.btn_cancel.clicked.connect(self._cancel_pipeline)
        actions.addWidget(self.btn_cancel)
        actions.addStretch()
        hero_l.addLayout(actions)
        hero_l.addStretch(1)
        split_main.addWidget(hero)

        split_right = QSplitter(Qt.Orientation.Vertical)
        split_right.setChildrenCollapsible(False)
        self._split_right = split_right

        chat_card = QFrame()
        chat_card.setObjectName("PanelCard")
        apply_card_shadow(chat_card, blur=32, y=8)
        chat_card_l = QVBoxLayout(chat_card)
        chat_card_l.setContentsMargins(16, 14, 16, 14)
        chat_cap = QLabel("Conversation")
        chat_cap.setObjectName("CardCaption")
        chat_card_l.addWidget(chat_cap)
        self.chat = ChatTimelineWidget()
        chat_card_l.addWidget(self.chat, 1)
        split_right.addWidget(chat_card)

        log_card = QFrame()
        log_card.setObjectName("PanelCard")
        apply_card_shadow(log_card, blur=28, y=6)
        log_card_l = QVBoxLayout(log_card)
        log_card_l.setContentsMargins(16, 10, 16, 12)
        self.logs = LogConsoleWidget()
        log_card_l.addWidget(self.logs, 1)
        split_right.addWidget(log_card)

        split_right.setStretchFactor(0, 3)
        split_right.setStretchFactor(1, 2)
        split_main.addWidget(split_right)
        split_main.setStretchFactor(0, 2)
        split_main.setStretchFactor(1, 3)
        layout.addWidget(split_main, 1)

        settings_wrap = QWidget()
        settings_l = QVBoxLayout(settings_wrap)
        settings_l.setContentsMargins(0, 0, 0, 0)
        settings_l.setSpacing(12)

        dev_row = QHBoxLayout()
        dev_row.addWidget(QLabel("Micro"))
        self.combo_in = QComboBox()
        dev_row.addWidget(self.combo_in, 1)
        dev_row.addWidget(QLabel("Sortie audio"))
        self.combo_out = QComboBox()
        dev_row.addWidget(self.combo_out, 1)
        self.btn_refresh_dev = QPushButton("Actualiser")
        self.btn_refresh_dev.setObjectName("OutlinedBtn")
        self.btn_refresh_dev.clicked.connect(self._refresh_devices)
        dev_row.addWidget(self.btn_refresh_dev)
        settings_l.addLayout(dev_row)

        gain_row = QHBoxLayout()
        gain_row.addWidget(QLabel("Gain micro"))
        self.slider_mic = QSlider(Qt.Orientation.Horizontal)
        self.slider_mic.setRange(25, 250)
        self.slider_mic.setValue(int(self.pipeline.mic_gain * 100))
        self.slider_mic.setToolTip("Sensibilite micro avant STT (25 % a 250 %).")
        self.slider_mic.valueChanged.connect(self._on_mic_gain_changed)
        self.slider_mic.sliderReleased.connect(self._persist_audio_prefs)
        gain_row.addWidget(self.slider_mic, 2)
        self.lbl_mic_gain = QLabel(self._mic_gain_label())
        self.lbl_mic_gain.setMinimumWidth(44)
        gain_row.addWidget(self.lbl_mic_gain)
        gain_row.addWidget(QLabel("Volume Marie"))
        self.slider_vol = QSlider(Qt.Orientation.Horizontal)
        self.slider_vol.setRange(5, 100)
        self.slider_vol.setValue(int(self.pipeline.play_gain * 100))
        self.slider_vol.setToolTip("Volume lecture reponses WAV (5 % a 100 %).")
        self.slider_vol.valueChanged.connect(self._on_play_gain_changed)
        self.slider_vol.sliderReleased.connect(self._persist_audio_prefs)
        gain_row.addWidget(self.slider_vol, 2)
        self.lbl_vol_gain = QLabel(self._vol_gain_label())
        self.lbl_vol_gain.setMinimumWidth(44)
        gain_row.addWidget(self.lbl_vol_gain)
        settings_l.addLayout(gain_row)

        tools_row = QHBoxLayout()
        self.btn_test = QPushButton("Test casque")
        self.btn_test.setObjectName("OutlinedBtn")
        self.btn_test.clicked.connect(self._test_hp)
        tools_row.addWidget(self.btn_test)
        self.btn_test_mic = QPushButton("Test micro")
        self.btn_test_mic.setObjectName("OutlinedBtn")
        self.btn_test_mic.clicked.connect(self._test_mic)
        tools_row.addWidget(self.btn_test_mic)
        self.chk_noise_gate = QPushButton("Filtre ambiance")
        self.chk_noise_gate.setObjectName("ToggleChip")
        self.chk_noise_gate.setCheckable(True)
        self.chk_noise_gate.setChecked(
            (os.environ.get("VG_STUDIO_NOISE_GATE") or "1").strip().lower()
            not in ("0", "false", "off")
        )
        self.chk_noise_gate.setToolTip(
            "Reduit TV, musique et bruit lointain (casque proche recommande)."
        )
        self.chk_noise_gate.toggled.connect(self._on_noise_gate_toggled)
        tools_row.addWidget(self.chk_noise_gate)
        self.btn_open = QPushButton("Ouverture seule")
        self.btn_open.setObjectName("OutlinedBtn")
        self.btn_open.setToolTip("Phrase d'accueil sans mode appel.")
        self.btn_open.clicked.connect(self._run_opening)
        tools_row.addWidget(self.btn_open)
        self.btn_sync_stt = QPushButton("Sync STT")
        self.btn_sync_stt.setObjectName("OutlinedBtn")
        self.btn_sync_stt.setToolTip(
            "Recupere le token HTTP node15 depuis node14."
        )
        self.btn_sync_stt.clicked.connect(self._sync_stt_token)
        tools_row.addWidget(self.btn_sync_stt)
        tools_row.addStretch()
        settings_l.addLayout(tools_row)

        self.lbl_endpoints = QLabel("")
        self.lbl_endpoints.setObjectName("MetaText")
        self.lbl_endpoints.setWordWrap(True)
        settings_l.addWidget(self.lbl_endpoints)
        self.lbl_recordings = QLabel("")
        self.lbl_recordings.setObjectName("MetaText")
        self.lbl_recordings.setWordWrap(True)
        settings_l.addWidget(self.lbl_recordings)

        self.panel_settings = CollapsibleSection("Parametres audio et technique")
        self.panel_settings.set_content_widget(settings_wrap)
        layout.addWidget(self.panel_settings)

        self._refresh_devices()
        self.setStyleSheet(material_stylesheet())
        self._show_endpoints_hint()
        self._apply_live_chrome(False)
        self._log("Commercial Studio pret.")
        self._refresh_recordings_hint()
        self.chat.add_system(
            "Simulation d'appel sortant : lancez l'appel ou un tour 4 s."
        )
        QTimer.singleShot(0, self._apply_split_sizes)

    def _apply_split_sizes(self) -> None:
        """Proportions initiales panneaux (hero / chat / logs)."""
        if hasattr(self, "_split_main"):
            self._split_main.setSizes([400, max(520, self.width() - 420)])
        if hasattr(self, "_split_right"):
            self._split_right.setSizes([420, 240])

    def _chat_time_meta(self, extra: str) -> str:
        """Horodatage court pour sous-titre de bulle."""
        ts = datetime.now().strftime("%H:%M")
        if extra:
            return f"{ts} · {extra}"
        return ts

    def _log(self, message: str, *, level: str = "info") -> None:
        """
        Ecrit dans le journal UI.

        @param message Ligne de log.
        @param level info | warn | error | debug.
        """
        if level not in ("info", "warn", "error", "debug"):
            level = "info"
        self.logs.append(message, level=level)  # type: ignore[arg-type]

    def _refresh_recordings_hint(self) -> None:
        """Affiche le dossier WAV filtre de la session."""
        if self.wav_archive.session_dir is not None:
            self.lbl_recordings.setText(
                f"WAV apres filtre : {self.wav_archive.session_dir} "
                "(desactiver : VG_STUDIO_SAVE_FILTERED_WAV=0)"
            )

    def _show_endpoints_hint(self) -> None:
        """URLs effectives dans le panneau parametres."""
        self.lbl_endpoints.setText(
            f"API {self.pipeline.voice_api} · STT {self.pipeline.stt_url}"
        )
        if not self._live_mode:
            self.lbl_status.setText(
                "Lancer l'appel : micro ouvert tout de suite, Marie dit bonjour."
            )

    def _set_state_pill(self, text: str, *, live: bool = False, busy: bool = False) -> None:
        """
        Met a jour le badge d'etat en haut (Material pill).

        @param text Libelle court.
        @param live Style appel en cours.
        @param busy Style traitement.
        """
        self.lbl_state_pill.setText(text)
        if live:
            name = "StatePillLive"
        elif busy:
            name = "StatePillBusy"
        else:
            name = "StatePill"
        self.lbl_state_pill.setObjectName(name)
        self.lbl_state_pill.style().unpolish(self.lbl_state_pill)
        self.lbl_state_pill.style().polish(self.lbl_state_pill)

    def _apply_live_chrome(self, live: bool) -> None:
        """FAB appel / raccrocher + avatar pulse."""
        self.avatar.set_live(live)
        if live:
            self.btn_live.setObjectName("FabHangup")
            self.btn_live.setText("Raccrocher")
            self._set_state_pill("En appel", live=True)
        else:
            self.btn_live.setObjectName("FabCall")
            self.btn_live.setText("Lancer l'appel")
            self._set_state_pill("Pret")
        self.btn_live.style().unpolish(self.btn_live)
        self.btn_live.style().polish(self.btn_live)

    def _mic_gain_label(self) -> str:
        """Texte pourcent gain micro."""
        return f"{self.slider_mic.value()} %"

    def _vol_gain_label(self) -> str:
        """Texte pourcent volume lecture."""
        return f"{self.slider_vol.value()} %"

    def _on_mic_gain_changed(self, value: int) -> None:
        """Applique le gain micro au pipeline."""
        self.pipeline.mic_gain = max(0.25, min(2.5, value / 100.0))
        self.lbl_mic_gain.setText(self._mic_gain_label())

    def _on_play_gain_changed(self, value: int) -> None:
        """Applique le volume lecture Marie."""
        self.pipeline.play_gain = max(0.05, min(1.0, value / 100.0))
        self.lbl_vol_gain.setText(self._vol_gain_label())

    def _on_noise_gate_toggled(self, enabled: bool) -> None:
        """Active/desactive le filtre TV/musique (studio.env)."""
        os.environ["VG_STUDIO_NOISE_GATE"] = "1" if enabled else "0"
        try:
            persist_studio_env({"VG_STUDIO_NOISE_GATE": os.environ["VG_STUDIO_NOISE_GATE"]})
        except OSError:
            pass

    def _persist_audio_prefs(self) -> None:
        """Sauvegarde les curseurs dans studio.env."""
        try:
            path = persist_studio_env(
                {
                    "VG_STUDIO_MIC_GAIN": f"{self.pipeline.mic_gain:.2f}",
                    "VG_STUDIO_PLAY_GAIN": f"{self.pipeline.play_gain:.2f}",
                }
            )
            self.lbl_status.setText(f"Audio enregistre ({path.name}).")
        except OSError as exc:
            self.lbl_status.setText(f"Impossible d'ecrire studio.env : {exc}")

    def _test_mic(self) -> None:
        """Test niveau micro 2,5 s (sans STT)."""
        if self.worker and self.worker.isRunning():
            return
        self.lbl_status.setText("Test micro — parlez…")
        self.wave.set_pulse(0.6)
        AudioDeviceHelper.probe_microphone(
            self._device_in(),
            lambda v: self.wave.push_level(v),
            lambda msg: self.lbl_status.setText(msg),
            mic_gain=self.pipeline.mic_gain,
        )

    def _sync_stt_token(self) -> None:
        """Recharge token STT depuis node14 ou studio.env."""
        from desktop.commercial_pipeline import _stt_token_from_env

        self.pipeline.reload_stt_client()
        if _stt_token_from_env():
            self.lbl_status.setText("Token STT synchronise (node14 / studio.env).")
            self._log("Token STT synchronise.")
        else:
            self.lbl_status.setText(
                "Pas de token STT. Mettez a jour node14 ou studio.env (VG_STT_TOKEN)."
            )
            self._log("Sync STT : aucun token trouve.", level="warn")

    def _refresh_devices(self) -> None:
        """Recharge la liste PortAudio (Bluetooth change souvent d'index)."""
        prev_in = self.combo_in.currentData()
        prev_out = self.combo_out.currentData()
        in_names, out_names, in_map, out_map = AudioDeviceHelper.list_devices()
        self.in_map = in_map
        self.out_map = out_map
        def_in, def_out = AudioDeviceHelper.default_labels(in_map, out_map)
        hs_in, hs_out = AudioDeviceHelper.find_headset_labels(in_map, out_map)

        self.combo_in.blockSignals(True)
        self.combo_out.blockSignals(True)
        self.combo_in.clear()
        self.combo_out.clear()
        for label in in_names:
            self.combo_in.addItem(label, in_map[label])
        for label in out_names:
            self.combo_out.addItem(label, out_map[label])

        def _pick(combo: QComboBox, prev, preferred, fallback) -> None:
            if prev is not None:
                idx = combo.findData(prev)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                    return
            if preferred:
                idx = combo.findText(preferred)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                    return
            if fallback:
                idx = combo.findText(fallback)
                if idx >= 0:
                    combo.setCurrentIndex(idx)

        _pick(self.combo_in, prev_in, hs_in, def_in)
        _pick(self.combo_out, prev_out, hs_out, def_out)
        self.combo_in.blockSignals(False)
        self.combo_out.blockSignals(False)

    def _device_in(self) -> Optional[int]:
        data = self.combo_in.currentData()
        if data is not None:
            try:
                return int(data)
            except (TypeError, ValueError):
                pass
        return self.in_map.get(self.combo_in.currentText())

    def _device_out(self) -> Optional[int]:
        data = self.combo_out.currentData()
        if data is not None:
            try:
                return int(data)
            except (TypeError, ValueError):
                pass
        return self.out_map.get(self.combo_out.currentText())

    def _set_step(self, index: int) -> None:
        """Met en avant l'étape pipeline 0..4."""
        if 0 <= index < len(STEP_LABELS):
            self._log(f"Etape : {STEP_LABELS[index]}", level="debug")
        self.avatar.set_speaking(index == 4)
        for i, lb in enumerate(self._step_labels):
            if i < index:
                lb.setObjectName("StepChipDone")
            elif i == index:
                lb.setObjectName("StepChipActive")
            else:
                lb.setObjectName("StepChipIdle")
            lb.style().unpolish(lb)
            lb.style().polish(lb)

    def _reset_steps(self) -> None:
        for lb in self._step_labels:
            lb.setObjectName("StepChipIdle")
            lb.style().unpolish(lb)
            lb.style().polish(lb)

    def _busy(self, value: bool) -> None:
        self.btn_record.setEnabled(not value and not self._live_mode)
        self.btn_open.setEnabled(not value and not self._live_mode)
        self.btn_reset.setEnabled(not value)
        self.btn_cancel.setEnabled(value)
        if self._live_mode:
            self.btn_live.setEnabled(True)
        else:
            self.btn_live.setEnabled(not value)
        if value:
            self._set_state_pill("Traitement…", busy=True)
        elif self._live_mode:
            self._set_state_pill("En appel", live=True)
        else:
            self._set_state_pill("Pret")

    def _stop_live_listen(self) -> None:
        """Arrete le thread micro live et la file STT chunks."""
        if self.live_stt_worker is not None:
            self.live_stt_worker.stop()
            self.live_stt_worker.wait(5000)
            self.live_stt_worker = None
        if self.live_worker is not None:
            self.live_worker.stop()
            self.live_worker.wait(3000)
            self.live_worker = None

    def _start_live_micro(self) -> None:
        """Demarre micro + chunks STT (des le debut de l'appel live)."""
        if not self._live_mode or not self.btn_live.isChecked():
            return
        if self.live_worker is not None:
            return
        self.live_stt_worker = LiveSttChunkWorker(self.pipeline)
        self.live_stt_worker.partial_text.connect(self._on_live_partial_stt)
        self.live_stt_worker.failed.connect(self._on_stt_chunk_fail)
        self.live_stt_worker.start()
        self.live_worker = LiveListenWorker(
            self._device_in(),
            mic_gain=self.pipeline.mic_gain,
            pipeline=self.pipeline,
        )
        self.live_worker.level.connect(self._on_level)
        self.live_worker.stt_chunk.connect(self._on_live_stt_chunk)
        self.live_worker.utterance.connect(self._on_live_utterance)
        self.live_worker.status.connect(self._on_live_status)
        self.live_worker.failed.connect(self._on_live_failed)
        self.live_worker.finished.connect(self._on_live_thread_finished)
        self.live_worker.start()
        self.lbl_status.setText("A vous — parlez (fin de phrase = pause).")

    def _toggle_live_mode(self, enabled: bool) -> None:
        """Appel sortant : micro ouvert + ouverture Marie en parallele."""
        self._live_mode = enabled
        if enabled:
            if self.worker and self.worker.isRunning():
                self.btn_live.blockSignals(True)
                self.btn_live.setChecked(False)
                self.btn_live.blockSignals(False)
                self._live_mode = False
                return
            self.btn_record.setEnabled(False)
            self.btn_open.setEnabled(False)
            self._live_start_pending = True
            self._apply_live_chrome(True)
            self.chat.clear()
            self.chat.add_system("Nouvel appel — conversation effacee.")
            self.lbl_status.setText("Decroche… micro actif, Marie vous salue.")
            self._log("Appel sortant demarre (micro + ouverture).")
            self._start_live_micro()
            self._run_pipeline(opening=True)
        else:
            self._live_start_pending = False
            self._stop_live_listen()
            self._apply_live_chrome(False)
            self._log("Appel raccroche.")
            self._show_endpoints_hint()

    def _on_live_thread_finished(self) -> None:
        if self._live_mode and self.btn_live.isChecked():
            self.btn_live.blockSignals(True)
            self.btn_live.setChecked(False)
            self.btn_live.blockSignals(False)
            self._live_mode = False
            self._apply_live_chrome(False)

    def _on_live_failed(self, msg: str) -> None:
        self.lbl_status.setText(f"Live : {msg}")
        self._log(f"Live interrompu : {msg}", level="error")
        self.btn_live.blockSignals(True)
        self.btn_live.setChecked(False)
        self.btn_live.blockSignals(False)
        self._live_mode = False
        self._apply_live_chrome(False)
        self._stop_live_listen()

    def _on_live_stt_chunk(self, mono: object) -> None:
        """Envoie un chunk audio a Whisper (file serialisee)."""
        if not isinstance(mono, np.ndarray) or self.live_stt_worker is None:
            return
        self.live_stt_worker.submit(mono)

    def _on_stt_chunk_fail(self, msg: str) -> None:
        """Erreur STT sur un chunk live."""
        self.lbl_status.setText(f"Chunk STT : {msg}")
        self._log(f"Chunk STT : {msg}", level="warn")

    def _on_live_status(self, msg: str) -> None:
        """Statut thread micro live."""
        self.lbl_status.setText(msg)
        self._log(msg, level="debug")

    def _on_live_partial_stt(self, text: str) -> None:
        """Affiche le texte cumule des chunks Whisper."""
        self.chat.set_draft_user(text or "")
        self._set_step(1)

    def _on_live_utterance(self, mono: object) -> None:
        """Phrase detectee : STT → Qdrant → Marie (micro en pause)."""
        if not isinstance(mono, np.ndarray):
            return
        if self.worker and self.worker.isRunning():
            return
        if self.live_worker is not None:
            self.live_worker.pause()
        self.lbl_status.setText("Whisper (live)…")
        self._log("Fin de phrase detectee — pipeline live.")
        self._run_pipeline(
            opening=False,
            precorded_mono=mono,
            resume_live_after=True,
        )

    def _resume_live_if_needed(self) -> None:
        if self.live_stt_worker is not None:
            self.live_stt_worker.clear_session()
        if self.live_worker is not None and self._live_mode:
            self.live_worker.resume()
            self.lbl_status.setText("Ecoute live — parlez.")
            self.chat.clear_draft()
            self._log("Micro live repris apres reponse Marie.")

    def _cancel_pipeline(self) -> None:
        """Debloque un tour bloque sur la sortie audio."""
        self.pipeline.stop_playback()
        self.lbl_status.setText("Annulation…")
        self._log("Annulation lecture / tour.", level="warn")

    def _run_mic(self) -> None:
        if self._live_mode:
            return
        if self.worker and self.worker.isRunning():
            return
        self.wave.set_pulse(1.0)
        self._run_pipeline(opening=False)

    def _run_opening(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        if self._live_mode:
            return
        self._run_pipeline(opening=True)

    def _run_pipeline(
        self,
        *,
        opening: bool,
        precorded_mono: Optional[np.ndarray] = None,
        resume_live_after: bool = False,
    ) -> None:
        self._resume_live_after = resume_live_after
        self._reset_steps()
        self._busy(True)
        if self._live_mode and opening:
            self.lbl_status.setText("Appel — micro actif, ouverture Marie…")
        elif not self._live_mode:
            self.lbl_status.setText("En cours…")
        kind = "ouverture" if opening else "tour"
        self._log(f"Pipeline {kind} demarre.")
        self.worker = PipelineWorker(
            self.pipeline,
            self._device_in(),
            self._device_out(),
            opening=opening,
            precorded_mono=precorded_mono,
        )
        self.worker.level.connect(self._on_level)
        self.worker.step.connect(self._set_step)
        self.worker.finished_ok.connect(self._on_ok)
        self.worker.failed.connect(self._on_fail)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

    def _on_worker_finished(self) -> None:
        self._busy(False)
        self.avatar.set_speaking(False)
        if self._live_start_pending and self._live_mode:
            self._live_start_pending = False
        if self._resume_live_after:
            self._resume_live_after = False
            self._resume_live_if_needed()

    def _on_level(self, v: float) -> None:
        self.wave.push_level(v)
        self.wave.set_pulse(max(self.wave.current_pulse(), v))
        self.avatar.set_energy(v)

    def _on_ok(self, result: PipelineResult) -> None:
        self._reset_steps()
        for lb in self._step_labels:
            lb.setObjectName("StepChipDone")
            lb.style().unpolish(lb)
            lb.style().polish(lb)
        prospect = (result.prospect_text or "").strip()
        reply = (result.reply or "").strip()
        tag = result.tag or "?"
        meta = f"Intent {tag} · score {result.score:.2f} · {result.engine}"
        is_opening = tag == "out_presentation" and not prospect
        if not is_opening:
            self.chat.clear_draft()
            if prospect and prospect not in ("(ouverture)", "—"):
                self.chat.add_user(
                    prospect,
                    meta=self._chat_time_meta(f"transcription · {tag}"),
                )
                self._log(f"Prospect : {prospect[:120]}")
            elif tag:
                self.chat.add_user(
                    "(phrase non transcrite)",
                    meta=self._chat_time_meta(tag),
                )
        if reply:
            kind = "Ouverture" if tag == "out_presentation" else "Reponse"
            self.chat.add_marie(
                reply,
                meta=self._chat_time_meta(f"{kind} · {meta}"),
            )
            self._log(f"Marie ({tag}) score={result.score:.2f}")
        for i, row in enumerate(result.top_predictions[:6]):
            self._log(
                f"  Qdrant #{i + 1} {row.get('tag')} "
                f"({float(row.get('score') or 0):.2f})",
                level="debug",
            )
        if self._live_mode and self.live_worker is not None:
            self.lbl_status.setText("Marie a repondu — ecoute live.")
        elif not self._live_mode:
            self.lbl_status.setText("Terminé — vous pouvez enchaîner.")

    def _on_fail(self, msg: str) -> None:
        self._reset_steps()
        self.avatar.set_speaking(False)
        self.lbl_status.setText(f"Erreur : {msg}")
        self._log(msg, level="error")
        self.chat.add_system(f"Erreur : {msg}")
        if self._live_start_pending and self._live_mode:
            self._live_start_pending = False
            self.btn_live.blockSignals(True)
            self.btn_live.setChecked(False)
            self.btn_live.blockSignals(False)
            self._live_mode = False
            self._apply_live_chrome(False)
            self._stop_live_listen()
        if self._resume_live_after:
            self._resume_live_after = False
            self._resume_live_if_needed()
        if "annulée" in msg.lower() or "annulee" in msg.lower():
            return
        QMessageBox.warning(self, "Commercial Studio", msg)

    def _reset_dialogue(self) -> None:
        self.pipeline.reset_dialogue()
        session = self.wav_archive.new_session()
        self._refresh_recordings_hint()
        self.chat.clear()
        self.chat.add_system("Nouveau fil de conversation.")
        self.lbl_status.setText("Fil réinitialisé.")
        self._log(f"Fil dialogue reinitialise. WAV : {session}")
        self._reset_steps()

    def _test_hp(self) -> None:
        AudioDeviceHelper.play_test_speaker(
            self._device_out(),
            lambda m: self.lbl_status.setText(m),
            output_gain=self.pipeline.play_gain,
        )

    def closeEvent(self, event) -> None:  # noqa: ANN001
        self._stop_live_listen()
        if self.worker and self.worker.isRunning():
            self.pipeline.stop_playback()
            self.worker.wait(3000)
        self.pipeline.close()
        super().closeEvent(event)


def _install_console_interrupt_handler(app: QApplication) -> None:
    """
    Permet Ctrl+C dans une console (python outbound_studio.py) sous Windows.

    @param app QApplication PySide6.
    """
    def _quit(*_args: object) -> None:
        app.quit()
        raise SystemExit(130)

    signal.signal(signal.SIGINT, _quit)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _quit)
    tick = QTimer()
    tick.timeout.connect(lambda: None)
    tick.start(200)


def main() -> None:
    """Point d'entrée application."""
    app = QApplication(sys.argv)
    _install_console_interrupt_handler(app)
    app.setStyle("Fusion")
    icon_file = _app_icon_path()
    if icon_file.is_file():
        app.setWindowIcon(QIcon(str(icon_file)))
    win = CommercialStudioWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
