#!/usr/bin/env python3
"""
VocalGuard Line Phone — telephone bureau (modem USB sur PC + casque).

Usage:
  python desktop/line_phone.py
"""

from __future__ import annotations

import asyncio
import os
import queue
import signal
import sys
import threading
from pathlib import Path
from typing import List, Optional

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from PySide6.QtCore import Qt, QThread, QTimer, Signal  # noqa: E402
from PySide6.QtGui import QIcon, QKeyEvent  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desktop.audio_core import AudioDeviceHelper  # noqa: E402
from desktop.modem_local_call import list_com_ports, run_modem_call  # noqa: E402
from desktop.studio_ui_material import (  # noqa: E402
    CallAvatarWidget,
    CollapsibleSection,
    DialPadButton,
    GradientHeroFrame,
    LevelMeterBar,
    apply_card_shadow,
    material_stylesheet,
)

PAD_LETTERS = {
    "1": "",
    "2": "ABC",
    "3": "DEF",
    "4": "GHI",
    "5": "JKL",
    "6": "MNO",
    "7": "PQRS",
    "8": "TUV",
    "9": "WXYZ",
    "*": "+",
    "0": "",
    "#": "",
}


def _icon_path() -> Path:
    """
    Icône Line Phone (fallback Studio si absente).

    @returns Chemin .ico.
    """
    here = Path(__file__).resolve().parent / "assets"
    dedicated = here / "line_phone.ico"
    if dedicated.is_file():
        return dedicated
    return here / "commercial_studio.ico"


class ModemCallWorker(QThread):
    """
    Thread asyncio pour une session modem (ne bloque pas l'UI Qt).

    @param com_port Port serie modem.
    @param number Numero a appeler.
    """

    status = Signal(str)
    failed = Signal(str)
    call_finished = Signal()
    line_level = Signal(float)
    mic_level = Signal(float)

    def __init__(
        self,
        *,
        com_port: str,
        baudrate: int,
        number: str,
        input_device: Optional[int],
        output_device: Optional[int],
    ) -> None:
        super().__init__()
        self.com_port = com_port
        self.baudrate = baudrate
        self.number = number
        self.input_device = input_device
        self.output_device = output_device
        self._hangup = threading.Event()
        self._dtmf: queue.Queue[str] = queue.Queue()
        self._ptt: queue.Queue[bool] = queue.Queue()

    def request_hangup(self) -> None:
        """Demande raccrochage."""
        self._hangup.set()

    def send_dtmf(self, digit: str) -> None:
        """Enfile une touche DTMF."""
        self._dtmf.put(digit)

    def request_ptt(self) -> None:
        """Declenche une prise de parole push-to-talk."""
        self._ptt.put(True)

    def run(self) -> None:
        """Lance la coroutine modem."""
        try:
            asyncio.run(
                run_modem_call(
                    number=self.number,
                    com_port=self.com_port,
                    baudrate=self.baudrate,
                    input_device=self.input_device,
                    output_device=self.output_device,
                    hangup_event=self._hangup,
                    dtmf_queue=self._dtmf,
                    ptt_queue=self._ptt,
                    on_status=lambda m: self.status.emit(m),
                    on_line_level=lambda v: self.line_level.emit(v),
                    on_mic_level=lambda v: self.mic_level.emit(v),
                    push_to_talk=True,
                    ptt_ms=1400,
                )
            )
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.call_finished.emit()


