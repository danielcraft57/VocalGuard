"""Widgets reutilisables Prospector."""

from __future__ import annotations

import math
from typing import List, Optional, Sequence

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desktop.prospector.ui.theme_tokens import ThemeMode, tokens_for


def apply_prospector_card_shadow(widget: QFrame, *, mode: ThemeMode = "light") -> None:
    """
    Ombre d'elevation M3 adaptee au theme (plus douce en white mode).

    @param widget Carte cible.
    @param mode Theme actif.
    """
    shadow = QGraphicsDropShadowEffect(widget)
    if mode == "light":
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(15, 23, 42, 28))
    else:
        shadow.setBlurRadius(36)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 100))
    widget.setGraphicsEffect(shadow)


class KpiHeaderPill(QLabel):
    """Pastille KPI header (maquette file / pilotage)."""

    def __init__(
        self,
        text: str,
        *,
        kind: str = "default",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(text, parent)
        names = {
            "calls": "KpiPillCalls",
            "deco": "KpiPillDeco",
            "rdv": "KpiPillRdv",
            "vocal": "KpiPillVocal",
        }
        self.setObjectName(names.get(kind, "KpiPill"))


class EmptyStatePanel(QFrame):
    """Message centre quand une liste ou table est vide."""

    def __init__(
        self,
        title: str,
        hint: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("EmptyStatePanel")
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(8)
        t = QLabel(title)
        t.setObjectName("EmptyStateTitle")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h = QLabel(hint)
        h.setObjectName("EmptyStateHint")
        h.setWordWrap(True)
        h.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(t)
        lay.addWidget(h)


class HeaderToolButton(QPushButton):
    """Icone header (recherche, notif, reglages)."""

    def __init__(self, glyph: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(glyph, parent)
        self.setObjectName("HeaderToolBtn")
        self.setFixedSize(40, 40)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)


class UserAvatarChip(QLabel):
    """Initiales telepro header."""

    def __init__(self, initials: str = "AG", parent: Optional[QWidget] = None) -> None:
        super().__init__(initials, parent)
        self.setObjectName("UserAvatarChip")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(40, 40)


class ObjectionCard(QFrame):
    """Carte objection (maquette script)."""

    def __init__(
        self,
        icon: str,
        title: str,
        body: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ObjectionCard")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(10)
        ic = QLabel(icon)
        ic.setObjectName("ObjectionIcon")
        ic.setFixedWidth(28)
        ic.setAlignment(Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(4)
        t = QLabel(title)
        t.setStyleSheet("font-weight: 600; font-size: 13px;")
        b = QLabel(body)
        b.setObjectName("PageSubtitle")
        b.setWordWrap(True)
        col.addWidget(t)
        col.addWidget(b)
        lay.addWidget(ic)
        lay.addLayout(col, 1)


class StatCard(QFrame):
    """Carte KPI pilotage avec bandeau couleur."""

    def __init__(
        self,
        title: str,
        value: str,
        trend: str,
        *,
        accent: str = "#4f46e5",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ProspectorCard")
        self._accent = accent
        apply_prospector_card_shadow(self, mode="light")
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self._strip = QFrame()
        self._strip.setObjectName("StatAccentStrip")
        self._strip.setFixedWidth(5)
        self._strip.setStyleSheet(f"background-color: {accent}; border-radius: 3px;")
        outer.addWidget(self._strip)
        lay = QVBoxLayout()
        lay.setContentsMargins(14, 14, 16, 14)
        lay.setSpacing(4)
        t = QLabel(title)
        t.setObjectName("StatCardTitle")
        self.lbl_value = QLabel(value)
        self.lbl_value.setObjectName("StatCardValue")
        self.lbl_trend = QLabel(trend)
        self.lbl_trend.setObjectName("StatCardTrend")
        self.lbl_trend.setStyleSheet(f"color: {accent};")
        lay.addWidget(t)
        lay.addWidget(self.lbl_value)
        lay.addWidget(self.lbl_trend)
        outer.addLayout(lay, 1)

    def set_accent(self, accent: str) -> None:
        """Met a jour la couleur d'accent."""
        self._accent = accent
        self._strip.setStyleSheet(f"background-color: {accent}; border-radius: 3px;")
        self.lbl_trend.setStyleSheet(f"color: {accent};")

    def refresh_theme(self, mode: ThemeMode) -> None:
        """Reapplique l'ombre selon le theme."""
        apply_prospector_card_shadow(self, mode=mode)


class BarChartWidget(QWidget):
    """Histogramme appels par heure (plusieurs couleurs M3)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._values: List[int] = [3, 5, 8, 12, 18, 22, 15, 10, 14, 20, 16, 9]
        self._palette: Sequence[str] = ("#4f46e5", "#0d9488", "#d97706", "#db2777")
        self.setMinimumHeight(180)

    def set_values(self, values: List[int]) -> None:
        """Met a jour les barres."""
        self._values = values or self._values
        self.update()

    def set_palette(self, colors: Sequence[str]) -> None:
        """
        Palette cyclique des barres.

        @param colors Liste de hex.
        """
        if colors:
            self._palette = tuple(colors)
            self.update()

    def paintEvent(self, _event) -> None:  # noqa: ANN001
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), Qt.GlobalColor.transparent)
        if not self._values:
            return
        mx = max(self._values) or 1
        n = len(self._values)
        gap = 6
        bar_w = max(8, (w - gap * (n + 1)) // n)
        x = gap
        for i, v in enumerate(self._values):
            bh = int((h - 24) * (v / mx))
            color = self._palette[i % len(self._palette)]
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(color))
            p.drawRoundedRect(x, h - 12 - bh, bar_w, bh, 5, 5)
            x += bar_w + gap


class FunnelWidget(QWidget):
    """Entonnoir conversion (maquette pilotage)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(160)
        self._steps = [
            ("Appels", "128", 1.0, "#4f46e5"),
            ("Decroche", "40 (31%)", 0.55, "#0d9488"),
            ("RDV", "14 (11%)", 0.32, "#d97706"),
        ]
        self._label_color = "#0f172a"

    def set_theme_colors(
        self,
        *,
        chart_colors: Sequence[str],
        label_color: str,
    ) -> None:
        """
        Harmonise les couleurs avec le theme actif.

        @param chart_colors Accents etapes.
        @param label_color Texte sur les barres.
        """
        self._label_color = label_color
        updated = []
        for i, (label, val, ratio, _) in enumerate(self._steps):
            color = chart_colors[i % len(chart_colors)] if chart_colors else "#4f46e5"
            updated.append((label, val, ratio, color))
        self._steps = updated
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: ANN001
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), Qt.GlobalColor.transparent)
        y = 8
        step_h = (h - 16) // len(self._steps)
        for label, val, ratio, color in self._steps:
            bw = int(w * ratio)
            x = (w - bw) // 2
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(color))
            p.drawRoundedRect(x, y, bw, step_h - 6, 8, 8)
            p.setPen(QPen(QColor("#ffffff")))
            p.drawText(x + 12, y + step_h // 2 + 4, f"{label}  {val}")
            y += step_h


class PulseRingIcon(QLabel):
    """Icone telephone pulse (maquette entrant)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._phase = 0.0
        self.setFixedSize(88, 88)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(80)

    def _tick(self) -> None:
        self._phase += 0.15
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: ANN001
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = 44, 44
        pulse = 0.5 + 0.5 * math.sin(self._phase)
        r = 28 + int(8 * pulse)
        p.setPen(QPen(QColor(37, 99, 235, 80), 3))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(cx - r, cy - r, 2 * r, 2 * r)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(37, 99, 235))
        p.drawEllipse(cx - 22, cy - 22, 44, 44)
        p.setPen(QPen(QColor("#ffffff")))
        f = QFont("Segoe UI", 11, QFont.Weight.Bold)
        p.setFont(f)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "APPEL")


class StatusFooter(QFrame):
    """Barre bas modem / Whisper (maquette entrant)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("ProspectorStatusBar")
        self.setFixedHeight(36)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 0, 16, 0)
        self.lbl_modem = QLabel("Modem USB — en attente")
        self.lbl_headset = QLabel("Sonnerie casque")
        self.lbl_stt = QLabel("Transcription Whisper prete")
        for w in (self.lbl_modem, self.lbl_headset, self.lbl_stt):
            w.setObjectName("PageSubtitle")
            lay.addWidget(w)
        lay.addStretch()
        self._mode: ThemeMode = "light"

    def refresh_theme(self, mode: ThemeMode) -> None:
        """Met a jour les couleurs inline du footer."""
        self._mode = mode
        t = tokens_for(mode)
        for w in (self.lbl_modem, self.lbl_headset, self.lbl_stt):
            if w is self.lbl_modem and "en ecoute" in w.text():
                w.setStyleSheet(f"color: {t.success}; font-size: 11px; font-weight: 600;")
            else:
                w.setStyleSheet(f"color: {t.on_surface_variant}; font-size: 11px;")

    def set_listen_active(self, active: bool) -> None:
        """Met a jour l'etat ecoute."""
        t = tokens_for(self._mode)
        if active:
            self.lbl_modem.setText("Modem USB en ecoute")
            self.lbl_modem.setStyleSheet(f"color: {t.success}; font-size: 11px; font-weight: 600;")
        else:
            self.lbl_modem.setText("Modem USB — en attente")
            self.lbl_modem.setStyleSheet(f"color: {t.on_surface_variant}; font-size: 11px;")
