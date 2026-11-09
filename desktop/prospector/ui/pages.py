"""Ecrans Prospector calques sur les maquettes JPG."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QApplication,
    QPushButton,
    QScrollArea,
    QSlider,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from desktop.prospector.call_player import CallWavPlayer, wav_duration_seconds
from desktop.prospector.ui.layout_helpers import clamp_panel_width

from desktop.studio_ui_material import (
    CallAvatarWidget,
    ChatTimelineWidget,
    DialPadButton,
    LevelMeterBar,
    MotionWaveform,
)
from desktop.prospector.ui.delegates import StatusPillDelegate
from desktop.prospector.ui.theme_tokens import ThemeMode, tokens_for
from desktop.prospector.ui.widgets import (
    BarChartWidget,
    EmptyStatePanel,
    FunnelWidget,
    ObjectionCard,
    StatCard,
    apply_prospector_card_shadow,
)
from desktop.prospector.ui.volume_control import VolumeControlPanel


class PilotagePage(QWidget):
    """Maquette pilotage — tableau de bord."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(16)
        head = QHBoxLayout()
        col = QVBoxLayout()
        col.addWidget(self._title("Tableau de bord"))
        col.addWidget(self._subtitle("Suivez vos performances d'appels en temps reel"))
        head.addLayout(col)
        head.addStretch()
        head.addWidget(QLabel("Aujourd'hui"))
        lay.addLayout(head)

        kpi = QHBoxLayout()
        kpi.setSpacing(12)
        self.card_calls = StatCard("Appels", "0", "+18% vs hier", accent="#4f46e5")
        self.card_deco = StatCard("Decroche", "0%", "+5 pts", accent="#0d9488")
        self.card_rdv = StatCard("RDV", "0", "+27%", accent="#d97706")
        self.card_duree = StatCard("Duree moy.", "0m00", "+12%", accent="#db2777")
        self._stat_cards = (self.card_calls, self.card_deco, self.card_rdv, self.card_duree)
        for c in self._stat_cards:
            kpi.addWidget(c)
        lay.addLayout(kpi)

        charts = QHBoxLayout()
        charts.setSpacing(14)
        self.chart_card = QFrame()
        self.chart_card.setObjectName("ProspectorCard")
        apply_prospector_card_shadow(self.chart_card, mode="light")
        cl = QVBoxLayout(self.chart_card)
        cl.setContentsMargins(16, 14, 16, 14)
        cl.addWidget(self._section_title("Appels par heure"))
        self.bar_chart = BarChartWidget()
        cl.addWidget(self.bar_chart)
        charts.addWidget(self.chart_card, 2)

        self.funnel_card = QFrame()
        self.funnel_card.setObjectName("ProspectorCard")
        apply_prospector_card_shadow(self.funnel_card, mode="light")
        fl = QVBoxLayout(self.funnel_card)
        fl.setContentsMargins(16, 14, 16, 14)
        fl.addWidget(self._section_title("Entonnoir de conversion"))
        self.funnel = FunnelWidget()
        fl.addWidget(self.funnel)
        hint = QLabel("Taux de conversion global — calcule depuis le journal")
        hint.setObjectName("PageSubtitle")
        fl.addWidget(hint)
        charts.addWidget(self.funnel_card, 1)
        lay.addLayout(charts, 1)

        self.act_card = QFrame()
        self.act_card.setObjectName("ProspectorCard")
        apply_prospector_card_shadow(self.act_card, mode="light")
        al = QVBoxLayout(self.act_card)
        al.setContentsMargins(16, 14, 16, 14)
        al.addWidget(self._section_title("Activites recentes"))
        self.activity_stack = QStackedWidget()
        self.empty_activity = EmptyStatePanel(
            "Aucune activite",
            "Vos appels et RDV du jour s'afficheront ici des la premiere session.",
        )
        self.list_activity = QListWidget()
        self.activity_stack.addWidget(self.empty_activity)
        self.activity_stack.addWidget(self.list_activity)
        al.addWidget(self.activity_stack, 1)
        lay.addWidget(self.act_card, 1)

    def refresh_theme(self, mode: ThemeMode) -> None:
        """
        Harmonise KPI / charts avec le theme actif.

        @param mode Theme clair ou sombre.
        """
        t = tokens_for(mode)
        accents = (t.chart_1, t.chart_2, t.chart_3, t.chart_4)
        for card, accent in zip(self._stat_cards, accents):
            card.set_accent(accent)
            card.refresh_theme(mode)
        self.bar_chart.set_palette(accents)
        self.funnel.set_theme_colors(chart_colors=accents, label_color=t.on_surface)
        for frame in (self.chart_card, self.funnel_card, self.act_card):
            apply_prospector_card_shadow(frame, mode=mode)

    @staticmethod
    def _section_title(text: str) -> QLabel:
        lb = QLabel(text)
        lb.setObjectName("CardSectionTitle")
        return lb

    @staticmethod
    def _title(text: str) -> QLabel:
        lb = QLabel(text)
        lb.setObjectName("PageTitle")
        return lb

    @staticmethod
    def _subtitle(text: str) -> QLabel:
        lb = QLabel(text)
        lb.setObjectName("PageSubtitle")
        return lb


