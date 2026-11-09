"""Controle volume global Prospector (header)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget


class VolumeControlWidget(QFrame):
    """
    Slider volume + mute + test (maquette header).

    @signal volume_changed Pourcent 0..100.
    @signal mute_changed True si coupe.
    @signal test_requested Demande bip test.
    """

    volume_changed = Signal(int)
    mute_changed = Signal(bool)
    test_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("VolumeControl")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(8)
        self.btn_mute = QPushButton("Vol")
        self.btn_mute.setObjectName("VolumeMuteBtn")
        self.btn_mute.setCheckable(True)
        self.btn_mute.setFixedWidth(44)
        self.btn_mute.setToolTip("Couper / reactiver les sons UI")
        self.btn_mute.toggled.connect(self._on_mute)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setObjectName("VolumeSlider")
        self.slider.setRange(0, 100)
        self.slider.setValue(65)
        self.slider.setFixedWidth(110)
        self.slider.valueChanged.connect(self._on_slide)
        self.lbl_pct = QLabel("65%")
        self.lbl_pct.setObjectName("VolumePct")
        self.lbl_pct.setFixedWidth(38)
        self.btn_test = QPushButton("Test")
        self.btn_test.setObjectName("OutlineButton")
        self.btn_test.setFixedHeight(32)
        self.btn_test.setToolTip("Bip sur le casque selectionne")
        self.btn_test.clicked.connect(self.test_requested.emit)
        lay.addWidget(self.btn_mute)
        lay.addWidget(self.slider)
        lay.addWidget(self.lbl_pct)
        lay.addWidget(self.btn_test)

    def set_volume_percent(self, percent: int) -> None:
        """Met a jour le slider sans emettre de signal."""
        self.slider.blockSignals(True)
        self.slider.setValue(max(0, min(100, percent)))
        self.slider.blockSignals(False)
        self.lbl_pct.setText(f"{self.slider.value()}%")

    def set_muted(self, muted: bool) -> None:
        """Sync bouton mute."""
        self.btn_mute.blockSignals(True)
        self.btn_mute.setChecked(muted)
        self.btn_mute.blockSignals(False)
        self._refresh_mute_label()

    def _on_slide(self, value: int) -> None:
        self.lbl_pct.setText(f"{value}%")
        self.volume_changed.emit(value)

    def _on_mute(self, checked: bool) -> None:
        self._refresh_mute_label()
        self.mute_changed.emit(checked)

    def _refresh_mute_label(self) -> None:
        self.btn_mute.setText("Muet" if self.btn_mute.isChecked() else "Vol")


class VolumeControlPanel(QFrame):
    """Bloc volume page parametres (meme signaux)."""

    volume_changed = Signal(int)
    mute_changed = Signal(bool)
    test_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ProspectorCard")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.addWidget(QLabel("Sons interface"))
        hint = QLabel(
            "Volume des bips (appel, sonnerie, confirmations). "
            "Utilise le casque choisi dans Connexions."
        )
        hint.setObjectName("PageSubtitle")
        hint.setWordWrap(True)
        outer.addWidget(hint)
        self.control = VolumeControlWidget()
        self.control.volume_changed.connect(self.volume_changed.emit)
        self.control.mute_changed.connect(self.mute_changed.emit)
        self.control.test_requested.connect(self.test_requested.emit)
        row = QHBoxLayout()
        row.addWidget(self.control)
        row.addStretch()
        outer.addLayout(row)

    def set_volume_percent(self, percent: int) -> None:
        """Sync depuis le moteur son."""
        self.control.set_volume_percent(percent)

    def set_muted(self, muted: bool) -> None:
        """Sync mute."""
        self.control.set_muted(muted)
