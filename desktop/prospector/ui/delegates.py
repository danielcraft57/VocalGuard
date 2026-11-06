"""Delegates Qt Prospector (table file campagne)."""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from PySide6.QtCore import Qt, QRect, QSize
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QWidget

from desktop.studio_ui_material import MaterialColors


class StatusPillDelegate(QStyledItemDelegate):
    """Pastille coloree colonne Statut (maquette file campagne)."""

    _PALETTE: Dict[str, Tuple[str, QColor, QColor]] = {
        "todo": ("A appeler", QColor(59, 130, 246), QColor(219, 234, 254)),
        "in_progress": ("Appel en cours", QColor(45, 212, 191), QColor(204, 251, 241)),
        "done": ("RDV pris", QColor(74, 222, 128), QColor(220, 252, 231)),
        "skip": ("Ne pas deranger", QColor(248, 113, 113), QColor(254, 226, 226)),
        "busy": ("Occupe", QColor(156, 163, 175), QColor(243, 244, 246)),
    }

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index,
    ) -> None:  # noqa: ANN001
        key = index.data(Qt.ItemDataRole.UserRole)
        label = index.data(Qt.ItemDataRole.DisplayRole) or ""
        fg = QColor(MaterialColors.on_surface)
        bg = QColor(43, 41, 48)
        if isinstance(key, str) and key in self._PALETTE:
            _, fg, bg = self._PALETTE[key]
            label = self._PALETTE[key][0]

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(8, 10, -8, -10)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg)
        painter.drawRoundedRect(rect, 10, 10)
        painter.setPen(fg)
        font = QFont(option.font)
        font.setPixelSize(12)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(label))
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:  # noqa: ANN001
        return QSize(option.rect.width(), 44)