class FileCampagnePage(QWidget):
    """Maquette file campagne / power dialer."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        root = QHBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(16)

        left = QFrame()
        clamp_panel_width(left, min_w=200, max_w=240)
        left.setObjectName("ProspectorCard")
        ll = QVBoxLayout(left)
        ll.addWidget(QLabel("Cartes"))
        sub = QLabel("Dossiers campagne")
        sub.setObjectName("PageSubtitle")
        ll.addWidget(sub)
        self.list_groupes = QListWidget()
        ll.addWidget(self.list_groupes, 1)
        self.btn_sync_groupes = QPushButton("Rafraichir groupes")
        self.btn_import = QPushButton("Charger ce groupe")
        self.btn_import.setObjectName("PrimaryButton")
        self.btn_clear = QPushButton("Vider file todo")
        ll.addWidget(self.btn_sync_groupes)
        ll.addWidget(self.btn_import)
        ll.addWidget(self.btn_clear)
        root.addWidget(left)

        center = QVBoxLayout()
        header = QHBoxLayout()
        tcol = QVBoxLayout()
        tcol.addWidget(self._title("File d'appels — Power Dialer"))
        sub = QLabel("Campagne de teleprospection · VocalGuard")
        sub.setObjectName("PageSubtitle")
        tcol.addWidget(sub)
        header.addLayout(tcol)
        header.addStretch()
        self.chip_active = QLabel("Actif")
        self.chip_active.setObjectName("StatePillLive")
        header.addWidget(self.chip_active)
        center.addLayout(header)

        filt = QHBoxLayout()
        filt.addWidget(QLabel("Filtre groupe"))
        self.cmb_filter_groupe = QComboBox()
        filt.addWidget(self.cmb_filter_groupe, 1)
        filt.addWidget(QLabel("Statut"))
        self.cmb_filter_status = QComboBox()
        self.cmb_filter_status.addItems(["todo", "in_progress", "done", "all"])
        filt.addWidget(self.cmb_filter_status)
        self.btn_refresh_queue = QPushButton("Rafraichir")
        filt.addWidget(self.btn_refresh_queue)
        center.addLayout(filt)

        self.table_queue = QTableWidget(0, 5)
        self.table_queue.setHorizontalHeaderLabels(
            ["Societe", "Contact", "Telephone", "Statut", "Dernier intent"]
        )
        self.table_queue.setAlternatingRowColors(True)
        self.table_queue.setShowGrid(False)
        self.table_queue.verticalHeader().setVisible(False)
        self.table_queue.verticalHeader().setDefaultSectionSize(46)
        h = self.table_queue.horizontalHeader()
        h.setStretchLastSection(False)
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        h.resizeSection(3, 150)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table_queue.setItemDelegateForColumn(3, StatusPillDelegate(self.table_queue))
        self.table_queue.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_queue.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.queue_stack = QStackedWidget()
        self.empty_queue = EmptyStatePanel(
            "File d'appels vide",
            "Synchronisez vos groupes ProspectLab a gauche, puis « Charger ce groupe » pour remplir la file.",
        )
        self.queue_stack.addWidget(self.empty_queue)
        self.queue_stack.addWidget(self.table_queue)
        center.addWidget(self.queue_stack, 1)

        self.bar_active_call = QFrame()
        self.bar_active_call.setObjectName("ActiveCallBar")
        bl = QHBoxLayout(self.bar_active_call)
        bl.setContentsMargins(12, 10, 12, 10)
        bl.setSpacing(10)
        self.bar_wave = MotionWaveform()
        self.bar_wave.setMinimumHeight(48)
        self.bar_wave.setMaximumHeight(48)
        self.bar_wave.setMaximumWidth(240)
        bl.addWidget(self.bar_wave, 1)
        info = QVBoxLayout()
        info.setSpacing(2)
        self.lbl_active_call = QLabel("Aucun appel en cours")
        self.lbl_active_call.setStyleSheet("font-weight: 600;")
        self.lbl_active_sub = QLabel("Selectionnez un contact ou lancez le dialer")
        self.lbl_active_sub.setObjectName("PageSubtitle")
        info.addWidget(self.lbl_active_call)
        info.addWidget(self.lbl_active_sub)
        bl.addLayout(info, 2)
        self.lbl_call_timer = QLabel("00:00")
        self.lbl_call_timer.setStyleSheet("font-size: 18px; font-weight: 700; font-family: Consolas, monospace;")
        bl.addWidget(self.lbl_call_timer)
        self.btn_bar_mute = QPushButton("Micro")
        self.btn_bar_mute.setObjectName("OutlineButton")
        self.btn_bar_mute.setFixedWidth(72)
        bl.addWidget(self.btn_bar_mute)
        self.btn_bar_hang = QPushButton("✕")
        self.btn_bar_hang.setObjectName("HangUpRound")
        self.btn_bar_hang.setFixedSize(48, 48)
        self.btn_bar_hang.setToolTip("Raccrocher (modem ATH0)")
        bl.addWidget(self.btn_bar_hang)
        center.addWidget(self.bar_active_call)
        root.addLayout(center, 1)

        script = QFrame()
        clamp_panel_width(script, min_w=268, max_w=332)
        script.setObjectName("ProspectorCard")
        sl = QVBoxLayout(script)
        sl.addWidget(QLabel("Script d'appel"))
        self.txt_script_open = QPlainTextEdit()
        self.txt_script_open.setObjectName("ScriptEditor")
        self.txt_script_open.setReadOnly(True)
        self.txt_script_open.setPlainText(
            "Ouverture\n\nBonjour, je suis [Prenom] de VocalGuard. "
            "Je vous appelle concernant la securite de votre activite…"
        )
        sl.addWidget(self.txt_script_open, 1)
        sl.addWidget(QLabel("Gestion des objections"))
        sl.addWidget(
            ObjectionCard("€", "Prix trop cher", "Parlez ROI, maintenance incluse et cout d'une panne evitee.")
        )
        sl.addWidget(
            ObjectionCard("⌂", "Deja un prestataire", "Proposez un comparatif reactif sous 24 h, sans engagement.")
        )
        self.btn_full_script = QPushButton("Ouvrir le script complet")
        self.btn_full_script.setObjectName("PrimaryButton")
        sl.addWidget(self.btn_full_script)
        root.addWidget(script)

    @staticmethod
    def _title(text: str) -> QLabel:
        lb = QLabel(text)
        lb.setObjectName("PageTitle")
        return lb


class CockpitPage(QWidget):
    """Maquette cockpit d'appel live."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(14)

        center = QVBoxLayout()
        center.setSpacing(10)
        self.hero = QFrame()
        self.hero.setObjectName("ProspectorCard")
        apply_prospector_card_shadow(self.hero, mode="light")
        self.hero.setMinimumHeight(168)
        self.hero.setMaximumHeight(220)
        hl = QVBoxLayout(self.hero)
        hl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar = CallAvatarWidget()
        self.avatar.set_letter("M")
        hl.addWidget(self.avatar, alignment=Qt.AlignmentFlag.AlignCenter)
        self.lbl_timer = QLabel("00:00")
        self.lbl_timer.setStyleSheet("font-size: 32px; font-weight: 700;")
        self.lbl_timer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hl.addWidget(self.lbl_timer)
        self.lbl_call_state = QLabel("Appel commercial — En ligne")
        self.lbl_call_state.setObjectName("StatePillLive")
        self.lbl_call_state.setMaximumWidth(280)
        hl.addWidget(self.lbl_call_state, alignment=Qt.AlignmentFlag.AlignCenter)
        center.addWidget(self.hero)

        self.chat_wrap = QFrame()
        self.chat_wrap.setObjectName("ProspectorCard")
        apply_prospector_card_shadow(self.chat_wrap, mode="light")
        cw = QVBoxLayout(self.chat_wrap)
        cw.setContentsMargins(8, 8, 8, 8)
        self.chat = ChatTimelineWidget()
        self._style_chat_surface(self.chat, tokens_for("light").input_bg)
        self.chat.add_system(
            "Transcription live — le dialogue prospect / telepro s'affichera ici pendant l'appel."
        )
        cw.addWidget(self.chat, 1)
        center.addWidget(self.chat_wrap, 1)
        self.waveform = MotionWaveform()
        center.addWidget(self.waveform)

        actions = QHBoxLayout()
        self.btn_next = QPushButton("Contact suivant")
        self.btn_call = QPushButton("Appeler")
        self.btn_call.setObjectName("PrimaryButton")
        self.btn_ptt = QPushButton("Parler")
        self.btn_hang = QPushButton("Raccrocher")
        self.btn_hang.setObjectName("DangerButton")
        self.btn_hang.setToolTip("Raccrocher (modem ATH0)")
        self.cmb_outcome = QComboBox()
        self.cmb_outcome.addItems(["Relance", "RDV", "Pas interesse", "Injoignable"])
        self.btn_close = QPushButton("Cloturer + sync PL")
        for b in (self.btn_next, self.btn_call, self.btn_ptt, self.btn_hang):
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            actions.addWidget(b)
        self.btn_close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        actions.addWidget(self.cmb_outcome)
        actions.addWidget(self.btn_close)
        center.addLayout(actions)
        lay.addLayout(center, 2)

        right = QFrame()
        right.setObjectName("ProspectorCard")
        clamp_panel_width(right, min_w=248, max_w=300)
        rl = QVBoxLayout(right)
        rl.addWidget(QLabel("Prospect"))
        self.lbl_prospect_card = QLabel("—")
        self.lbl_prospect_card.setWordWrap(True)
        rl.addWidget(self.lbl_prospect_card)
        rl.addWidget(QLabel("Intent & score"))
        self.lbl_intent = QLabel("STT actif — pas de predict MVP")
        self.lbl_intent.setWordWrap(True)
        rl.addWidget(self.lbl_intent)
        rl.addWidget(QLabel("Prochaine action"))
        self.lbl_next_action = QLabel("Rappeler —")
        rl.addWidget(self.lbl_next_action)
        rl.addStretch()
        self.lbl_status = QLabel("Pret")
        rl.addWidget(self.lbl_status)
        self.meter_line = LevelMeterBar()
        self.meter_mic = LevelMeterBar()
        rl.addWidget(QLabel("Ligne"))
        rl.addWidget(self.meter_line)
        rl.addWidget(QLabel("Micro"))
        rl.addWidget(self.meter_mic)
        lay.addWidget(right)

    @staticmethod
    def _style_chat_surface(chat: ChatTimelineWidget, bg: str) -> None:
        """Harmonise le fil chat avec le theme Prospector."""
        chat._scroll.viewport().setStyleSheet(f"background-color: {bg}; border: none;")
        chat._inner.setStyleSheet(f"background-color: {bg};")

    def refresh_theme(self, mode: ThemeMode) -> None:
        """Met a jour surfaces hors QSS (timeline chat)."""
        t = tokens_for(mode)
        self._style_chat_surface(self.chat, t.input_bg)
        apply_prospector_card_shadow(self.hero, mode=mode)
        apply_prospector_card_shadow(self.chat_wrap, mode=mode)


