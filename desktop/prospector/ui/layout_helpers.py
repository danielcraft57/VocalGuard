"""Helpers geometrie fenetres Prospector (centre ecran, tailles adaptatives)."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QRect, QSize
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget


def available_screen_geometry(widget: Optional[QWidget] = None) -> QRect:
    """
    Retourne la zone utilisable de l'ecran (sans barre des taches).

    @param widget Widget de reference pour multi-ecran (optionnel).
    @returns Rectangle disponible en pixels.
    """
    app = QApplication.instance()
    screen = widget.screen() if widget else None
    if screen is None and app:
        screen = app.primaryScreen()
    if screen is not None:
        return screen.availableGeometry()
    return QRect(0, 0, 1280, 800)


def center_on_screen(widget: QWidget, *, margin: int = 12) -> None:
    """
    Centre un widget dans la zone disponible, avec marge mini aux bords.

    @param widget Fenetre ou splash a positionner.
    @param margin Ecart minimum aux bords de l'ecran.
    """
    geo = available_screen_geometry(widget)
    frame = widget.frameGeometry()
    frame.moveCenter(geo.center())
    x = max(geo.x() + margin, min(frame.x(), geo.right() - frame.width() - margin))
    y = max(geo.y() + margin, min(frame.y(), geo.bottom() - frame.height() - margin))
    widget.move(x, y)


def default_main_window_size(geo: Optional[QRect] = None) -> QSize:
    """
    Calcule une taille confortable (~86 % largeur, ~82 % hauteur), bornee.

    @param geo Zone ecran (defaut: ecran principal).
    @returns Taille proposee pour la fenetre principale.
    """
    if geo is None:
        geo = available_screen_geometry()
    target_w = int(geo.width() * 0.86)
    target_h = int(geo.height() * 0.82)
    w = max(1080, min(target_w, 1520))
    h = max(660, min(target_h, 920))
    w = min(w, geo.width() - 24)
    h = min(h, geo.height() - 32)
    return QSize(w, h)


def apply_main_window_geometry(window: QMainWindow, *, maximize: bool = True) -> None:
    """
    Applique taille par defaut, minimums adaptatifs et centrage ou plein ecran.

    @param window Fenetre principale Prospector.
    @param maximize Ouvre en maximized si l'ecran le permet.
    """
    geo = available_screen_geometry(window)
    min_w = max(960, min(1080, geo.width() - 32))
    min_h = max(600, min(660, geo.height() - 48))
    window.setMinimumSize(min_w, min_h)
    if maximize and geo.width() >= 1200 and geo.height() >= 700:
        window.showMaximized()
    else:
        window.resize(default_main_window_size(geo))
        center_on_screen(window, margin=8)


def clamp_panel_width(widget: QWidget, *, min_w: int, max_w: int) -> None:
    """
    Fixe une largeur souple pour panneaux lateraux (min/max, hauteur extensible).

    @param widget Panneau lateral.
    @param min_w Largeur minimum.
    @param max_w Largeur maximum.
    """
    widget.setMinimumWidth(min_w)
    widget.setMaximumWidth(max_w)
