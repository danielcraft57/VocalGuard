"""Icones vectorielles legers (QPainter, style M3 outline)."""

from __future__ import annotations

import math

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


class MaterialIcon(QWidget):
    """
    Dessine une icone 24px (navigation, header).

    @param name Identifiant icone (dashboard, campaigns, ...).
    @param color Couleur trait.
    """

    def __init__(
        self,
        name: str,
        *,
        color: str = "#c4b5fd",
        size: int = 22,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._name = name
        self._color = color
        self.setFixedSize(size, size)

    def set_icon_name(self, name: str) -> None:
        """Change le glyphe dessine."""
        self._name = name
        self.update()

    def set_color(self, color: str) -> None:
        """Met a jour la couleur de trait."""
        self._color = color
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: ANN001
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(self._color))
        pen.setWidthF(1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        w, h = self.width(), self.height()
        s = min(w, h)
        ox = (w - s) / 2
        oy = (h - s) / 2
        draw = {
            "dashboard": self._dashboard,
            "campaigns": self._campaigns,
            "cockpit": self._cockpit,
            "phone": self._phone,
            "incoming": self._incoming,
            "settings": self._settings,
            "search": self._search,
            "notifications": self._bell,
            "theme_dark": self._moon,
            "theme_light": self._sun,
        }.get(self._name, self._dashboard)
        draw(p, ox, oy, s)

    @staticmethod
    def _dashboard(p: QPainter, x: float, y: float, s: float) -> None:
        g = s / 4
        for row in range(2):
            for col in range(2):
                p.drawRoundedRect(x + col * (g + 2), y + row * (g + 2), g, g, 3, 3)

    @staticmethod
    def _campaigns(p: QPainter, x: float, y: float, s: float) -> None:
        p.drawRoundedRect(x + 2, y + 4, s - 8, s - 6, 3, 3)
        p.drawLine(x + s - 6, y + 6, x + s - 6, y + s - 2)

    @staticmethod
    def _cockpit(p: QPainter, x: float, y: float, s: float) -> None:
        p.drawEllipse(x + 3, y + 3, s - 6, s - 6)
        p.drawLine(x + s / 2, y + 5, x + s / 2, y + s - 5)

    @staticmethod
    def _phone(p: QPainter, x: float, y: float, s: float) -> None:
        p.drawRoundedRect(x + 5, y + 2, s - 10, s - 4, 4, 4)
        p.drawLine(x + s / 2 - 3, y + s - 5, x + s / 2 + 3, y + s - 5)

    @staticmethod
    def _incoming(p: QPainter, x: float, y: float, s: float) -> None:
        p.drawLine(x + 4, y + 6, x + s / 2, y + s - 4)
        p.drawLine(x + s - 4, y + 6, x + s / 2, y + s - 4)
        p.drawLine(x + 4, y + 6, x + s - 4, y + 6)

    @staticmethod
    def _settings(p: QPainter, x: float, y: float, s: float) -> None:
        cx, cy = x + s / 2, y + s / 2
        p.drawEllipse(cx - 3, cy - 3, 6, 6)
        for i in range(8):
            ang = i * 45
            rad = math.radians(ang)
            x1 = cx + math.cos(rad) * 5
            y1 = cy + math.sin(rad) * 5
            x2 = cx + math.cos(rad) * 8
            y2 = cy + math.sin(rad) * 8
            p.drawLine(int(x1), int(y1), int(x2), int(y2))

    @staticmethod
    def _search(p: QPainter, x: float, y: float, s: float) -> None:
        p.drawEllipse(x + 3, y + 3, s - 10, s - 10)
        p.drawLine(x + s - 7, y + s - 7, x + s - 3, y + s - 3)

    @staticmethod
    def _bell(p: QPainter, x: float, y: float, s: float) -> None:
        p.drawLine(x + s / 2, y + 3, x + s / 2, y + 5)
        path_y = y + 5
        p.drawArc(int(x + 4), int(path_y), int(s - 8), int(s - 8), 0, 180 * 16)
        p.drawLine(x + 4, y + s - 4, x + s - 4, y + s - 4)

    @staticmethod
    def _sun(p: QPainter, x: float, y: float, s: float) -> None:
        cx, cy = x + s / 2, y + s / 2
        p.drawEllipse(cx - 3, cy - 3, 6, 6)
        for i in range(8):
            rad = math.radians(i * 45)
            p.drawLine(
                int(cx + math.cos(rad) * 6),
                int(cy + math.sin(rad) * 6),
                int(cx + math.cos(rad) * 9),
                int(cy + math.sin(rad) * 9),
            )

    @staticmethod
    def _moon(p: QPainter, x: float, y: float, s: float) -> None:
        p.drawArc(int(x + 4), int(y + 3), int(s - 6), int(s - 6), 60 * 16, 240 * 16)


def icon_size() -> QSize:
    """Taille standard header."""
    return QSize(22, 22)
