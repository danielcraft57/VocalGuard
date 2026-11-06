"""Boutons header + switch theme clair / sombre."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from desktop.prospector.ui.icons import MaterialIcon
from desktop.prospector.ui.theme_tokens import ThemeMode


class IconHeaderButton(QPushButton):
    """Bouton rond 40px avec icone Material."""

    def __init__(self, icon_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("HeaderToolBtn")
        self.setFixedSize(40, 40)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.icon = MaterialIcon(icon_name, size=20)
        lay.addWidget(self.icon, alignment=Qt.AlignmentFlag.AlignCenter)

    def set_icon_color(self, color: str) -> None:
        self.icon.set_color(color)


class ThemeSwitchWidget(QPushButton):
    """
    Bascule dark / light (icone soleil ou lune).

    @signal theme_changed Mode ``dark`` ou ``light``.
    """

    theme_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ThemeSwitchBtn")
        self.setCheckable(True)
        self.setFixedSize(40, 40)
        self.setToolTip("Theme clair / sombre")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._mode: ThemeMode = "dark"
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.icon = MaterialIcon("theme_light", size=20)
        lay.addWidget(self.icon, alignment=Qt.AlignmentFlag.AlignCenter)
        self.toggled.connect(self._on_toggle)

    def set_mode(self, mode: ThemeMode) -> None:
        """Sync UI sans signal."""
        self._mode = mode
        self.blockSignals(True)
        self.setChecked(mode == "light")
        icon = "theme_dark" if mode == "dark" else "theme_light"
        self.icon.set_icon_name(icon)
        self.blockSignals(False)

    def set_icon_color(self, color: str) -> None:
        self.icon.set_color(color)

    def _on_toggle(self, checked: bool) -> None:
        self._mode = "light" if checked else "dark"
        self.icon.set_icon_name("theme_dark" if self._mode == "dark" else "theme_light")
        self.theme_changed.emit(self._mode)


class HeaderToolsRow(QWidget):
    """Recherche, notif, theme, reglages."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.btn_search = IconHeaderButton("search")
        self.btn_notif = IconHeaderButton("notifications")
        self.theme_switch = ThemeSwitchWidget()
        self.btn_settings = IconHeaderButton("settings")
        for w in (self.btn_search, self.btn_notif, self.theme_switch, self.btn_settings):
            lay.addWidget(w)

    def set_accent_color(self, color: str) -> None:
        """Met a jour les icones header."""
        self.btn_search.set_icon_color(color)
        self.btn_notif.set_icon_color(color)
        self.theme_switch.set_icon_color(color)
        self.btn_settings.set_icon_color(color)
