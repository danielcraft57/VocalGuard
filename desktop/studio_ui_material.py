"""
Composants Material Design 3 + motion pour Commercial Studio (PySide6).

Palette sombre type M3, cartes, FAB, onde vocale et panneau repliable.
"""

from __future__ import annotations

import html
import math
from datetime import datetime
from collections import deque
from typing import Deque, Literal, Optional

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    Qt,
    QTimer,
)
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPalette
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class MaterialColors:
    """Tokens couleur M3 (dark) pour le Studio."""

    bg = "#0f0d13"
    surface = "#1d1b20"
    surface_high = "#2b2930"
    surface_highest = "#36343b"
    primary = "#d0bcff"
    on_primary = "#381e72"
    primary_container = "#4f378b"
    on_primary_container = "#eaddff"
    secondary = "#ccc2dc"
    tertiary = "#efb8c8"
    on_surface = "#e6e1e5"
    on_surface_variant = "#cac4d0"
    outline = "#938f99"
    error = "#f2b8b5"
    success = "#a8d5ba"
    call_active = "#7dd3fc"
    call_live = "#86efac"


def material_stylesheet() -> str:
    """
    Feuille de style globale M3 pour la fenetre Studio.

    @returns CSS Qt.
    """
    c = MaterialColors
    return f"""
QMainWindow, QWidget#Root {{
    background-color: {c.bg};
    color: {c.on_surface};
    font-family: "Segoe UI Variable", "Segoe UI", sans-serif;
    font-size: 13px;
}}
QFrame#M3Card {{
    background-color: {c.surface_high};
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 28px;
}}
QFrame#M3CardInner {{
    background-color: {c.surface};
    border-radius: 20px;
    border: 1px solid rgba(255,255,255,0.04);
}}
QLabel#AppTitle {{
    font-size: 28px;
    font-weight: 600;
    letter-spacing: -0.5px;
    color: {c.on_surface};
}}
QLabel#AppSubtitle {{
    color: {c.on_surface_variant};
    font-size: 13px;
}}
QLabel#StatePill {{
    background-color: {c.primary_container};
    color: {c.on_primary_container};
    padding: 6px 14px;
    border-radius: 16px;
    font-weight: 600;
    font-size: 12px;
}}
QLabel#StatePillLive {{
    background-color: rgba(134, 239, 172, 0.22);
    color: {c.call_live};
    padding: 6px 14px;
    border-radius: 16px;
    font-weight: 600;
    font-size: 12px;
}}
QLabel#StatePillBusy {{
    background-color: rgba(125, 211, 252, 0.18);
    color: {c.call_active};
    padding: 6px 14px;
    border-radius: 16px;
    font-weight: 600;
    font-size: 12px;
}}
QLabel#CardCaption {{
    color: {c.on_surface_variant};
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.8px;
}}
QLabel#BodyText {{
    color: {c.on_surface};
    font-size: 14px;
    line-height: 1.45;
}}
QLabel#MetaText {{
    color: {c.outline};
    font-size: 12px;
}}
QLabel#StepChipIdle {{
    color: {c.outline};
    background: {c.surface};
    padding: 5px 12px;
    border-radius: 12px;
    font-size: 11px;
}}
QLabel#StepChipActive {{
    color: {c.on_primary_container};
    background: {c.primary_container};
    padding: 5px 12px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 600;
}}
QLabel#StepChipDone {{
    color: {c.success};
    background: rgba(168, 213, 186, 0.12);
    padding: 5px 12px;
    border-radius: 12px;
    font-size: 11px;
}}
QComboBox {{
    background: {c.surface_highest};
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 12px;
    padding: 10px 14px;
    min-height: 22px;
    color: {c.on_surface};
}}
QComboBox:hover {{
    border-color: {c.primary};
}}
QPushButton#TextBtn {{
    background: transparent;
    border: none;
    color: {c.primary};
    padding: 10px 16px;
    border-radius: 20px;
    font-weight: 600;
}}
QPushButton#TextBtn:hover {{
    background: rgba(208, 188, 255, 0.12);
}}
QPushButton#OutlinedBtn {{
    background: transparent;
    border: 1px solid {c.outline};
    border-radius: 20px;
    padding: 12px 22px;
    color: {c.on_surface};
    font-weight: 600;
}}
QPushButton#OutlinedBtn:hover {{
    border-color: {c.primary};
    background: rgba(208, 188, 255, 0.08);
}}
QPushButton#OutlinedBtn:disabled {{
    color: {c.outline};
    border-color: rgba(147, 143, 153, 0.35);
}}
QPushButton#FabCall {{
    background: {c.primary_container};
    color: {c.on_primary_container};
    border: none;
    border-radius: 32px;
    padding: 16px 32px;
    font-size: 15px;
    font-weight: 700;
    min-width: 200px;
    min-height: 56px;
}}
QPushButton#FabCall:hover {{
    background: #5a4196;
}}
QPushButton#FabHangup {{
    background: #8c1d18;
    color: #ffdad6;
    border: none;
    border-radius: 32px;
    padding: 16px 32px;
    font-size: 15px;
    font-weight: 700;
    min-width: 200px;
    min-height: 56px;
}}
QPushButton#FabHangup:hover {{
    background: #a5241e;
}}
QPushButton#IconGhost {{
    background: rgba(255,255,255,0.06);
    border: none;
    border-radius: 20px;
    padding: 10px 14px;
    color: {c.on_surface_variant};
}}
QPushButton#IconGhost:hover {{
    background: rgba(208, 188, 255, 0.14);
    color: {c.on_surface};
}}
QPushButton#ToggleChip {{
    background: {c.surface};
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 16px;
    padding: 8px 14px;
    color: {c.on_surface_variant};
}}
QPushButton#ToggleChip:checked {{
    background: rgba(208, 188, 255, 0.18);
    border-color: {c.primary};
    color: {c.primary};
}}
QSlider::groove:horizontal {{
    height: 4px;
    background: {c.surface_highest};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    width: 20px;
    height: 20px;
    margin: -8px 0;
    background: {c.primary};
    border-radius: 10px;
}}
QSlider::sub-page:horizontal {{
    background: {c.primary_container};
    border-radius: 2px;
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
QFrame#ChatBubbleUser {{
    background-color: rgba(14, 116, 144, 0.35);
    border: 1px solid rgba(125, 211, 252, 0.55);
    border-radius: 18px;
    border-top-right-radius: 6px;
}}
QFrame#ChatBubbleUser QLabel#ChatBody {{
    color: #ecfeff;
    font-size: 15px;
    font-weight: 500;
}}
QFrame#ChatBubbleUser QLabel#ChatMeta {{
    color: #99f6e4;
    font-size: 11px;
}}
QFrame#ChatBubbleMarie {{
    background-color: rgba(88, 56, 163, 0.45);
    border: 1px solid rgba(196, 181, 253, 0.55);
    border-radius: 18px;
    border-top-left-radius: 6px;
}}
QFrame#ChatBubbleMarie QLabel#ChatBody {{
    color: #faf5ff;
    font-size: 15px;
    font-weight: 500;
}}
QFrame#ChatBubbleMarie QLabel#ChatMeta {{
    color: #ddd6fe;
    font-size: 11px;
}}
QFrame#ChatBubbleMarie QLabel#ChatWho {{
    color: #e9d5ff;
}}
QFrame#ChatBubbleSystem {{
    background-color: rgba(255,255,255,0.05);
    border: 1px dashed rgba(147, 143, 153, 0.4);
    border-radius: 14px;
}}
QFrame#ChatBubbleSystem QLabel#ChatBody {{
    color: {c.on_surface_variant};
    font-size: 13px;
}}
QFrame#ChatBubbleDraft {{
    background-color: rgba(255,255,255,0.06);
    border: 1px solid rgba(147, 143, 153, 0.35);
    border-radius: 18px;
    border-top-right-radius: 6px;
}}
QFrame#ChatBubbleDraft QLabel#ChatBody {{
    color: {c.on_surface};
    font-size: 14px;
    font-style: italic;
}}
QTextEdit#LogConsole {{
    background-color: #141218;
    color: {c.on_surface_variant};
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 16px;
    padding: 12px;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 11px;
}}
QPlainTextEdit#LogConsole {{
    background-color: #141218;
    color: {c.on_surface_variant};
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 16px;
    padding: 12px;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 11px;
}}
QFrame#GradientHero {{
    background-color: {c.surface_high};
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 28px;
}}
QFrame#PanelCard {{
    background-color: {c.surface_high};
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 22px;
}}
QWidget#ChatTimelineInner {{
    background-color: {c.surface};
}}
"""