class SoftphonePage(QWidget):
    """Maquette Line + Prospection (clavier + timeline)."""

    PAD = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "0", "#"]
    PAD_LETTERS = {
        "1": "",
        "2": "ABC",
        "3": "DEF",
        "4": "GHI",
        "5": "JKL",
        "6": "MNO",
        "7": "PQRS",
        "8": "TUV",
        "9": "WXYZ",
        "*": "+",
        "0": "",
        "#": "",
    }

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        app = QApplication.instance()
        if app:
            app.installEventFilter(self)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(14)

        dial = QFrame()
        dial.setObjectName("ProspectorCard")
        clamp_panel_width(dial, min_w=300, max_w=360)
        dl = QVBoxLayout(dial)
        self.lbl_modem_status = QLabel("COM modem —")
        self.lbl_modem_status.setObjectName("StatePillLive")
        dl.addWidget(self.lbl_modem_status)
        self.txt_dial = QLineEdit()
        self.txt_dial.setPlaceholderText("Numero")
        self.txt_dial.setObjectName("DialNumberField")
        dl.addWidget(self.txt_dial)
        self.avatar = CallAvatarWidget()
        self.avatar.set_letter("P")
        dl.addWidget(self.avatar, alignment=Qt.AlignmentFlag.AlignCenter)
        self.lbl_prospect = QLabel("Prospect")
        self.lbl_prospect.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dl.addWidget(self.lbl_prospect)

        grid = QGridLayout()
        for i, d in enumerate(self.PAD):
            btn = DialPadButton(d, self.PAD_LETTERS.get(d, ""))
            btn.clicked.connect(lambda checked=False, digit=d: self._append(digit))
            grid.addWidget(btn, i // 3, i % 3)
        dl.addLayout(grid)
        row = QHBoxLayout()
        self.btn_dial_call = QPushButton("Appeler")
        self.btn_dial_call.setObjectName("SuccessButton")
        self.btn_dial_hang = QPushButton("Raccrocher")
        self.btn_dial_hang.setObjectName("DangerButton")
        self.btn_dial_hang.setToolTip("Raccrocher et liberer la ligne (modem ATH0)")
        row.addWidget(self.btn_dial_call)
        row.addWidget(self.btn_dial_hang)
        dl.addLayout(row)
        lay.addWidget(dial)

        right = QVBoxLayout()
        tabs = QHBoxLayout()
        tabs.setSpacing(0)
        self._tab_group = QButtonGroup(self)
        for i, t in enumerate(("Prospection", "Entreprises", "Contacts", "Campagnes")):
            b = QPushButton(t)
            b.setObjectName("TopTab")
            b.setCheckable(True)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            if i == 0:
                b.setChecked(True)
            self._tab_group.addButton(b, i)
            tabs.addWidget(b)
        tabs.addStretch()
        right.addLayout(tabs)
        tl = QLabel("Prospect · Timeline")
        tl.setObjectName("PageSubtitle")
        right.addWidget(tl)
        self.timeline = QListWidget()
        right.addWidget(self.timeline, 1)
        self.txt_notes = QPlainTextEdit()
        self.txt_notes.setPlaceholderText("Ajoutez une note interne…")
        right.addWidget(self.txt_notes)
        lay.addLayout(right, 1)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: ANN001
        """
        Pavé numérique et chiffres : remplissent le champ numero hors focus notes.

        Filtre application : agit seulement sur cette page quand le focus est dedans.
        Les touches avec ``KeypadModifier`` sont prioritaires (vrai pave USB).
        """
        if event.type() != QEvent.Type.KeyPress:
            return False
        ke = event
        if not isinstance(ke, QKeyEvent):
            return False
        app = QApplication.instance()
        fw = app.focusWidget() if app else None
        if fw is None or not self.isAncestorOf(fw):
            return False
        if fw is self.txt_dial:
            return False
        if fw is self.txt_notes:
            return False

        digit = self._key_to_dial_char(ke)
        if digit is not None:
            self._append(digit)
            return True
        if ke.key() == Qt.Key.Key_Backspace and ke.modifiers() == Qt.KeyboardModifier.NoModifier:
            self._backspace_dial()
            return True
        return False

    @staticmethod
    def _key_to_dial_char(ke: QKeyEvent) -> Optional[str]:
        """
        Convertit une touche clavier en caractere de numerotation.

        @param ke Evenement touche.
        @returns Un chiffre ou ``*`` / ``#`` / ``+`` ou None.
        """
        k = ke.key()
        mods = ke.modifiers()
        keypad = bool(mods & Qt.KeyboardModifier.KeypadModifier)
        mainpad = (mods & ~Qt.KeyboardModifier.KeypadModifier) == Qt.KeyboardModifier.NoModifier
        if k == Qt.Key.Key_Plus and (keypad or ke.text() == "+"):
            return "+"
        if k == Qt.Key.Key_Asterisk and keypad:
            return "*"
        if k == Qt.Key.Key_NumberSign and (keypad or mainpad):
            return "#"
        if k == Qt.Key.Key_Period and keypad:
            return "#"
        if Qt.Key.Keypad0 <= k <= Qt.Key.Keypad9:
            return str(k - int(Qt.Key.Keypad0))
        if keypad and Qt.Key.Key_0 <= k <= Qt.Key.Key_9:
            return str(k - int(Qt.Key.Key_0))
        if mainpad and Qt.Key.Key_0 <= k <= Qt.Key.Key_9:
            return str(k - int(Qt.Key.Key_0))
        ch = ke.text()
        if mainpad and len(ch) == 1 and ch in "*#+":
            return ch
        return None

    def _backspace_dial(self) -> None:
        """Efface le dernier chiffre du numero."""
        t = self.txt_dial.text()
        if t:
            self.txt_dial.setText(t[:-1])

    def _append(self, digit: str) -> None:
        self.txt_dial.setText(self.txt_dial.text() + digit)


class EntrantsPage(QWidget):
    """Ecoute entrants + historique (contexte maquette entrant)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.addWidget(self._title("Appels entrants"))
        lay.addWidget(self._subtitle("Modem en ecoute — overlay maquette au ring"))
        row = QHBoxLayout()
        self.btn_listen_start = QPushButton("Demarrer ecoute")
        self.btn_listen_start.setObjectName("PrimaryButton")
        self.btn_listen_stop = QPushButton("Arreter")
        row.addWidget(self.btn_listen_start)
        row.addWidget(self.btn_listen_stop)
        row.addStretch()
        self.lbl_listen = QLabel("Arrete")
        row.addWidget(self.lbl_listen)
        lay.addLayout(row)
        self.table_incoming = QTableWidget(0, 4)
        self.table_incoming.setHorizontalHeaderLabels(["Date", "Numero", "Action", "Match"])
        self.table_incoming.setAlternatingRowColors(True)
        self.table_incoming.setShowGrid(False)
        self.table_incoming.verticalHeader().setVisible(False)
        lay.addWidget(self.table_incoming, 1)

    @staticmethod
    def _title(text: str) -> QLabel:
        lb = QLabel(text)
        lb.setObjectName("PageTitle")
        return lb

    @staticmethod
    def _subtitle(text: str) -> QLabel:
        lb = QLabel(text)
        lb.setObjectName("PageSubtitle")
        return lb


class HistoryPage(QWidget):
    """Historique des appels + lecteur WAV."""

    play_requested = Signal()
    stop_requested = Signal()
    delete_selected = Signal()
    clear_all = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)
        head = QHBoxLayout()
        head.addWidget(self._title("Historique"))
        head.addStretch()
        self.btn_refresh = QPushButton("Actualiser")
        self.btn_refresh.setObjectName("OutlineButton")
        self.btn_delete = QPushButton("Supprimer la selection")
        self.btn_delete.setObjectName("DangerButton")
        self.btn_clear_all = QPushButton("Vider l'historique")
        self.btn_clear_all.setObjectName("DangerButton")
        head.addWidget(self.btn_refresh)
        head.addWidget(self.btn_delete)
        head.addWidget(self.btn_clear_all)
        root.addLayout(head)
        sub = self._subtitle("Journal des sessions et ecoute des enregistrements (L = correspondant, R = votre micro).")
        sub.setWordWrap(True)
        root.addWidget(sub)

        split = QHBoxLayout()
        split.setSpacing(16)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Date", "Sens", "Numero", "Societe", "Duree", "Statut", "WAV"]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._on_row_selected)
        self.table.cellDoubleClicked.connect(lambda _r, _c: self.play_requested.emit())
        split.addWidget(self.table, 3)

        player_card = QFrame()
        player_card.setObjectName("ProspectorCard")
        pc_lay = QVBoxLayout(player_card)
        pc_lay.setContentsMargins(18, 16, 18, 16)
        pc_lay.setSpacing(10)
        pc_lay.addWidget(self._section_title("Lecteur"))
        self.lbl_file = QLabel("Selectionnez un appel dans la liste.")
        self.lbl_file.setObjectName("PageSubtitle")
        self.lbl_file.setWordWrap(True)
        pc_lay.addWidget(self.lbl_file)
        self.cmb_channel = QComboBox()
        self.cmb_channel.setObjectName("SettingsCombo")
        self.cmb_channel.addItem("Ligne — correspondant (L)", "line")
        self.cmb_channel.addItem("Mix stereo (L+R)", "stereo")
        self.cmb_channel.addItem("Micro agent (R, PTT seulement)", "mic")
        self.cmb_channel.setCurrentIndex(0)
        self.cmb_channel.setMinimumHeight(44)
        pc_lay.addWidget(QLabel("Piste"))
        pc_lay.addWidget(self.cmb_channel)
        self.lbl_progress = QLabel("00:00 / 00:00")
        self.lbl_progress.setObjectName("FormHint")
        pc_lay.addWidget(self.lbl_progress)
        btn_row = QHBoxLayout()
        self.btn_play = QPushButton("Lire")
        self.btn_play.setObjectName("PrimaryButton")
        self.btn_play.setMinimumHeight(42)
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setObjectName("OutlineButton")
        self.btn_stop.setMinimumHeight(42)
        self.btn_open = QPushButton("Ouvrir dossier")
        self.btn_open.setObjectName("OutlineButton")
        self.btn_open.setMinimumHeight(42)
        btn_row.addWidget(self.btn_play)
        btn_row.addWidget(self.btn_stop)
        btn_row.addWidget(self.btn_open)
        pc_lay.addLayout(btn_row)
        self.lbl_player_status = QLabel("")
        self.lbl_player_status.setObjectName("FormHint")
        self.lbl_player_status.setWordWrap(True)
        pc_lay.addWidget(self.lbl_player_status)
        pc_lay.addStretch()
        split.addWidget(player_card, 2)
        root.addLayout(split, 1)

        self._wav_by_row: dict[int, str] = {}
        self.wav_player = CallWavPlayer(self)
        self.wav_player.position_changed.connect(self._on_playback_position)
        self.wav_player.error.connect(self._on_player_error)
        self.wav_player.finished.connect(self._on_player_finished)
        self.btn_play.clicked.connect(self.play_requested.emit)
        self.btn_stop.clicked.connect(self.stop_requested.emit)
        self.btn_delete.clicked.connect(self.delete_selected.emit)
        self.btn_clear_all.clicked.connect(self.clear_all.emit)

    def selected_session_id(self) -> Optional[int]:
        """Id ``call_session`` de la ligne selectionnee."""
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if item is None:
            return None
        raw = item.data(Qt.ItemDataRole.UserRole)
        try:
            return int(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None

    def selected_wav_path(self) -> Optional[Path]:
        """Chemin WAV de la ligne selectionnee."""
        row = self.table.currentRow()
        if row < 0:
            return None
        p = self._wav_by_row.get(row)
        if not p:
            return None
        path = Path(p)
        return path if path.is_file() else None

    def selected_channel(self) -> str:
        """Mode ``stereo`` / ``line`` / ``mic``."""
        data = self.cmb_channel.currentData()
        return str(data or "stereo")

    def set_sessions(self, rows: list[dict[str, Any]]) -> None:
        """
        Remplit le tableau historique.

        @param rows Dicts produits par l'application (voir ``app._refresh_journal``).
        """
        self.table.setRowCount(0)
        self._wav_by_row.clear()
        for r, row in enumerate(rows):
            self.table.insertRow(r)
            for c, key in enumerate(
                ("started", "direction", "phone", "company", "duration", "outcome", "wav_flag")
            ):
                item = QTableWidgetItem(str(row.get(key, "")))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(r, c, item)
            wav = row.get("wav_path")
            if wav:
                self._wav_by_row[r] = str(wav)
            item0 = self.table.item(r, 0)
            if item0 is not None:
                item0.setData(Qt.ItemDataRole.UserRole, row.get("id"))
        if rows:
            self.table.selectRow(0)
            self._on_row_selected()

    def _on_row_selected(self) -> None:
        path = self.selected_wav_path()
        if path:
            dur = wav_duration_seconds(path)
            m, s = divmod(int(dur), 60)
            self.lbl_file.setText(path.name)
            self.lbl_progress.setText(f"00:00 / {m:02d}:{s:02d}")
            self.btn_play.setEnabled(True)
            self.btn_open.setEnabled(True)
        else:
            row = self.table.currentRow()
            wav_hint = self.table.item(row, 6).text() if row >= 0 else ""
            self.lbl_file.setText("Pas d'enregistrement pour cette session." if wav_hint == "—" else wav_hint)
            self.btn_play.setEnabled(False)
            self.btn_open.setEnabled(False)

    def open_wav_in_explorer(self) -> None:
        """Ouvre l'explorateur sur le fichier selectionne."""
        path = self.selected_wav_path()
        if path is None:
            return
        try:
            if sys.platform == "win32":
                subprocess.run(["explorer", "/select,", str(path)], check=False)
            else:
                os.startfile(path.parent)  # type: ignore[attr-defined]
        except Exception:
            pass

    def _on_playback_position(self, pos_s: float, total_s: float) -> None:
        ps, m1, s1 = int(pos_s), *divmod(int(pos_s), 60)
        m2, s2 = divmod(int(total_s), 60)
        self.lbl_progress.setText(f"{m1:02d}:{s1:02d} / {m2:02d}:{s2:02d}")

    def _on_player_error(self, msg: str) -> None:
        self.lbl_player_status.setText(msg)

    def _on_player_finished(self) -> None:
        self.lbl_player_status.setText("Lecture terminee.")

    def set_player_status(self, text: str) -> None:
        """Message court sous les boutons."""
        self.lbl_player_status.setText(text)

    @staticmethod
    def _section_title(text: str) -> QLabel:
        lb = QLabel(text)
        lb.setObjectName("CardSectionTitle")
        return lb

    @staticmethod
    def _title(text: str) -> QLabel:
        lb = QLabel(text)
        lb.setObjectName("PageTitle")
        return lb

    @staticmethod
    def _subtitle(text: str) -> QLabel:
        lb = QLabel(text)
        lb.setObjectName("PageSubtitle")
        return lb


class SettingsPage(QWidget):
    """Parametres connexions — formulaire lisible, cartes, scroll."""

    call_line_gain_changed = Signal(int)
    record_calls_changed = Signal(bool)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        header = QVBoxLayout()
        header.setSpacing(4)
        header.addWidget(self._title("Parametres"))
        sub = self._subtitle(
            "ProspectLab, modem USB et peripheriques audio. "
            "Les valeurs ProspectLab sont enregistrees dans prospector.env."
        )
        sub.setWordWrap(True)
        header.addWidget(sub)
        root.addLayout(header)

        scroll = QScrollArea()
        scroll.setObjectName("SettingsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        body = QWidget()
        body.setObjectName("SettingsBody")
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(0, 4, 8, 24)
        body_lay.setSpacing(16)

        card_pl = QFrame()
        card_pl.setObjectName("ProspectorCard")
        pl_lay = QVBoxLayout(card_pl)
        pl_lay.setContentsMargins(20, 18, 20, 18)
        pl_lay.setSpacing(6)
        pl_lay.addWidget(self._section_title("ProspectLab"))
        pl_lay.addWidget(
            self._hint("API publique pour synchroniser les groupes et pousser les statuts d appels.")
        )

        self.txt_pl_url = QLineEdit()
        self.txt_pl_url.setObjectName("SettingsField")
        self.txt_pl_url.setPlaceholderText("http://node15.lan:5000")
        self.txt_pl_url.setClearButtonEnabled(True)
        pl_lay.addLayout(
            self._field_block(
                "URL du serveur",
                "Sans /api/public — ex. http://node15.lan:5000",
                self.txt_pl_url,
            )
        )

        self.txt_pl_token = QLineEdit()
        self.txt_pl_token.setObjectName("SettingsField")
        self.txt_pl_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_pl_token.setPlaceholderText("Token Bearer fourni par ProspectLab")
        self.txt_pl_token.setClearButtonEnabled(True)
        token_row = QVBoxLayout()
        token_row.setSpacing(6)
        token_row.addLayout(
            self._field_block(
                "Token d acces",
                "Ne le partage pas ; stocke-le via Enregistrer.",
                self.txt_pl_token,
            )
        )
        self.chk_show_token = QCheckBox("Afficher le token")
        self.chk_show_token.setObjectName("FormCheck")
        self.chk_show_token.toggled.connect(self._on_toggle_token_visibility)
        token_row.addWidget(self.chk_show_token)
        pl_lay.addLayout(token_row)

        actions = QHBoxLayout()
        actions.setSpacing(12)
        self.btn_save_pl = QPushButton("Enregistrer ProspectLab")
        self.btn_save_pl.setObjectName("PrimaryButton")
        self.btn_save_pl.setMinimumHeight(44)
        self.btn_flush_outbox = QPushButton("Sync file PATCH en attente")
        self.btn_flush_outbox.setObjectName("OutlineButton")
        self.btn_flush_outbox.setMinimumHeight(44)
        actions.addWidget(self.btn_save_pl)
        actions.addWidget(self.btn_flush_outbox)
        actions.addStretch()
        pl_lay.addLayout(actions)
        body_lay.addWidget(card_pl)

        card_hw = QFrame()
        card_hw.setObjectName("ProspectorCard")
        hw_lay = QVBoxLayout(card_hw)
        hw_lay.setContentsMargins(20, 18, 20, 18)
        hw_lay.setSpacing(6)
        hw_lay.addWidget(self._section_title("Modem et audio"))
        hw_lay.addWidget(self._hint("Port serie du modem USB VocalGuard et peripheriques pour appels et sons UI."))

        self.cmb_com = QComboBox()
        self.cmb_com.setObjectName("SettingsCombo")
        hw_lay.addLayout(
            self._field_block("Port COM", "Detecte automatiquement quand le modem est branche.", self.cmb_com)
        )
        self.cmb_in = QComboBox()
        self.cmb_in.setObjectName("SettingsCombo")
        hw_lay.addLayout(self._field_block("Micro (entree)", None, self.cmb_in))
        self.cmb_out = QComboBox()
        self.cmb_out.setObjectName("SettingsCombo")
        hw_lay.addLayout(self._field_block("Casque / sortie", None, self.cmb_out))

        call_vol = QHBoxLayout()
        call_vol.setSpacing(12)
        self.slider_call_line = QSlider(Qt.Orientation.Horizontal)
        self.slider_call_line.setObjectName("VolumeSlider")
        self.slider_call_line.setRange(5, 100)
        self.slider_call_line.setValue(22)
        self.slider_call_line.setFixedWidth(280)
        self.lbl_call_line_gain = QLabel("22 %")
        self.lbl_call_line_gain.setObjectName("VolumePct")
        self.lbl_call_line_gain.setFixedWidth(44)
        self.slider_call_line.valueChanged.connect(self._on_call_line_slider)
        call_vol.addWidget(self.slider_call_line)
        call_vol.addWidget(self.lbl_call_line_gain)
        call_vol.addStretch()
        vol_lbl = QLabel("Volume ecoute appel")
        vol_lbl.setObjectName("FormLabel")
        hw_lay.addWidget(vol_lbl)
        hw_lay.addWidget(
            self._hint("Voix entendue dans le casque pendant un appel (pas les bips UI).")
        )
        hw_lay.addLayout(call_vol)
        body_lay.addWidget(card_hw)

        self.volume_panel = VolumeControlPanel()
        body_lay.addWidget(self.volume_panel)

        card_rec = QFrame()
        card_rec.setObjectName("ProspectorCard")
        rec_lay = QVBoxLayout(card_rec)
        rec_lay.setContentsMargins(20, 18, 20, 18)
        rec_lay.addWidget(self._section_title("Enregistrement appels"))
        rec_lay.addWidget(
            self._hint(
                "Chaque appel produit un WAV stereo (gauche = correspondant, droite = ton micro PTT). "
                "Fichiers dans Documents/VocalGuard/prospector/recordings. "
                "Si la ligne est trop forte dans le fichier : VG_PROSPECTOR_RECORD_LINE_GAIN=0.3 dans prospector.env."
            )
        )
        self.chk_record_calls = QCheckBox("Enregistrer chaque appel automatiquement")
        self.chk_record_calls.setObjectName("FormCheck")
        self.chk_record_calls.setChecked(True)
        self.chk_record_calls.toggled.connect(self.record_calls_changed.emit)
        rec_lay.addWidget(self.chk_record_calls)
        body_lay.addWidget(card_rec)
        body_lay.addStretch()

        scroll.setWidget(body)
        root.addWidget(scroll, 1)

    def set_call_line_gain_percent(self, percent: int) -> None:
        """Sync slider depuis prefs."""
        p = max(5, min(100, int(percent)))
        self.slider_call_line.blockSignals(True)
        self.slider_call_line.setValue(p)
        self.slider_call_line.blockSignals(False)
        self.lbl_call_line_gain.setText(f"{p} %")

    def _on_call_line_slider(self, value: int) -> None:
        self.lbl_call_line_gain.setText(f"{value} %")
        self.call_line_gain_changed.emit(value)

    def _on_toggle_token_visibility(self, checked: bool) -> None:
        """Bascule masque / clair pour le token."""
        mode = QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        self.txt_pl_token.setEchoMode(mode)

    @staticmethod
    def _section_title(text: str) -> QLabel:
        lb = QLabel(text)
        lb.setObjectName("CardSectionTitle")
        return lb

    @staticmethod
    def _hint(text: str) -> QLabel:
        lb = QLabel(text)
        lb.setObjectName("FormHint")
        lb.setWordWrap(True)
        return lb

    @staticmethod
    def _field_block(title: str, hint: Optional[str], field: QWidget) -> QVBoxLayout:
        """
        Libelle + aide + champ avec espacement Material.

        @param title Libelle principal.
        @param hint Sous-texte optionnel.
        @param field QLineEdit ou QComboBox.
        @returns Layout vertical pret a addLayout.
        """
        block = QVBoxLayout()
        block.setSpacing(6)
        lbl = QLabel(title)
        lbl.setObjectName("FormLabel")
        block.addWidget(lbl)
        if hint:
            h = QLabel(hint)
            h.setObjectName("FormHint")
            h.setWordWrap(True)
            block.addWidget(h)
        if isinstance(field, (QLineEdit, QComboBox)):
            field.setMinimumHeight(44)
        block.addWidget(field)
        return block

    @staticmethod
    def _title(text: str) -> QLabel:
        lb = QLabel(text)
        lb.setObjectName("PageTitle")
        return lb

    @staticmethod
    def _subtitle(text: str) -> QLabel:
        lb = QLabel(text)
        lb.setObjectName("PageSubtitle")
        return lb
