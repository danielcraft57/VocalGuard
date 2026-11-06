"""Bouton navigation Material Design (rail large desktop)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from desktop.prospector.ui.icons import MaterialIcon


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    """
    Convertit un hex #RRGGBB en rgba CSS Qt.

    @param hex_color Couleur hex.
    @param alpha Opacite 0..1.
    @returns Chaine ``rgba(...)``.
    """
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return f"rgba(79, 70, 229, {alpha})"
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


class NavRailButton(QPushButton):
    """
    Entree sidebar Prospector (barre active + icone + libelle).

    Style M3 : hauteur confortable, pastille icone coloree, indicateur
    vertical a gauche quand la page est selectionnee.
    """

    def __init__(
        self,
        icon_name: str,
        label: str,
        *,
        accent: str = "#4f46e5",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("NavRailBtn")
        self.setCheckable(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(52)
        self._icon_name = icon_name
        self._accent = accent
        self._idle_icon_color = accent

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 8, 14, 8)
        lay.setSpacing(12)

        self._active_bar = QFrame()
        self._active_bar.setObjectName("NavActiveBar")
        self._active_bar.setFixedSize(4, 28)
        self._active_bar.setVisible(False)
        lay.addWidget(self._active_bar, alignment=Qt.AlignmentFlag.AlignVCenter)

        frame = QFrame()
        frame.setObjectName("NavIconFrame")
        frame.setFixedSize(38, 38)
        self._icon_frame = frame
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(0, 0, 0, 0)
        self.icon = MaterialIcon(icon_name, size=22, color=accent)
        fl.addWidget(self.icon, alignment=Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(frame)

        txt = QLabel(label)
        txt.setObjectName("NavLabel")
        txt.setWordWrap(False)
        self._label = txt
        lay.addWidget(txt, 1)

        self.toggled.connect(self._on_toggled)

    def set_accent(self, accent: str) -> None:
        """
        Definit la couleur d'accent (icone au repos + pastille).

        @param accent Hex couleur.
        """
        self._accent = accent
        self._idle_icon_color = accent
        if not self.isChecked():
            self.icon.set_color(accent)
            soft = _hex_to_rgba(accent, 0.14)
            self._icon_frame.setStyleSheet(
                f"QFrame#NavIconFrame {{ background-color: {soft}; border-radius: 12px; border: none; }}"
            )
        else:
            self._icon_frame.setStyleSheet(
                f"QFrame#NavIconFrame {{ background-color: {accent}; border-radius: 12px; border: none; }}"
            )

    def set_icon_color(self, color: str) -> None:
        """Adapte la couleur d'icone au theme / etat."""
        self.icon.set_color(color)

    def set_idle_icon_color(self, color: str) -> None:
        """Couleur d'icone quand le bouton n'est pas actif."""
        self._idle_icon_color = color
        if not self.isChecked():
            self.icon.set_color(color)

    def _on_toggled(self, checked: bool) -> None:
        self._active_bar.setVisible(checked)
        if checked:
            self.icon.set_color("#ffffff")
            self._active_bar.setStyleSheet(
                f"background-color: {self._accent}; border-radius: 2px;"
            )
            self._icon_frame.setStyleSheet(
                f"QFrame#NavIconFrame {{ background-color: {self._accent}; border-radius: 12px; border: none; }}"
            )
        else:
            self.icon.set_color(self._idle_icon_color)
            soft = _hex_to_rgba(self._accent, 0.14)
            self._icon_frame.setStyleSheet(
                f"QFrame#NavIconFrame {{ background-color: {soft}; border-radius: 12px; border: none; }}"
            )