def apply_card_shadow(widget: QFrame, *, blur: int = 48, y: int = 12) -> None:
    """
    Ombre douce type elevation M3.

    @param widget Carte cible.
    @param blur Rayon de flou.
    @param y Decalage vertical.
    """
    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(blur)
    shadow.setOffset(0, y)
    shadow.setColor(QColor(0, 0, 0, 100))
    widget.setGraphicsEffect(shadow)


class CallAvatarWidget(QWidget):
    """
    Avatar Marie avec anneaux pulses (motion) en mode appel.

    @param parent Widget parent.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._pulse = 0.0
        self._live = False
        self._speaking = False
        self.setFixedSize(132, 132)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

    def set_live(self, live: bool) -> None:
        """Active ou coupe l'animation pulse."""
        self._live = live
        if live:
            self._pulse = 1.0
        else:
            self._pulse = 0.0
        self.update()

    def set_energy(self, level: float) -> None:
        """Renforce le pulse selon le niveau audio 0..1."""
        if self._live:
            self._pulse = max(self._pulse, min(1.0, level * 1.2))

    def set_speaking(self, speaking: bool) -> None:
        """Marie parle (halo chaud)."""
        self._speaking = speaking
        self.update()

    def _tick(self) -> None:
        if self._live:
            self._pulse *= 0.94
            if self._pulse < 0.15:
                self._pulse = 0.55
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: ANN001
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() // 2, self.height() // 2
        if self._live:
            ring_color = QColor(239, 184, 200, 90) if self._speaking else QColor(208, 188, 255, 70)
            for i, alpha in enumerate((28, 48, 72)):
                r = 42 + i * 12 + int(self._pulse * 14)
                p.setPen(Qt.PenStyle.NoPen)
                c = QColor(ring_color)
                c.setAlpha(alpha)
                p.setBrush(c)
                p.drawEllipse(cx - r, cy - r, 2 * r, 2 * r)
        grad = QLinearGradient(cx - 44, cy - 44, cx + 44, cy + 44)
        grad.setColorAt(0.0, QColor(126, 87, 194))
        grad.setColorAt(0.55, QColor(79, 55, 139))
        grad.setColorAt(1.0, QColor(56, 38, 96))
        p.setBrush(grad)
        p.setPen(QPen(QColor(255, 255, 255, 55), 2))
        p.drawEllipse(cx - 40, cy - 40, 80, 80)
        inner = QLinearGradient(cx - 28, cy - 28, cx + 28, cy + 28)
        inner.setColorAt(0.0, QColor(255, 255, 255, 35))
        inner.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(inner)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(cx - 28, cy - 32, 56, 40)
        p.setPen(QColor(MaterialColors.on_primary_container))
        font = QFont("Segoe UI", 24, QFont.Weight.DemiBold)
        p.setFont(font)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "M")


