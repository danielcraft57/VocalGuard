"""Coquille fenetre Prospector (header + rail + pages)."""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QStackedWidget, QVBoxLayout, QWidget

from desktop.prospector.ui.header_tools import HeaderToolsRow
from desktop.prospector.ui.layout_helpers import clamp_panel_width
from desktop.prospector.ui.nav_rail import NavRailButton
from desktop.prospector.ui.pages import (
    CockpitPage,
    EntrantsPage,
    FileCampagnePage,
    PilotagePage,
    SettingsPage,
    SoftphonePage,
)
from desktop.prospector.ui.theme_tokens import ThemeMode, nav_accent_for, tokens_for
from desktop.prospector.ui.volume_control import VolumeControlWidget
from desktop.prospector.ui.widgets import KpiHeaderPill, StatusFooter, UserAvatarChip


class ProspectorShell(QWidget):
    """Layout principal calque maquettes VocalGuard (rail Material large)."""

    NAV = [
        ("dashboard", "Tableau de bord"),
        ("campaigns", "Campagnes"),
        ("cockpit", "Cockpit d'appel"),
        ("phone", "Line + Prospection"),
        ("incoming", "Appels entrants"),
        ("settings", "Parametres"),
    ]

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("ProspectorRoot")
        self._theme_mode: ThemeMode = "light"
        self._nav_label: Optional[QLabel] = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.header = QFrame()
        self.header.setObjectName("ProspectorHeader")
        self.header.setFixedHeight(68)
        hl = QHBoxLayout(self.header)
        hl.setContentsMargins(20, 10, 20, 10)
        hl.setSpacing(12)
        brand = QVBoxLayout()
        brand.setSpacing(0)
        self.lbl_brand = QLabel("VocalGuard")
        self.lbl_brand.setObjectName("ProspectorBrand")
        self.lbl_subbrand = QLabel("Campagne de teleprospection  ·  Power Dialer")
        self.lbl_subbrand.setObjectName("ProspectorTagline")
        self.lbl_subbrand.setWordWrap(False)
        brand.addWidget(self.lbl_brand)
        brand.addWidget(self.lbl_subbrand)
        hl.addLayout(brand, 1)
        self.volume = VolumeControlWidget()
        hl.addWidget(self.volume)
        hl.addSpacing(8)
        self.kpi_calls = KpiHeaderPill("0 appels", kind="calls")
        self.kpi_deco = KpiHeaderPill("0% decroches", kind="deco")
        self.kpi_rdv = KpiHeaderPill("0 RDV", kind="rdv")
        self.kpi_vocal = KpiHeaderPill("0 vocaux", kind="vocal")
        self._header_kpis = (
            self.kpi_calls,
            self.kpi_deco,
            self.kpi_rdv,
            self.kpi_vocal,
        )
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(8)
        for k in self._header_kpis:
            kpi_row.addWidget(k)
        hl.addLayout(kpi_row)
        hl.addSpacing(8)
        self.header_tools = HeaderToolsRow()
        self.header_tools.btn_settings.clicked.connect(lambda: self.set_page(5))
        self.avatar_header = UserAvatarChip("AG")
        hl.addWidget(self.header_tools)
        hl.addWidget(self.avatar_header)
        root.addWidget(self.header)

        body = QHBoxLayout()
        body.setSpacing(0)
        self.rail = QFrame()
        self.rail.setObjectName("ProspectorNavRail")
        # Rail Material large desktop (~18–20 % sur ecran 1440+)
        clamp_panel_width(self.rail, min_w=268, max_w=312)
        rl = QVBoxLayout(self.rail)
        rl.setSpacing(4)
        rl.setContentsMargins(0, 20, 0, 14)
        nav_lbl = QLabel("NAVIGATION")
        nav_lbl.setObjectName("NavSectionLabel")
        self._nav_label = nav_lbl
        rl.addWidget(nav_lbl)
        self._nav_btns: List[NavRailButton] = []
        for i, (icon_name, label) in enumerate(self.NAV):
            accent = nav_accent_for(i)
            b = NavRailButton(icon_name, label, accent=accent)
            b.clicked.connect(lambda checked=False, idx=i: self.set_page(idx))
            rl.addWidget(b)
            self._nav_btns.append(b)
        rl.addStretch()
        user = QFrame()
        user.setObjectName("UserCard")
        ul = QHBoxLayout(user)
        ul.setContentsMargins(12, 12, 12, 12)
        ul.setSpacing(10)
        avatar = UserAvatarChip("AG")
        avatar.setFixedSize(36, 36)
        ul.addWidget(avatar)
        ucol = QVBoxLayout()
        ucol.setSpacing(2)
        name = QLabel("Antoine Garnier")
        name.setObjectName("UserCardName")
        st = QLabel("Disponible")
        st.setObjectName("UserStatusLive")
        self.lbl_user_status = st
        ucol.addWidget(name)
        ucol.addWidget(st)
        ul.addLayout(ucol, 1)
        rl.addWidget(user)
        body.addWidget(self.rail)

        self.stack = QStackedWidget()
        self._apply_stack_background("light")
        self.page_pilotage = PilotagePage()
        self.page_file = FileCampagnePage()
        self.page_cockpit = CockpitPage()
        self.page_softphone = SoftphonePage()
        self.page_entrants = EntrantsPage()
        self.page_settings = SettingsPage()
        for p in (
            self.page_pilotage,
            self.page_file,
            self.page_cockpit,
            self.page_softphone,
            self.page_entrants,
            self.page_settings,
        ):
            self.stack.addWidget(p)
        body.addWidget(self.stack, 1)
        root.addLayout(body, 1)

        self.footer = StatusFooter()
        root.addWidget(self.footer)
        if self._nav_btns:
            self._nav_btns[0].setChecked(True)
        self.apply_theme("light")

    def _apply_stack_background(self, mode: ThemeMode) -> None:
        t = tokens_for(mode)
        self.stack.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:0,y2:1, "
            f"stop:0 {t.bg_grad_top}, stop:1 {t.bg_grad_bottom});"
        )

    def apply_theme(self, mode: ThemeMode) -> None:
        """
        Met a jour couleurs inline (icones, labels) apres changement QSS.

        @param mode Theme actif.
        """
        self._theme_mode = mode
        t = tokens_for(mode)
        self._apply_stack_background(mode)
        # Header icons: neutre slate en light, primary en dark
        accent = t.on_surface_variant if mode == "light" else t.primary
        self.header_tools.set_accent_color(accent)
        self._sync_nav_icon_colors()
        self.footer.refresh_theme(mode)
        if hasattr(self.page_pilotage, "refresh_theme"):
            self.page_pilotage.refresh_theme(mode)
        if hasattr(self.page_cockpit, "refresh_theme"):
            self.page_cockpit.refresh_theme(mode)
        if hasattr(self.page_file, "refresh_theme"):
            self.page_file.refresh_theme(mode)

    def _sync_nav_icon_colors(self) -> None:
        for i, btn in enumerate(self._nav_btns):
            accent = nav_accent_for(i)
            btn.set_accent(accent)
            if btn.isChecked():
                btn.set_icon_color("#ffffff")
            else:
                btn.set_idle_icon_color(accent)

    def set_page(self, index: int) -> None:
        """Change la page avec fondu court (M3 standard motion)."""
        if index < 0 or index >= self.stack.count():
            return
        if index == self.stack.currentIndex():
            return
        target = self.stack.widget(index)
        effect = QGraphicsOpacityEffect(target)
        target.setGraphicsEffect(effect)
        effect.setOpacity(0.0)
        self.stack.setCurrentIndex(index)
        for i, b in enumerate(self._nav_btns):
            b.setChecked(i == index)
        self._sync_nav_icon_colors()
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(180)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        def _cleanup() -> None:
            target.setGraphicsEffect(None)

        anim.finished.connect(_cleanup)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def resizeEvent(self, event: QResizeEvent) -> None:  # type: ignore[override]
        """Masque elements header si fenetre etroite ; elargit le rail en grand ecran."""
        super().resizeEvent(event)
        w = self.width()
        compact = w < 1180
        narrow = w < 1050
        self.lbl_subbrand.setVisible(not compact)
        self.kpi_vocal.setVisible(not narrow)
        self.kpi_deco.setVisible(not narrow)
        self.header_tools.btn_search.setVisible(not narrow)
        self.volume.setVisible(not narrow)
        if w >= 1440:
            clamp_panel_width(self.rail, min_w=288, max_w=320)
        elif w >= 1200:
            clamp_panel_width(self.rail, min_w=268, max_w=300)
        else:
            clamp_panel_width(self.rail, min_w=240, max_w=268)
