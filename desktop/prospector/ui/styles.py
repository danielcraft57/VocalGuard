"""Styles Qt Prospector — themes clair / sombre (M3)."""

from __future__ import annotations

from desktop.prospector.ui.theme_tokens import ThemeMode, tokens_for


def prospector_stylesheet(mode: ThemeMode = "dark") -> str:
    """
    Feuille de style complete selon le theme.

    @param mode ``dark`` ou ``light``.
    @returns CSS Qt.
    """
    t = tokens_for(mode)
    root = "QWidget#ProspectorRoot"
    # White mode : primary_container est deja un indigo plein ; dark garde le violet rempli
    nav_checked_bg = t.nav_active_bg
    primary_btn_bg = t.primary_container
    primary_btn_fg = t.on_primary_container
    return f"""
QMainWindow, {root} {{
    background-color: {t.bg};
    color: {t.on_surface};
    font-family: "Segoe UI Variable", "Segoe UI", sans-serif;
    font-size: 13px;
}}
QFrame#ProspectorHeader {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {t.header_grad_start}, stop:1 {t.header_grad_end});
    border-bottom: 1px solid {t.border};
}}
QLabel#ProspectorBrand {{
    font-size: 21px;
    font-weight: 700;
    color: {t.primary};
    letter-spacing: -0.4px;
}}
QLabel#ProspectorTagline {{
    color: {t.on_surface_variant};
    font-size: 12px;
}}
QFrame#ProspectorNavRail {{
    background-color: {t.surface_nav};
    border-right: 1px solid {t.border};
}}
QLabel#NavSectionLabel {{
    color: {t.on_surface_variant};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.08em;
    padding: 4px 22px 10px 22px;
}}
QFrame#ProspectorStatusBar {{
    background-color: {t.surface};
    border-top: 1px solid {t.border};
}}
QFrame#ProspectorCard {{
    background-color: {t.surface_card};
    border: 1px solid {t.border};
    border-radius: 16px;
}}
QFrame#ActiveCallBar {{
    background-color: {t.secondary_container};
    border: 1px solid {t.secondary};
    border-radius: 14px;
}}
QLabel#KpiPill {{
    background-color: {t.input_bg};
    color: {t.on_surface};
    padding: 6px 12px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 600;
    border: 1px solid {t.border};
}}
QLabel#KpiPillCalls {{
    background-color: {t.info_container};
    color: {t.info};
    padding: 6px 12px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 700;
    border: 1px solid transparent;
}}
QLabel#KpiPillDeco {{
    background-color: {t.secondary_container};
    color: {t.secondary};
    padding: 6px 12px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 700;
    border: 1px solid transparent;
}}
QLabel#KpiPillRdv {{
    background-color: {t.tertiary_container};
    color: {t.tertiary};
    padding: 6px 12px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 700;
    border: 1px solid transparent;
}}
QLabel#KpiPillVocal {{
    background-color: rgba(219, 39, 119, 0.12);
    color: #db2777;
    padding: 6px 12px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 700;
    border: 1px solid transparent;
}}
QPushButton#NavRailBtn {{
    background: transparent;
    border: none;
    border-radius: 14px;
    margin: 3px 14px;
    padding: 0;
    text-align: left;
    min-height: 48px;
}}
QPushButton#NavRailBtn:checked {{
    background-color: {nav_checked_bg};
}}
QPushButton#NavRailBtn:hover {{
    background-color: {t.button_hover};
}}
QFrame#NavIconFrame {{
    background-color: {t.nav_badge_bg};
    border-radius: 12px;
    border: none;
}}
QPushButton#NavRailBtn:checked QFrame#NavIconFrame {{
    background-color: {t.nav_badge_active};
}}
QFrame#NavActiveBar {{
    background-color: {t.nav_indicator};
    border-radius: 2px;
}}
QLabel#NavLabel {{
    color: {t.on_surface_variant};
    font-size: 14px;
    font-weight: 500;
}}
QPushButton#NavRailBtn:checked QLabel#NavLabel {{
    color: {t.on_surface};
    font-weight: 700;
}}
QPushButton#TopTab {{
    background-color: transparent;
    color: {t.on_surface_variant};
    border: none;
    border-bottom: 2px solid transparent;
    border-radius: 0;
    padding: 10px 18px;
    font-weight: 600;
}}
QPushButton#TopTab:checked {{
    color: {t.primary};
    border-bottom: 2px solid {t.primary_container};
}}
{root} QPushButton {{
    background-color: {t.button_bg};
    color: {t.on_surface};
    border: 1px solid {t.border};
    border-radius: 12px;
    padding: 9px 16px;
    font-size: 13px;
}}
{root} QPushButton:hover {{
    background-color: {t.button_hover};
}}
QPushButton#PrimaryButton {{
    background-color: {primary_btn_bg};
    color: {primary_btn_fg};
    border: none;
    font-weight: 600;
}}
QPushButton#PrimaryButton:hover {{
    background-color: {primary_btn_bg};
}}
QPushButton#SuccessButton {{
    background-color: {t.secondary_container};
    color: {t.secondary};
    border: 1px solid {t.secondary};
    font-weight: 600;
}}
QPushButton#DangerButton {{
    background-color: rgba(220, 38, 38, 0.12);
    color: {t.error};
    border: 1px solid rgba(220, 38, 38, 0.28);
}}
QPushButton#OutlineButton {{
    background: transparent;
    border: 1px solid {t.border_strong};
}}
QPushButton#GhostScriptBtn {{
    background: transparent;
    border: 1px solid {t.primary};
    color: {t.primary};
}}
QLabel#PageTitle {{
    font-size: 24px;
    font-weight: 700;
    color: {t.on_surface};
}}
QLabel#PageSubtitle {{
    color: {t.on_surface_variant};
    font-size: 13px;
}}
QLabel#StatePillLive {{
    background-color: {t.secondary_container};
    color: {t.success};
    padding: 6px 14px;
    border-radius: 14px;
    font-weight: 600;
    font-size: 12px;
}}
{root} QLineEdit, {root} QPlainTextEdit, {root} QTextEdit, QPlainTextEdit#ScriptEditor {{
    background-color: {t.input_bg};
    color: {t.on_surface};
    border: 1px solid {t.border};
    border-radius: 14px;
    padding: 10px 14px;
    min-height: 40px;
    selection-background-color: {t.info_container};
    font-size: 14px;
}}
QLabel#FormLabel {{
    color: {t.on_surface};
    font-size: 13px;
    font-weight: 600;
    padding-top: 10px;
}}
QLabel#FormHint {{
    color: {t.on_surface_variant};
    font-size: 12px;
    line-height: 1.35;
}}
{root} QLineEdit#SettingsField, {root} QComboBox#SettingsCombo {{
    background-color: {t.surface_card};
    border: 1px solid {t.border_strong};
    border-radius: 12px;
    padding: 10px 14px;
    min-height: 44px;
    font-size: 14px;
}}
{root} QLineEdit#SettingsField:focus, {root} QComboBox#SettingsCombo:focus,
{root} QComboBox#SettingsCombo:hover {{
    border-color: {t.primary};
}}
QCheckBox#FormCheck {{
    color: {t.on_surface_variant};
    font-size: 12px;
    spacing: 8px;
    padding: 4px 0 8px 0;
}}
QScrollArea#SettingsScroll {{
    background: transparent;
    border: none;
}}
QWidget#SettingsBody {{
    background: transparent;
}}
{root} QComboBox {{
    background-color: {t.input_bg};
    color: {t.on_surface};
    border: 1px solid {t.border};
    border-radius: 10px;
    padding: 8px 12px;
    min-height: 40px;
}}
{root} QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
{root} QComboBox QAbstractItemView {{
    background-color: {t.surface_card};
    color: {t.on_surface};
    selection-background-color: {t.info_container};
    border: 1px solid {t.border};
}}
QTableWidget {{
    background-color: {t.table_bg};
    alternate-background-color: {t.table_alt};
    color: {t.on_surface};
    border: 1px solid {t.border};
    border-radius: 14px;
    gridline-color: {t.border};
}}
QTableWidget::item {{
    padding: 10px 8px;
    border: none;
}}
QTableWidget::item:selected {{
    background-color: {t.info_container};
    color: {t.on_surface};
}}
QHeaderView::section {{
    background-color: {t.surface};
    color: {t.on_surface_variant};
    padding: 10px 8px;
    border: none;
    border-bottom: 1px solid {t.border};
    font-weight: 600;
    font-size: 12px;
}}
QTableCornerButton::section {{
    background-color: {t.surface};
    border: none;
}}
QListWidget {{
    background-color: {t.table_bg};
    color: {t.on_surface};
    border: 1px solid {t.border};
    border-radius: 14px;
    padding: 6px;
}}
QListWidget::item {{
    padding: 10px 12px;
    border-radius: 10px;
    margin: 2px 0;
}}
QListWidget::item:selected {{
    background-color: {t.info_container};
    color: {t.on_surface};
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollBar:vertical {{
    background: {t.surface};
    width: 10px;
    border-radius: 5px;
}}
QScrollBar::handle:vertical {{
    background: {t.on_surface_variant};
    border-radius: 5px;
    min-height: 24px;
}}
QFrame#IncomingDim, QWidget#IncomingDim {{
    background-color: {t.overlay_dim};
}}
QFrame#IncomingCard {{
    background-color: {t.surface_card};
    border: 1px solid {t.primary_container};
    border-radius: 22px;
}}
QLabel#MatchChip {{
    background-color: {t.info_container};
    color: {t.info};
    padding: 8px 14px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: 600;
}}
QFrame#UserCard {{
    background-color: {t.input_bg};
    border-radius: 16px;
    border: 1px solid {t.border};
    margin: 8px 14px 4px 14px;
}}
QLabel#UserCardName {{
    color: {t.on_surface};
    font-size: 13px;
    font-weight: 700;
}}
QLabel#UserStatusLive {{
    color: {t.success};
    font-size: 12px;
    font-weight: 600;
}}
QPushButton#HeaderToolBtn, QPushButton#ThemeSwitchBtn {{
    background-color: {t.input_bg};
    border: 1px solid {t.border};
    border-radius: 12px;
    padding: 0;
}}
QPushButton#HeaderToolBtn:hover, QPushButton#ThemeSwitchBtn:hover {{
    background-color: {t.button_hover};
}}
QPushButton#ThemeSwitchBtn:checked {{
    background-color: {t.info_container};
}}
QLabel#UserAvatarChip {{
    background-color: {t.primary_container};
    color: {t.on_primary_container};
    border-radius: 20px;
    font-weight: 700;
    font-size: 13px;
}}
QFrame#ObjectionCard {{
    background-color: {t.input_bg};
    border: 1px solid {t.border};
    border-radius: 14px;
}}
QLabel#ObjectionIcon {{
    color: {t.tertiary};
    font-size: 18px;
    font-weight: 700;
}}
QPushButton#HangUpRound {{
    background-color: #dc2626;
    color: white;
    border: none;
    border-radius: 24px;
    font-size: 18px;
    font-weight: 700;
    padding: 0;
}}
QWidget#ProspectorSplash {{
    background-color: {t.bg};
    border: 1px solid {t.splash_border};
    border-radius: 20px;
}}
QLabel#SplashBrand {{
    font-size: 28px;
    font-weight: 700;
    color: {t.primary};
}}
QLabel#SplashTagline, QLabel#SplashFoot {{
    color: {t.on_surface_variant};
    font-size: 13px;
}}
QLabel#SplashStatus {{
    color: {t.on_surface};
    font-size: 13px;
}}
QWidget#ProspectorSplash QProgressBar {{
    background-color: {t.surface};
    border: none;
    border-radius: 3px;
}}
QWidget#ProspectorSplash QProgressBar::chunk {{
    background-color: {t.primary_container};
    border-radius: 3px;
}}
QFrame#VolumeControl {{
    background-color: {t.input_bg};
    border: 1px solid {t.border};
    border-radius: 12px;
}}
QSlider#VolumeSlider::groove:horizontal {{
    height: 6px;
    background: {t.surface};
    border-radius: 3px;
}}
QSlider#VolumeSlider::handle:horizontal {{
    width: 14px;
    margin: -5px 0;
    background: {t.primary_container};
    border-radius: 7px;
}}
QSlider#VolumeSlider::sub-page:horizontal {{
    background: {t.primary_container};
    border-radius: 3px;
}}
QLabel#VolumePct {{
    color: {t.on_surface_variant};
    font-size: 11px;
}}
QFrame#EmptyStatePanel {{
    background-color: transparent;
    border: 1px dashed {t.border_strong};
    border-radius: 14px;
}}
QLabel#EmptyStateTitle {{
    color: {t.on_surface};
    font-size: 15px;
    font-weight: 600;
}}
QLabel#EmptyStateHint {{
    color: {t.on_surface_variant};
    font-size: 12px;
}}
QLabel#CardSectionTitle {{
    color: {t.on_surface};
    font-size: 14px;
    font-weight: 600;
}}
QLabel#StatCardTitle {{
    color: {t.on_surface_variant};
    font-size: 12px;
    font-weight: 600;
}}
QLabel#StatCardValue {{
    color: {t.on_surface};
    font-size: 28px;
    font-weight: 700;
}}
QLabel#StatCardTrend {{
    font-size: 11px;
    font-weight: 600;
}}
QFrame#StatAccentStrip {{
    border-radius: 3px;
}}
{root} QLineEdit#DialNumberField {{
    font-size: 22px;
    font-weight: 700;
    letter-spacing: 0.06em;
    padding: 14px 16px;
    min-height: 28px;
}}
QPushButton#DialPadKey {{
    background-color: {t.input_bg};
    border: 1px solid {t.border};
    border-radius: 14px;
    color: {t.on_surface};
    font-size: 22px;
    font-weight: 700;
    min-width: 76px;
    min-height: 56px;
}}
QPushButton#DialPadKey:hover {{
    background-color: {t.button_hover};
    border-color: {t.border_strong};
}}
QPushButton#DialPadKey:pressed {{
    background-color: {t.primary_container};
    color: {t.on_primary_container};
    border-color: transparent;
}}
QPushButton#DialPadKey QLabel {{
    background: transparent;
    border: none;
}}
QLabel#DialLetters {{
    color: {t.on_surface_variant};
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 1.4px;
}}
QStackedWidget {{
    background: transparent;
}}
"""
