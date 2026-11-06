"""Ecrans Prospector calques sur les maquettes JPG."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from desktop.prospector.ui.layout_helpers import clamp_panel_width

from desktop.studio_ui_material import (
    CallAvatarWidget,
    ChatTimelineWidget,
    CollapsibleSection,
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
        self.btn_bar_hang.setToolTip("Raccrocher")
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

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
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
        dl.addWidget(self.txt_dial)
        self.avatar = CallAvatarWidget()
        self.avatar.set_letter("P")
        dl.addWidget(self.avatar, alignment=Qt.AlignmentFlag.AlignCenter)
        self.lbl_prospect = QLabel("Prospect")
        self.lbl_prospect.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dl.addWidget(self.lbl_prospect)

        grid = QGridLayout()
        for i, d in enumerate(self.PAD):
            btn = DialPadButton(d)
            btn.clicked.connect(lambda checked=False, digit=d: self._append(digit))
            grid.addWidget(btn, i // 3, i % 3)
        dl.addLayout(grid)
        row = QHBoxLayout()
        self.btn_dial_call = QPushButton("Appeler")
        self.btn_dial_call.setObjectName("SuccessButton")
        self.btn_dial_hang = QPushButton("Raccrocher")
        self.btn_dial_hang.setObjectName("DangerButton")
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


class SettingsPage(QWidget):
    """Parametres connexions."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.addWidget(self._title("Parametres"))
        self.txt_pl_url = QLineEdit()
        self.txt_pl_token = QLineEdit()
        self.txt_pl_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.cmb_com = QComboBox()
        self.cmb_in = QComboBox()
        self.cmb_out = QComboBox()
        form = QWidget()
        fl = QVBoxLayout(form)
        for label, w in (
            ("PROSPECTLAB_URL", self.txt_pl_url),
            ("PROSPECTLAB_TOKEN", self.txt_pl_token),
            ("Port COM", self.cmb_com),
            ("Micro", self.cmb_in),
            ("Casque", self.cmb_out),
        ):
            fl.addWidget(QLabel(label))
            fl.addWidget(w)
        section = CollapsibleSection("Connexions")
        section.set_content_widget(form)
        section.expand()
        lay.addWidget(section)
        self.volume_panel = VolumeControlPanel()
        lay.addWidget(self.volume_panel)
        self.btn_flush_outbox = QPushButton("Sync file PATCH en attente")
        lay.addWidget(self.btn_flush_outbox)
        lay.addStretch()

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