class MotionWaveform(QWidget):
    """
    Visualiseur onde Material (barres + lueur centrale).

    @param parent Widget parent.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._samples: Deque[float] = deque(maxlen=72)
        self._pulse = 0.0
        self._phase = 0.0
        self.setMinimumHeight(160)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._decay)
        self._timer.start(33)

    def push_level(self, level: float) -> None:
        """Ajoute un echantillon RMS 0..1."""
        self._samples.append(max(0.0, min(1.0, level)))

    def set_pulse(self, value: float) -> None:
        """Intensite halo global."""
        self._pulse = max(0.0, min(1.0, value))

    def current_pulse(self) -> float:
        """Pulse actuel."""
        return self._pulse

    def _decay(self) -> None:
        if self._pulse > 0.02:
            self._pulse *= 0.91
        self._phase += 0.08
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: ANN001
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        mid = h // 2

        bg = QLinearGradient(0, 0, w, h)
        bg.setColorAt(0.0, QColor(25, 22, 32, 180))
        bg.setColorAt(1.0, QColor(15, 13, 19, 40))
        p.fillRect(0, 0, w, h, bg)

        samples_list = list(self._samples)
        if len(samples_list) >= 2:
            pts: list[tuple[float, float]] = []
            n = len(samples_list)
            for i, lvl in enumerate(samples_list):
                x = 12 + (i / max(1, n - 1)) * (w - 24)
                amp = lvl * (h * 0.38) + 2
                wave = math.sin(self._phase + i * 0.25) * 4 * lvl
                y_top = mid - amp - wave
                pts.append((x, y_top))

            fill = QPainterPath()
            fill.moveTo(pts[0][0], mid + 10)
            for x, y in pts:
                fill.lineTo(x, y)
            fill.lineTo(pts[-1][0], mid + 10)
            fill.closeSubpath()
            gfill = QLinearGradient(0, mid - h * 0.4, 0, mid + 12)
            gfill.setColorAt(0.0, QColor(208, 188, 255, 95))
            gfill.setColorAt(0.5, QColor(125, 211, 252, 50))
            gfill.setColorAt(1.0, QColor(79, 55, 139, 12))
            p.fillPath(fill, gfill)

            stroke = QPainterPath()
            stroke.moveTo(pts[0][0], pts[0][1])
            for x, y in pts[1:]:
                stroke.lineTo(x, y)
            pen_glow = QPen(QColor(125, 211, 252, 100), 7)
            pen_glow.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen_glow)
            p.drawPath(stroke)
            pen = QPen(QColor(234, 221, 255), 2.2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawPath(stroke)
        else:
            pen_idle = QPen(QColor(147, 143, 153, 60), 1.5, Qt.PenStyle.DashLine)
            p.setPen(pen_idle)
            p.drawLine(24, mid, w - 24, mid)

        if self._pulse > 0.04:
            glow = int(35 + 75 * self._pulse)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(208, 188, 255, glow))
            p.drawEllipse(w // 2 - 62, mid - 62, 124, 124)


class GradientHeroFrame(QFrame):
    """
    Carte hero avec fond degrade peint (motion-friendly).

    @param parent Widget parent.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("GradientHero")
        self._shift = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(50)

    def _tick(self) -> None:
        self._shift = (self._shift + 0.015) % 1.0
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ANN001
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        g1 = QLinearGradient(0, 0, r.width(), r.height())
        t = self._shift
        g1.setColorAt(0.0, QColor(79, 55, 139, 55))
        g1.setColorAt(0.35 + t * 0.1, QColor(125, 211, 252, 28))
        g1.setColorAt(1.0, QColor(15, 13, 19, 0))
        p.fillRect(r, g1)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(208, 188, 255, 18))
        p.drawEllipse(r.width() // 2 - 120, -40, 240, 160)


def _label_text_color(label: QLabel, hex_color: str) -> None:
    """
    Force la couleur du texte (contourne les conflits QSS Windows).

    @param label Cible.
    @param hex_color Couleur #RRGGBB.
    """
    pal = label.palette()
    pal.setColor(QPalette.ColorRole.WindowText, QColor(hex_color))
    pal.setColor(QPalette.ColorRole.Text, QColor(hex_color))
    label.setPalette(pal)
    label.setStyleSheet(f"color: {hex_color}; background: transparent; border: none;")


_CHAT_THEMES: dict[str, dict[str, str]] = {
    "user": {
        "frame": (
            "QFrame { background-color: #0e4f66; border: 1px solid #22d3ee; "
            "border-radius: 16px; border-top-right-radius: 4px; }"
        ),
        "who": "#a5f3fc",
        "body": "#ffffff",
        "meta": "#67e8f9",
    },
    "marie": {
        "frame": (
            "QFrame { background-color: #4a2d7a; border: 1px solid #c4b5fd; "
            "border-radius: 16px; border-top-left-radius: 4px; }"
        ),
        "who": "#e9d5ff",
        "body": "#ffffff",
        "meta": "#ddd6fe",
    },
    "system": {
        "frame": (
            "QFrame { background-color: #2a2830; border: 1px dashed #78716c; "
            "border-radius: 12px; }"
        ),
        "who": "#a8a29e",
        "body": "#e7e5e4",
        "meta": "#a8a29e",
    },
    "draft": {
        "frame": (
            "QFrame { background-color: #3f3f46; border: 1px solid #71717a; "
            "border-radius: 16px; border-top-right-radius: 4px; }"
        ),
        "who": "#d4d4d8",
        "body": "#fafafa",
        "meta": "#a1a1aa",
    },
}


def _chat_bubble(
    role: Literal["user", "marie", "system", "draft"],
    body: str,
    meta: str = "",
) -> QFrame:
    """
    Construit une bulle de conversation Material.

    @param role Auteur visuel.
    @param body Texte principal.
    @param meta Sous-titre (intent, heure).
    @returns Frame stylée.
    """
    names = {
        "user": "ChatBubbleUser",
        "marie": "ChatBubbleMarie",
        "system": "ChatBubbleSystem",
        "draft": "ChatBubbleDraft",
    }
    frame = QFrame()
    frame.setObjectName(names[role])
    frame.setMaximumWidth(480)
    theme = _CHAT_THEMES[role]
    frame.setStyleSheet(theme["frame"])
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(14, 10, 14, 10)
    lay.setSpacing(4)
    if role == "user" or role == "draft":
        who = "Vous"
        if role == "draft":
            who = "Vous (en cours…)"
    elif role == "marie":
        who = "Marie"
    else:
        who = "Systeme"
    cap = QLabel(who)
    cap.setObjectName("ChatWho")
    _label_text_color(cap, theme["who"])
    cap.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
    lay.addWidget(cap)
    txt = QLabel(body or "…")
    txt.setWordWrap(True)
    txt.setObjectName("ChatBody")
    _label_text_color(txt, theme["body"])
    txt.setFont(QFont("Segoe UI", 14, QFont.Weight.DemiBold))
    txt.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    lay.addWidget(txt)
    if meta:
        m = QLabel(meta)
        m.setObjectName("ChatMeta")
        _label_text_color(m, theme["meta"])
        m.setFont(QFont("Segoe UI", 10))
        m.setWordWrap(True)
        lay.addWidget(m)
    return frame


class ChatTimelineWidget(QWidget):
    """
    Fil de chat scrollable (bulles prospect / Marie / systeme).

    @param parent Widget parent.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.viewport().setStyleSheet(
            f"background-color: {MaterialColors.surface}; border: none;"
        )
        self._inner = QWidget()
        self._inner.setObjectName("ChatTimelineInner")
        self._inner.setStyleSheet(
            f"background-color: {MaterialColors.surface};"
        )
        self._layout = QVBoxLayout(self._inner)
        self._layout.setContentsMargins(4, 8, 4, 8)
        self._layout.setSpacing(10)
        self._layout.addStretch(1)
        self._scroll.setWidget(self._inner)
        self._draft: Optional[QFrame] = None
        self._draft_wrap: Optional[QWidget] = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._scroll)

    def clear(self) -> None:
        """Vide le fil."""
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._draft = None
        self._draft_wrap = None

    def _scroll_bottom(self) -> None:
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def add_system(self, text: str) -> None:
        """Message systeme centre."""
        bubble = _chat_bubble("system", text)
        row = QHBoxLayout()
        wrap = QWidget()
        row.addStretch(1)
        row.addWidget(bubble, 0)
        row.addStretch(1)
        wrap.setLayout(row)
        self._layout.insertWidget(self._layout.count() - 1, wrap)
        QTimer.singleShot(0, self._scroll_bottom)

    def add_user(self, text: str, meta: str = "") -> None:
        """Tour prospect confirme."""
        self.clear_draft()
        bubble = _chat_bubble("user", text, meta)
        row = QHBoxLayout()
        wrap = QWidget()
        row.addStretch(1)
        row.addWidget(bubble, 5)
        wrap.setLayout(row)
        self._layout.insertWidget(self._layout.count() - 1, wrap)
        QTimer.singleShot(0, self._scroll_bottom)

    def add_marie(self, text: str, meta: str = "") -> None:
        """Reponse Marie."""
        bubble = _chat_bubble("marie", text, meta)
        row = QHBoxLayout()
        wrap = QWidget()
        row.addWidget(bubble, 5)
        row.addStretch(1)
        wrap.setLayout(row)
        self._layout.insertWidget(self._layout.count() - 1, wrap)
        QTimer.singleShot(0, self._scroll_bottom)

    def set_draft_user(self, text: str) -> None:
        """STT live partiel (une seule bulle brouillon)."""
        if not text.strip():
            self.clear_draft()
            return
        if self._draft is None:
            self._draft = _chat_bubble("draft", text)
            row = QHBoxLayout()
            self._draft_wrap = QWidget()
            row.addStretch(1)
            row.addWidget(self._draft, 5)
            self._draft_wrap.setLayout(row)
            self._layout.insertWidget(self._layout.count() - 1, self._draft_wrap)
        else:
            lay = self._draft.layout()
            if lay:
                for i in range(lay.count()):
                    w = lay.itemAt(i).widget()
                    if isinstance(w, QLabel) and w.objectName() == "ChatBody":
                        w.setText(text)
                        break
        QTimer.singleShot(0, self._scroll_bottom)

    def clear_draft(self) -> None:
        """Retire le brouillon STT."""
        wrap = getattr(self, "_draft_wrap", None)
        if wrap is not None:
            self._layout.removeWidget(wrap)
            wrap.deleteLater()
            self._draft_wrap = None
            self._draft = None


class LogConsoleWidget(QWidget):
    """
    Console logs monospace avec horodatage.

    @param parent Widget parent.
    """

    _MAX_LINES = 800

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._edit = QTextEdit()
        self._edit.setObjectName("LogConsole")
        self._edit.setReadOnly(True)
        self._line_count = 0
        self._max_lines = self._MAX_LINES
        header = QHBoxLayout()
        cap = QLabel("Journal")
        cap.setObjectName("CardCaption")
        header.addWidget(cap)
        header.addStretch()
        btn = QPushButton("Effacer")
        btn.setObjectName("TextBtn")
        btn.clicked.connect(self.clear)
        header.addWidget(btn)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addLayout(header)
        lay.addWidget(self._edit, 1)

    def clear(self) -> None:
        """Vide la console."""
        self._edit.clear()
        self._line_count = 0

    def append(
        self,
        message: str,
        *,
        level: Literal["info", "warn", "error", "debug"] = "info",
    ) -> None:
        """
        Ajoute une ligne horodatee avec couleur.

        @param message Texte.
        @param level Niveau visuel (prefixe).
        """
        ts = datetime.now().strftime("%H:%M:%S")
        prefix = {"info": "INF", "warn": "WRN", "error": "ERR", "debug": "DBG"}.get(
            level, "INF"
        )
        colors = {
            "info": "#d6d3d1",
            "warn": "#fcd34d",
            "error": "#fca5a5",
            "debug": "#7dd3fc",
        }
        fg = colors.get(level, colors["info"])
        safe = html.escape(message)
        line = (
            f'<span style="color:#78716c">[{ts}]</span> '
            f'<span style="color:{fg}; font-weight:600">{prefix}</span> '
            f'<span style="color:#e7e5e4">{safe}</span>'
        )
        self._edit.append(line)
        self._line_count += 1
        if self._line_count > self._max_lines:
            self._edit.clear()
            self._line_count = 1
        sb = self._edit.verticalScrollBar()
        sb.setValue(sb.maximum())


class CollapsibleSection(QWidget):
    """
    Panneau repliable avec animation hauteur.

    @param title Titre du panneau.
    @param parent Widget parent.
    """

    def __init__(self, title: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._expanded = False
        self._content_height = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._title = title
        self.btn_header = QPushButton("▸ " + title)
        self.btn_header.setObjectName("TextBtn")
        self.btn_header.setCheckable(True)
        self.btn_header.clicked.connect(self._toggle)
        layout.addWidget(self.btn_header)

        self._wrap = QWidget()
        self._wrap.setMaximumHeight(0)
        self._inner = QVBoxLayout(self._wrap)
        self._inner.setContentsMargins(8, 8, 8, 12)
        layout.addWidget(self._wrap)

        self._anim = QPropertyAnimation(self._wrap, b"maximumHeight", self)
        self._anim.setDuration(280)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def set_content_widget(self, widget: QWidget) -> None:
        """
        Remplace le contenu du panneau.

        @param widget Contenu (devices, sliders, etc.).
        """
        while self._inner.count():
            item = self._inner.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        self._inner.addWidget(widget)
        widget.adjustSize()
        self._content_height = widget.sizeHint().height() + 16

    def _toggle(self) -> None:
        self._expanded = not self._expanded
        prefix = "▾ " if self._expanded else "▸ "
        self.btn_header.setText(prefix + self._title)
        self._anim.stop()
        self._anim.setStartValue(self._wrap.maximumHeight())
        end = self._content_height if self._expanded else 0
        self._anim.setEndValue(end)
        self._anim.start()

    def expand(self) -> None:
        """Ouvre le panneau si ferme."""
        if not self._expanded:
            self._toggle()
