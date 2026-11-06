"""Ecran de chargement Prospector au demarrage."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QProgressBar, QVBoxLayout, QWidget

from desktop.prospector.ui.layout_helpers import center_on_screen

class ProspectorSplashScreen(QWidget):
    """
    Fenetre frameless sombre pendant l'init (migration, UI, peripheriques).

    @param parent Parent Qt optionnel.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("ProspectorSplash")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setFixedSize(480, 280)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(36, 32, 36, 24)
        lay.setSpacing(12)

        brand = QLabel("VocalGuard")
        brand.setObjectName("SplashBrand")
        tag = QLabel("Prospector · Power Dialer")
        tag.setObjectName("SplashTagline")
        lay.addWidget(brand)
        lay.addWidget(tag)
        lay.addSpacing(8)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(6)
        self.progress.setTextVisible(False)
        lay.addWidget(self.progress)

        self.lbl_status = QLabel("Demarrage…")
        self.lbl_status.setObjectName("SplashStatus")
        self.lbl_status.setWordWrap(True)
        lay.addWidget(self.lbl_status)

        lay.addStretch()
        foot = QLabel("Teleprospection · Modem · Whisper STT")
        foot.setObjectName("SplashFoot")
        lay.addWidget(foot)

    def show_centered(self) -> None:
        """Affiche la splash centree sur l'ecran principal."""
        center_on_screen(self, margin=16)
        self.show()
        app = QApplication.instance()
        if app:
            app.processEvents()

    def set_status(self, message: str) -> None:
        """
        Met a jour le libelle et rafraichit la boucle Qt.

        @param message Texte etape en cours.
        """
        self.lbl_status.setText(message)
        app = QApplication.instance()
        if app:
            app.processEvents()

    def finish(self, window: QMainWindow) -> None:
        """
        Ferme la splash et affiche la fenetre principale.

        @param window Fenetre Prospector prete.
        """
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.set_status("Pret")
        app = QApplication.instance()
        if app:
            app.processEvents()
        window.show()
        if not window.isMaximized():
            center_on_screen(window, margin=8)
        self.close()