class LinePhoneWindow(QMainWindow):
    """Fenetre principale Line Phone."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("VocalGuard - Line Phone")
        icon = _icon_path()
        if icon.is_file():
            self.setWindowIcon(QIcon(str(icon)))
        self.setMinimumSize(420, 820)
        self.resize(460, 900)
        self.worker: Optional[ModemCallWorker] = None
        self.in_map: dict[str, int] = {}
        self.out_map: dict[str, int] = {}
        self._in_call = False
        self._call_seconds = 0
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick_call_clock)

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        head = QHBoxLayout()
        t1 = QLabel("Line Phone")
        t1.setObjectName("AppTitle")
        t2 = QLabel("Ligne analogique · casque")
        t2.setObjectName("AppSubtitle")
        col = QVBoxLayout()
        col.addWidget(t1)
        col.addWidget(t2)
        head.addLayout(col)
        head.addStretch()
        self.lbl_state = QLabel("Pret")
        self.lbl_state.setObjectName("StatePill")
        head.addWidget(self.lbl_state)
        layout.addLayout(head)

        hero = GradientHeroFrame()
        apply_card_shadow(hero, blur=40, y=10)
        hero_l = QVBoxLayout(hero)
        hero_l.setContentsMargins(20, 20, 20, 16)
        hero_l.setSpacing(8)
        av_row = QHBoxLayout()
        av_row.addStretch()
        self.avatar = CallAvatarWidget()
        self.avatar.set_letter("#")
        av_row.addWidget(self.avatar)
        av_row.addStretch()
        hero_l.addLayout(av_row)

        self.lbl_timer = QLabel("00:00")
        self.lbl_timer.setObjectName("CallTimer")
        self.lbl_timer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_timer.hide()
        hero_l.addWidget(self.lbl_timer)

        self.edit_number = QLineEdit()
        self.edit_number.setObjectName("NumberDisplay")
        self.edit_number.setPlaceholderText("Qui appeler ?")
        self.edit_number.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.edit_number.setClearButtonEnabled(False)
        self.edit_number.textChanged.connect(self._on_number_changed)
        hero_l.addWidget(self.edit_number)

        self.lbl_status = QLabel("Composez, puis Appeler. Parler = micro (PTT).")
        self.lbl_status.setObjectName("AppSubtitle")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_l.addWidget(self.lbl_status)

        meters = QVBoxLayout()
        meters.setSpacing(6)
        m1 = QHBoxLayout()
        cap_l = QLabel("Ligne")
        cap_l.setObjectName("CardCaption")
        cap_l.setFixedWidth(48)
        m1.addWidget(cap_l)
        self.meter_line = LevelMeterBar()
        m1.addWidget(self.meter_line, 1)
        meters.addLayout(m1)
        m2 = QHBoxLayout()
        cap_m = QLabel("Micro")
        cap_m.setObjectName("CardCaption")
        cap_m.setFixedWidth(48)
        m2.addWidget(cap_m)
        self.meter_mic = LevelMeterBar()
        m2.addWidget(self.meter_mic, 1)
        meters.addLayout(m2)
        hero_l.addLayout(meters)
        layout.addWidget(hero)

        pad_card = QFrame()
        pad_card.setObjectName("PanelCard")
        apply_card_shadow(pad_card, blur=28, y=6)
        pad_l = QVBoxLayout(pad_card)
        pad_l.setContentsMargins(12, 16, 12, 8)
        pad = QGridLayout()
        pad.setSpacing(8)
        pad.setContentsMargins(4, 0, 4, 0)
        keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "0", "#"]
        for i, k in enumerate(keys):
            b = DialPadButton(k, PAD_LETTERS.get(k, ""))
            b.clicked.connect(lambda _c=False, d=k: self._pad_digit(d))
            pad.addWidget(b, i // 3, i % 3)
        pad_l.addLayout(pad)
        layout.addWidget(pad_card)

        actions = QHBoxLayout()
        actions.setSpacing(28)
        actions.addStretch()
        self.btn_ptt = QPushButton("Parler")
        self.btn_ptt.setObjectName("FabPttRound")
        self.btn_ptt.setEnabled(False)
        self.btn_ptt.hide()
        self.btn_ptt.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ptt.setToolTip("Appuyez pour parler (~1,4 s, push-to-talk).")
        self.btn_ptt.pressed.connect(self._ptt_pressed)
        actions.addWidget(self.btn_ptt)
        self.btn_call = QPushButton("Appeler")
        self.btn_call.setObjectName("FabCallRound")
        self.btn_call.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_call.clicked.connect(self._start_call)
        actions.addWidget(self.btn_call)
        self.btn_hangup = QPushButton("Fin")
        self.btn_hangup.setObjectName("FabHangupRound")
        self.btn_hangup.setEnabled(False)
        self.btn_hangup.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_hangup.clicked.connect(self._hangup)
        self.btn_hangup.hide()
        actions.addWidget(self.btn_hangup)
        self.btn_back = QPushButton("Effacer")
        self.btn_back.setObjectName("TextBtn")
        self.btn_back.setToolTip("Supprimer le dernier chiffre")
        self.btn_back.clicked.connect(self._backspace)
        actions.addWidget(self.btn_back)
        actions.addStretch()
        layout.addLayout(actions)

        settings_wrap = QWidget()
        settings_l = QVBoxLayout(settings_wrap)
        settings_l.setContentsMargins(0, 4, 0, 0)
        settings_l.setSpacing(10)
        row_com = QHBoxLayout()
        row_com.addWidget(QLabel("Port modem"))
        self.combo_com = QComboBox()
        row_com.addWidget(self.combo_com, 1)
        self.btn_refresh_com = QPushButton("Actualiser")
        self.btn_refresh_com.setObjectName("OutlinedBtn")
        self.btn_refresh_com.clicked.connect(self._refresh_com_ports)
        row_com.addWidget(self.btn_refresh_com)
        settings_l.addLayout(row_com)
        row_a = QHBoxLayout()
        row_a.addWidget(QLabel("Micro"))
        self.combo_in = QComboBox()
        row_a.addWidget(self.combo_in, 1)
        settings_l.addLayout(row_a)
        row_b = QHBoxLayout()
        row_b.addWidget(QLabel("Casque"))
        self.combo_out = QComboBox()
        row_b.addWidget(self.combo_out, 1)
        settings_l.addLayout(row_b)
        tools = QHBoxLayout()
        self.btn_refresh_dev = QPushButton("Audio")
        self.btn_refresh_dev.setObjectName("OutlinedBtn")
        self.btn_refresh_dev.clicked.connect(self._refresh_audio_devices)
        tools.addWidget(self.btn_refresh_dev)
        self.btn_test_hp = QPushButton("Test casque")
        self.btn_test_hp.setObjectName("OutlinedBtn")
        self.btn_test_hp.clicked.connect(self._test_hp)
        tools.addWidget(self.btn_test_hp)
        self.btn_test_mic = QPushButton("Test micro")
        self.btn_test_mic.setObjectName("OutlinedBtn")
        self.btn_test_mic.clicked.connect(self._test_mic)
        tools.addWidget(self.btn_test_mic)
        tools.addStretch()
        settings_l.addLayout(tools)
        hint = QLabel("USR5637 · baud 230400 · RJ11 sur le filtre ADSL.")
        hint.setObjectName("MetaText")
        hint.setWordWrap(True)
        settings_l.addWidget(hint)
        self.panel_settings = CollapsibleSection("Peripheriques")
        self.panel_settings.set_content_widget(settings_wrap)
        layout.addWidget(self.panel_settings)

        self.setStyleSheet(material_stylesheet())
        self._refresh_com_ports()
        self._refresh_audio_devices()
        saved_com = (os.environ.get("VG_LINE_PHONE_COM") or "").strip()
        if saved_com:
            idx = self.combo_com.findData(saved_com)
            if idx >= 0:
                self.combo_com.setCurrentIndex(idx)
        self.panel_settings.expand()

    def _refresh_com_ports(self) -> None:
        """Recharge la liste COM."""
        prev = self.combo_com.currentData()
        self.combo_com.blockSignals(True)
        self.combo_com.clear()
        ports = list_com_ports()
        if not ports:
            self.combo_com.addItem("(aucun port detecte)", "")
        for dev, desc in ports:
            label = f"{dev} - {desc}"
            self.combo_com.addItem(label, dev)
        if prev:
            idx = self.combo_com.findData(prev)
            if idx >= 0:
                self.combo_com.setCurrentIndex(idx)
        self.combo_com.blockSignals(False)

    def _refresh_audio_devices(self) -> None:
        """Liste micro / casque."""
        prev_in = self.combo_in.currentData()
        prev_out = self.combo_out.currentData()
        in_names, out_names, in_map, out_map = AudioDeviceHelper.list_devices()
        self.in_map = in_map
        self.out_map = out_map
        hs_in, hs_out = AudioDeviceHelper.find_headset_labels(in_map, out_map)

        def _fill(combo: QComboBox, names: List[str], mapping: dict, prev, preferred) -> None:
            combo.blockSignals(True)
            combo.clear()
            for label in names:
                combo.addItem(label, mapping[label])
            if prev is not None:
                idx = combo.findData(prev)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                    combo.blockSignals(False)
                    return
            if preferred:
                idx = combo.findText(preferred)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            combo.blockSignals(False)

        _fill(self.combo_in, in_names, in_map, prev_in, hs_in)
        _fill(self.combo_out, out_names, out_map, prev_out, hs_out)

    def _device_in(self) -> Optional[int]:
        data = self.combo_in.currentData()
        try:
            return int(data) if data is not None else None
        except (TypeError, ValueError):
            return self.in_map.get(self.combo_in.currentText())

    def _device_out(self) -> Optional[int]:
        data = self.combo_out.currentData()
        try:
            return int(data) if data is not None else None
        except (TypeError, ValueError):
            return self.out_map.get(self.combo_out.currentText())

    def _com_port(self) -> str:
        data = self.combo_com.currentData()
        return str(data or "").strip()

    def _digits_only(self) -> str:
        """Numero brut (chiffres et *#+)."""
        return "".join(c for c in self.edit_number.text() if c.isdigit() or c in "+*#")

    def _on_number_changed(self, text: str) -> None:
        """Met a jour l'avatar selon le numero."""
        digits = "".join(c for c in text if c.isdigit())
        if digits:
            self.avatar.set_letter(digits[-1])
        else:
            self.avatar.set_letter("#")

    def _backspace(self) -> None:
        """Supprime le dernier caractere du numero."""
        t = self.edit_number.text()
        if t:
            self.edit_number.setText(t[:-1])

    def _tick_call_clock(self) -> None:
        """Chrono d'appel mm:ss."""
        self._call_seconds += 1
        mm = self._call_seconds // 60
        ss = self._call_seconds % 60
        self.lbl_timer.setText(f"{mm:02d}:{ss:02d}")

    def _pad_digit(self, d: str) -> None:
        self.edit_number.setText(self.edit_number.text() + d)
        if self.worker is not None and self._in_call:
            self.worker.send_dtmf(d)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: ANN001
        """Pavé physique : chiffres, retour, entree pour appeler."""
        key = event.key()
        text = event.text()
        if key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            self._backspace()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not self._in_call:
            self._start_call()
            return
        if text and (text.isdigit() or text in "*#"):
            self._pad_digit(text)
            return
        super().keyPressEvent(event)

    def _set_in_call_ui(self, active: bool) -> None:
        self._in_call = active
        self.btn_call.setEnabled(not active)
        self.btn_call.setVisible(not active)
        self.btn_hangup.setEnabled(active)
        self.btn_hangup.setVisible(active)
        self.btn_ptt.setEnabled(active)
        self.btn_ptt.setVisible(active)
        self.btn_back.setEnabled(not active)
        self.btn_back.setVisible(not active)
        self.combo_com.setEnabled(not active)
        self.edit_number.setReadOnly(active)
        self.avatar.set_live(active)
        if active:
            self.lbl_state.setObjectName("StatePillLive")
            self.lbl_state.setText("En appel")
            self._call_seconds = 0
            self.lbl_timer.setText("00:00")
            self.lbl_timer.show()
            self._timer.start()
        else:
            self.lbl_state.setObjectName("StatePill")
            self.lbl_state.setText("Pret")
            self._timer.stop()
            self.lbl_timer.hide()
            self.meter_line.set_level(0.0)
            self.meter_mic.set_level(0.0)
        self.lbl_state.style().unpolish(self.lbl_state)
        self.lbl_state.style().polish(self.lbl_state)

    def _start_call(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        number = self._digits_only()
        if not number:
            QMessageBox.warning(self, "Line Phone", "Saisissez un numero.")
            return
        com = self._com_port()
        if not com:
            QMessageBox.warning(self, "Line Phone", "Selectionnez le port COM du modem.")
            return
        os.environ["VG_LINE_PHONE_COM"] = com
        self.worker = ModemCallWorker(
            com_port=com,
            baudrate=230400,
            number=number,
            input_device=self._device_in(),
            output_device=self._device_out(),
        )
        self.worker.status.connect(self.lbl_status.setText)
        self.worker.failed.connect(self._on_call_failed)
        self.worker.call_finished.connect(self._on_call_finished)
        self.worker.line_level.connect(self._on_line_level)
        self.worker.mic_level.connect(self._on_mic_level)
        self._set_in_call_ui(True)
        self.worker.start()

    def _hangup(self) -> None:
        if self.worker is not None:
            self.worker.request_hangup()

    def _ptt_pressed(self) -> None:
        if self.worker is not None and self._in_call:
            self.worker.request_ptt()

    def _on_line_level(self, v: float) -> None:
        self.meter_line.set_level(v)
        self.avatar.set_energy(v)

    def _on_mic_level(self, v: float) -> None:
        self.meter_mic.set_level(v)
        self.avatar.set_speaking(v > 0.12)

    def _on_call_failed(self, msg: str) -> None:
        self.lbl_status.setText(f"Erreur : {msg}")
        QMessageBox.warning(self, "Line Phone", msg)

    def _on_call_finished(self) -> None:
        self._set_in_call_ui(False)
        self.worker = None

    def _test_hp(self) -> None:
        AudioDeviceHelper.play_test_speaker(
            self._device_out(),
            lambda m: self.lbl_status.setText(m),
            output_gain=0.35,
        )

    def _test_mic(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        AudioDeviceHelper.probe_microphone(
            self._device_in(),
            lambda v: self.meter_mic.set_level(v),
            lambda m: self.lbl_status.setText(m),
        )

    def closeEvent(self, event) -> None:  # noqa: ANN001
        if self.worker is not None and self.worker.isRunning():
            self.worker.request_hangup()
            self.worker.wait(8000)
        super().closeEvent(event)


def _install_sigint(app: QApplication) -> None:
    def _quit(*_a: object) -> None:
        app.quit()

    signal.signal(signal.SIGINT, _quit)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _quit)
    tick = QTimer()
    tick.timeout.connect(lambda: None)
    tick.start(200)


def main() -> None:
    """Point d'entree."""
    app = QApplication(sys.argv)
    _install_sigint(app)
    app.setStyle("Fusion")
    icon = _icon_path()
    if icon.is_file():
        app.setWindowIcon(QIcon(str(icon)))
    win = LinePhoneWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
