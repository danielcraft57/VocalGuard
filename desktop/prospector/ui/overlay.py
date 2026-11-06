"""Overlay appel entrant plein ecran (maquette)."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desktop.prospector.ui.widgets import PulseRingIcon


class IncomingCallOverlay(QWidget):
    """
    Overlay assombri + carte centrale.

    @signal answer Utilisateur decroche.
    @signal reject Refus.
    @signal ignore Laisser sonner.
    @signal voicemail Renvoyer messagerie.
    @signal add_queue Ajouter a la file.
    """

    answer = Signal()
    reject = Signal()
    ignore = Signal()
    voicemail = Signal()
    add_queue = Signal()

    def __init__(
        self,
        parent: QWidget,
        *,
        number: str,
        company: str,
        subtitle: str = "",
    ) -> None:
        super().__init__(parent)
        self.setObjectName("IncomingDim")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setGeometry(parent.rect())
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card = QFrame()
        card.setObjectName("IncomingCard")
        card.setMinimumWidth(420)
        card.setMaximumWidth(520)
        cl = QVBoxLayout(card)
        cl.setSpacing(12)

        top = QHBoxLayout()
        top.addStretch()
        btn_x = QPushButton("X")
        btn_x.setFixedSize(32, 32)
        btn_x.clicked.connect(self.reject.emit)
        top.addWidget(btn_x)
        cl.addLayout(top)

        cl.addWidget(PulseRingIcon(), alignment=Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(QLabel("Appel entrant"), alignment=Qt.AlignmentFlag.AlignCenter)
        lbl_num = QLabel(number)
        lbl_num.setStyleSheet("font-size: 26px; font-weight: 700;")
        lbl_num.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(lbl_num)
        cl.addWidget(QLabel("Identifie reseau"), alignment=Qt.AlignmentFlag.AlignCenter)

        chip = QLabel("Match ProspectLab")
        chip.setObjectName("MatchChip")
        chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(chip, alignment=Qt.AlignmentFlag.AlignCenter)

        co = QLabel(company or "Contact inconnu")
        co.setWordWrap(True)
        co.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(co)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("PageSubtitle")
            sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cl.addWidget(sub)

        main_row = QHBoxLayout()
        b_ok = QPushButton("Decrocher")
        b_ok.setObjectName("SuccessButton")
        b_ok.clicked.connect(self.answer.emit)
        b_no = QPushButton("Refuser")
        b_no.setObjectName("OutlineButton")
        b_no.clicked.connect(self.reject.emit)
        b_ring = QPushButton("Laisser sonner")
        b_ring.setObjectName("OutlineButton")
        b_ring.clicked.connect(self._ignore_close)
        main_row.addWidget(b_ok)
        main_row.addWidget(b_no)
        main_row.addWidget(b_ring)
        cl.addLayout(main_row)

        sec = QHBoxLayout()
        b_vm = QPushButton("Renvoyer messagerie")
        b_vm.setObjectName("OutlineButton")
        b_vm.clicked.connect(self._voicemail_close)
        b_q = QPushButton("Ajouter a la file")
        b_q.setObjectName("OutlineButton")
        b_q.clicked.connect(self._queue_close)
        sec.addWidget(b_vm)
        sec.addWidget(b_q)
        cl.addLayout(sec)

        outer.addWidget(card)

    def _ignore_close(self) -> None:
        self.ignore.emit()
        self.close()

    def _voicemail_close(self) -> None:
        self.voicemail.emit()
        self.close()

    def _queue_close(self) -> None:
        self.add_queue.emit()
        self.close()

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self.parentWidget():
            self.setGeometry(self.parentWidget().rect())
        super().resizeEvent(event)
