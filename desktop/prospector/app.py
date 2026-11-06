#!/usr/bin/env python3
"""
VocalGuard Prospector — UI maquettes + logique metier.
"""

from __future__ import annotations

import os
import queue
import sys
import threading
from pathlib import Path
from typing import Callable, Optional

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from PySide6.QtCore import Qt, QThread, QTimer, Signal  # noqa: E402
from PySide6.QtGui import QFont, QIcon, QColor  # noqa: E402
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QTableWidgetItem  # noqa: E402

from desktop.audio_core import AudioDeviceHelper  # noqa: E402
from desktop.modem_local_call import list_com_ports  # noqa: E402
from desktop.prospector.campaign_store import CampaignStore  # noqa: E402
from desktop.prospector.call_session import answer_incoming_call, run_outbound_call  # noqa: E402
from desktop.prospector.db.migrate import upgrade_head  # noqa: E402
from desktop.prospector.db.models import PlEntreprise, QueueItem  # noqa: E402
from desktop.prospector.db.session import SessionLocal, get_engine  # noqa: E402
from desktop.prospector.incoming_match import match_incoming_caller  # noqa: E402
from desktop.prospector.modem_listen import IncomingListenWorker  # noqa: E402
from desktop.prospector.phone_utils import phone_digits  # noqa: E402
from desktop.prospector.prospectlab_client import ProspectLabClient, ProspectLabError  # noqa: E402
from desktop.prospector.settings import (  # noqa: E402
    load_prospector_env,
    modem_baudrate,
    modem_com_port,
    prospectlab_api_prefix,
    prospectlab_token,
)
from desktop.prospector.sounds import ProspectorSounds  # noqa: E402
from desktop.prospector.ui_prefs import load_prefs, save_prefs  # noqa: E402
from desktop.prospector.stt_ws_client import SttWsClient  # noqa: E402
from desktop.prospector.ui.layout_helpers import apply_main_window_geometry  # noqa: E402
from desktop.prospector.ui.overlay import IncomingCallOverlay  # noqa: E402
from desktop.prospector.ui.shell import ProspectorShell  # noqa: E402
from desktop.prospector.ui.splash import ProspectorSplashScreen  # noqa: E402
from desktop.prospector.ui.styles import prospector_stylesheet  # noqa: E402
from desktop.prospector.ui.theme_tokens import ThemeMode  # noqa: E402


def _icon_path() -> Path:
    p = Path(__file__).resolve().parent.parent / "assets" / "commercial_studio.ico"
    return p if p.is_file() else Path(__file__).resolve().parent.parent / "assets" / "line_phone.ico"


class CallWorker(QThread):
    """Thread appel sortant ou entrant."""

    status = Signal(str)
    failed = Signal(str)
    finished_call = Signal()
    line_level = Signal(float)
    mic_level = Signal(float)

    def __init__(
        self,
        *,
        mode: str,
        number: str,
        com_port: str,
        baudrate: int,
        input_device: Optional[int],
        output_device: Optional[int],
        on_uplink_pcm: Optional[Callable[[bytes], None]] = None,
        on_downlink_pcm: Optional[Callable[[bytes], None]] = None,
    ) -> None:
        super().__init__()
        self.mode = mode
        self.number = number
        self.com_port = com_port
        self.baudrate = baudrate
        self.input_device = input_device
        self.output_device = output_device
        self.on_uplink_pcm = on_uplink_pcm
        self.on_downlink_pcm = on_downlink_pcm
        self._hangup = threading.Event()
        self._dtmf: queue.Queue[str] = queue.Queue()
        self._ptt: queue.Queue[bool] = queue.Queue()

    def hangup(self) -> None:
        self._hangup.set()

    def ptt(self) -> None:
        self._ptt.put(True)

    def run(self) -> None:
        import asyncio

        async def _go() -> None:
            kw = dict(
                com_port=self.com_port,
                baudrate=self.baudrate,
                input_device=self.input_device,
                output_device=self.output_device,
                hangup_event=self._hangup,
                dtmf_queue=self._dtmf,
                ptt_queue=self._ptt,
                on_status=lambda m: self.status.emit(m),
                on_line_level=lambda v: self.line_level.emit(v),
                on_mic_level=lambda v: self.mic_level.emit(v),
                on_uplink_pcm=self.on_uplink_pcm,
                on_downlink_pcm=self.on_downlink_pcm,
                push_to_talk=True,
                ptt_ms=1400,
            )
            if self.mode == "incoming":
                await answer_incoming_call(**kw)
            else:
                await run_outbound_call(number=self.number, **kw)

        try:
            asyncio.run(_go())
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished_call.emit()


class ProspectorWindow(QMainWindow):
    """Fenetre principale (shell maquettes)."""

    def __init__(self, *, skip_migrate: bool = False) -> None:
        super().__init__()
        load_prospector_env()
        if not skip_migrate:
            get_engine.cache_clear()
            upgrade_head()
        self.setWindowTitle("VocalGuard Prospector")
        icon = _icon_path()
        if icon.is_file():
            self.setWindowIcon(QIcon(str(icon)))

        self._overlay: Optional[IncomingCallOverlay] = None

        self.session = SessionLocal()
        self.pl_client: Optional[ProspectLabClient] = None
        try:
            if prospectlab_api_prefix() and prospectlab_token():
                self.pl_client = ProspectLabClient()
        except ProspectLabError:
            self.pl_client = None
        self.store = CampaignStore(self.session, self.pl_client)

        in_names, out_names, in_map, out_map = AudioDeviceHelper.list_devices()
        self.in_map = in_map
        self.out_map = out_map
        self._in_names = in_names
        self._out_names = out_names

        self.sounds = ProspectorSounds(self._out_dev)

        self.shell = ProspectorShell()
        self.setCentralWidget(self.shell)
        self.pf = self.shell.page_file
        self.pc = self.shell.page_cockpit
        self.ps = self.shell.page_softphone
        self.pe = self.shell.page_entrants
        self.pp = self.shell.page_pilotage
        self.pcfg = self.shell.page_settings

        self._fill_settings_combos()
        self._wire_ui()
        self._wire_sounds()
        self._wire_theme()

        self.call_worker: Optional[CallWorker] = None
        self.listen_worker: Optional[IncomingListenWorker] = None
        self.stt: Optional[SttWsClient] = None
        self._active_call_session_id: Optional[int] = None
        self._active_queue_id: Optional[int] = None
        self._incoming_number = ""
        self._call_seconds = 0
        self._call_timer = QTimer(self)
        self._call_timer.setInterval(1000)
        self._call_timer.timeout.connect(self._tick_call_timer)

        self.shell.set_page(1)
        self._refresh_groupes_list()
        self._refresh_queue_table()
        self._refresh_kpis()
        self._refresh_journal()
        apply_main_window_geometry(self)

    def _fill_settings_combos(self) -> None:
        self.pcfg.txt_pl_url.setText(os.environ.get("PROSPECTLAB_URL", ""))
        self.pcfg.txt_pl_token.setText(prospectlab_token())
        for port, desc in list_com_ports():
            self.pcfg.cmb_com.addItem(f"{port} — {desc}", port)
        pref = modem_com_port()
        if pref:
            ix = self.pcfg.cmb_com.findData(pref)
            if ix >= 0:
                self.pcfg.cmb_com.setCurrentIndex(ix)
        for name in self._in_names:
            if name in self.in_map:
                self.pcfg.cmb_in.addItem(name, self.in_map[name])
        for name in self._out_names:
            if name in self.out_map:
                self.pcfg.cmb_out.addItem(name, self.out_map[name])
        com_label = self._com_port() or "non configure"
        self.ps.lbl_modem_status.setText(f"COM modem {com_label}")

    def _wire_ui(self) -> None:
        self.pf.btn_sync_groupes.clicked.connect(self._sync_groupes_api)
        self.pf.btn_import.clicked.connect(self._import_selected_groupe)
        self.pf.btn_clear.clicked.connect(self._clear_queue_todo)
        self.pf.btn_refresh_queue.clicked.connect(self._refresh_queue_table)
        self.pf.cmb_filter_groupe.currentIndexChanged.connect(self._refresh_queue_table)
        self.pf.cmb_filter_status.currentIndexChanged.connect(self._refresh_queue_table)

        self.pc.btn_next.clicked.connect(self._pick_next_contact)
        self.pc.btn_call.clicked.connect(self._start_outbound)
        self.pc.btn_ptt.clicked.connect(self._ptt)
        self.pc.btn_hang.clicked.connect(self._hangup_call)
        self.pc.btn_close.clicked.connect(self._close_call_sync)

        self.ps.btn_dial_call.clicked.connect(self._start_manual_dial)
        self.ps.btn_dial_hang.clicked.connect(self._hangup_call)
        self.pf.btn_bar_hang.clicked.connect(self._hangup_call)

        self.pe.btn_listen_start.clicked.connect(self._start_listen)
        self.pe.btn_listen_stop.clicked.connect(self._stop_listen)

        self.pcfg.btn_flush_outbox.clicked.connect(self._flush_outbox)

    def _wire_sounds(self) -> None:
        """Volume header + parametres, branche sur ProspectorSounds."""
        self.shell.volume.set_volume_percent(self.sounds.volume_percent)
        self.shell.volume.set_muted(self.sounds.muted)
        self.pcfg.volume_panel.set_volume_percent(self.sounds.volume_percent)
        self.pcfg.volume_panel.set_muted(self.sounds.muted)

        self.shell.volume.volume_changed.connect(self._set_ui_volume)
        self.shell.volume.mute_changed.connect(self._set_ui_muted)
        self.shell.volume.test_requested.connect(self.sounds.play_test_beep)
        self.pcfg.volume_panel.volume_changed.connect(self._set_ui_volume)
        self.pcfg.volume_panel.mute_changed.connect(self._set_ui_muted)
        self.pcfg.volume_panel.test_requested.connect(self.sounds.play_test_beep)

    def _set_ui_volume(self, percent: int) -> None:
        self.sounds.set_volume_percent(percent)
        self.shell.volume.set_volume_percent(percent)
        self.pcfg.volume_panel.set_volume_percent(percent)

    def _set_ui_muted(self, muted: bool) -> None:
        self.sounds.set_muted(muted)
        self.shell.volume.set_muted(muted)
        self.pcfg.volume_panel.set_muted(muted)

    def _initial_theme(self) -> ThemeMode:
        raw = str(load_prefs().get("theme", "light"))
        return "light" if raw == "light" else "dark"

    def _apply_theme(self, mode: ThemeMode) -> None:
        """Bascule QSS + icones (M3 clair / sombre)."""
        app = QApplication.instance()
        if app:
            app.setStyleSheet(prospector_stylesheet(mode))
        self.shell.apply_theme(mode)
        self.shell.header_tools.theme_switch.set_mode(mode)
        if hasattr(self.pc, "refresh_theme"):
            self.pc.refresh_theme(mode)
        save_prefs(theme=mode)

    def _wire_theme(self) -> None:
        mode = self._initial_theme()
        self._apply_theme(mode)
        self.shell.header_tools.theme_switch.theme_changed.connect(self._apply_theme)

    @property
    def chat(self):
        return self.pc.chat

    def _pl(self) -> ProspectLabClient:
        if self.pl_client is None:
            url = self.pcfg.txt_pl_url.text().strip()
            tok = self.pcfg.txt_pl_token.text().strip()
            if url:
                os.environ["PROSPECTLAB_URL"] = url
            if tok:
                os.environ["PROSPECTLAB_TOKEN"] = tok
            self.pl_client = ProspectLabClient()
            self.store.pl_client = self.pl_client
        return self.pl_client

    def _com_port(self) -> str:
        if self.pcfg.cmb_com.count():
            return str(self.pcfg.cmb_com.currentData() or "")
        return modem_com_port()

    def _in_dev(self):
        return self.pcfg.cmb_in.currentData()

    def _out_dev(self):
        return self.pcfg.cmb_out.currentData()

    def _selected_groupe_pl_id(self) -> Optional[int]:
        item = self.pf.list_groupes.currentItem()
        if item is None:
            return None
        return int(item.data(Qt.ItemDataRole.UserRole))

    def _refresh_kpis(self) -> None:
        sessions = self.store.list_call_sessions(500)
        n = len(sessions)
        rdv = sum(1 for s in sessions if s.outcome and "RDV" in s.outcome.upper())
        deco = sum(1 for s in sessions if s.outcome)
        pct = int(100 * deco / n) if n else 0
        self.shell.kpi_calls.setText(f"{n} appels")
        self.shell.kpi_deco.setText(f"{pct}% decroches")
        self.shell.kpi_rdv.setText(f"{rdv} RDV")
        self.pp.card_calls.lbl_value.setText(str(n))
        self.pp.card_deco.lbl_value.setText(f"{pct}%")
        self.pp.card_rdv.lbl_value.setText(str(rdv))
        self.pp.list_activity.clear()
        for s in sessions[:6]:
            self.pp.list_activity.addItem(
                f"{s.started_at:%H:%M} · {s.direction} · {s.outcome or '—'}"
            )
        if sessions:
            self.pp.activity_stack.setCurrentWidget(self.pp.list_activity)
        else:
            self.pp.activity_stack.setCurrentWidget(self.pp.empty_activity)

    def _refresh_groupes_list(self) -> None:
        self.pf.list_groupes.clear()
        self.pf.cmb_filter_groupe.clear()
        self.pf.cmb_filter_groupe.addItem("Tous groupes", None)
        for g in self.store.list_groupes_local():
            label = f"{g.nom} ({g.entreprises_count})"
            from PySide6.QtWidgets import QListWidgetItem

            it = QListWidgetItem(label)
            it.setData(Qt.ItemDataRole.UserRole, g.prospectlab_id)
            self.pf.list_groupes.addItem(it)
            self.pf.cmb_filter_groupe.addItem(label, g.id)

    def _sync_groupes_api(self) -> None:
        try:
            n = self.store.refresh_groupes_from_api(self._pl())
            QMessageBox.information(self, "Groupes", f"{n} groupes synchronises.")
            self.sounds.play("notify")
            self._refresh_groupes_list()
        except Exception as exc:
            self.sounds.play("error")
            QMessageBox.warning(self, "Erreur", str(exc))

    def _import_selected_groupe(self) -> None:
        gid = self._selected_groupe_pl_id()
        if gid is None:
            QMessageBox.warning(self, "Import", "Selectionnez un groupe.")
            return
        try:
            batch = self.store.import_groupe_entreprises(
                gid, self._pl(), clear_queue=False, filters={"has_phone": 1}
            )
            QMessageBox.information(self, "Import", f"{batch.row_count} contacts ajoutes.")
            self.sounds.play("success")
            self._refresh_queue_table()
        except Exception as exc:
            self.sounds.play("error")
            QMessageBox.warning(self, "Erreur", str(exc))

    def _clear_queue_todo(self) -> None:
        for qi in self.store.list_queue_items(status="todo"):
            self.session.delete(qi)
        self.session.commit()
        self._refresh_queue_table()

    def _status_label(self, st: str) -> str:
        mapping = {
            "todo": "A appeler",
            "in_progress": "Appel en cours",
            "done": "RDV pris",
            "skip": "Ne pas deranger",
        }
        return mapping.get(st, st)

    def _refresh_queue_table(self) -> None:
        status = self.pf.cmb_filter_status.currentText()
        st = None if status == "all" else status
        gid = self.pf.cmb_filter_groupe.currentData()
        items = self.store.list_queue_items(status=st, groupe_local_id=gid)
        self.pf.table_queue.setRowCount(len(items))
        if items:
            self.pf.queue_stack.setCurrentWidget(self.pf.table_queue)
        else:
            self.pf.queue_stack.setCurrentWidget(self.pf.empty_queue)
        highlight = QColor(79, 55, 139, 55)
        for r, qi in enumerate(items):
            ent = qi.entreprise
            tel = self.store.dial_phone_for_entreprise(ent) or ""
            self.pf.table_queue.setItem(r, 0, QTableWidgetItem(ent.raison_sociale))
            self.pf.table_queue.setItem(r, 1, QTableWidgetItem(ent.raison_sociale.split()[0] if ent.raison_sociale else ""))
            self.pf.table_queue.setItem(r, 2, QTableWidgetItem(tel))
            st_item = QTableWidgetItem(self._status_label(qi.local_status))
            st_item.setData(Qt.ItemDataRole.UserRole, qi.local_status)
            self.pf.table_queue.setItem(r, 3, st_item)
            intent = ent.statut_pl or "—"
            self.pf.table_queue.setItem(r, 4, QTableWidgetItem(str(intent)))
            if qi.local_status == "in_progress":
                for c in range(5):
                    cell = self.pf.table_queue.item(r, c)
                    if cell:
                        cell.setBackground(highlight)

    def _pick_next_contact(self) -> None:
        qi = self.store.next_queue_item()
        if qi is None:
            QMessageBox.information(self, "File", "Aucun contact todo.")
            return
        self._active_queue_id = qi.id
        ent = qi.entreprise
        tel = self.store.dial_phone_for_entreprise(ent) or ""
        self._update_contact_ui(ent, tel)
        self.store.set_queue_status(qi.id, "in_progress")
        self._refresh_queue_table()
        self.shell.set_page(2)

    def _update_contact_ui(self, ent: PlEntreprise, tel: str) -> None:
        line = f"{ent.raison_sociale}\n{tel}\n{ent.ville or ''} · {ent.secteur or ''}"
        self.pc.lbl_prospect_card.setText(line)
        self.pc.avatar.set_letter((ent.raison_sociale[:1] or "P").upper())
        self.ps.lbl_prospect.setText(ent.raison_sociale)
        self.ps.txt_dial.setText(tel)
        self.pf.lbl_active_call.setText(f"Contact selectionne — {ent.raison_sociale}")
        self.pf.lbl_active_sub.setText(tel or "—")

    def _start_stt(self) -> None:
        self.stt = SttWsClient(
            on_partial=lambda t: self.chat.add_marie(t, meta="…"),
            on_final=lambda t: self._on_stt_final("remote", t),
        )
        self.stt.start()

    def _on_stt_final(self, speaker: str, text: str) -> None:
        if speaker == "agent":
            self.chat.add_user(text)
        else:
            self.chat.add_marie(text)
        self.pc.waveform.push_level(0.35)
        self.pf.bar_wave.push_level(0.35)
        if self._active_call_session_id:
            self.store.add_transcript_line(
                self._active_call_session_id, speaker=speaker, text=text, is_final=True
            )

    def _begin_call_ui(self, label: str) -> None:
        self.sounds.stop_ring()
        self.sounds.play("connect")
        self._call_seconds = 0
        self._call_timer.start()
        self.pf.lbl_active_call.setText(label)
        parts = label.split("—", 1)
        if len(parts) > 1:
            self.pf.lbl_active_sub.setText(parts[1].strip())
        self.pf.chip_active.setText("En cours")
        self.pf.bar_wave.set_pulse(0.65)
        self.pc.lbl_call_state.setText("En ligne")
        self._tick_call_timer()

    def _tick_call_timer(self) -> None:
        self._call_seconds += 1
        m, s = divmod(self._call_seconds, 60)
        t = f"{m:02d}:{s:02d}"
        self.pc.lbl_timer.setText(t)
        self.pf.lbl_call_timer.setText(t)

    def _end_call_ui(self) -> None:
        self._call_timer.stop()
        self.sounds.play("hangup")
        self.pf.lbl_active_call.setText("Aucun appel en cours")
        self.pf.lbl_active_sub.setText("Selectionnez un contact ou lancez le dialer")
        self.pf.lbl_call_timer.setText("00:00")
        self.pf.chip_active.setText("Actif")
        self.pf.bar_wave.set_pulse(0.0)
        self.pc.lbl_call_state.setText("Pret")
        self.pc.lbl_timer.setText("00:00")

    def _start_call_worker(self, mode: str, number: str) -> None:
        if self.call_worker is not None:
            return

        def pcm_agent(b: bytes) -> None:
            if self.stt:
                self.stt.push_pcm(b)

        def pcm_remote(b: bytes) -> None:
            if self.stt:
                self.stt.push_pcm(b)
            self.pc.waveform.push_level(min(1.0, len(b) / 8000.0))

        self.call_worker = CallWorker(
            mode=mode,
            number=number,
            com_port=self._com_port(),
            baudrate=modem_baudrate(),
            input_device=self._in_dev(),
            output_device=self._out_dev(),
            on_uplink_pcm=pcm_agent,
            on_downlink_pcm=pcm_remote,
        )
        self.call_worker.status.connect(self.pc.lbl_status.setText)
        self.call_worker.failed.connect(self._on_call_failed)
        self.call_worker.line_level.connect(self.pc.meter_line.set_level)
        self.call_worker.mic_level.connect(self.pc.meter_mic.set_level)
        self.call_worker.line_level.connect(self.pc.waveform.push_level)
        self.call_worker.finished_call.connect(self._on_call_worker_done)
        self.call_worker.start()

    def _start_outbound(self) -> None:
        qi = (
            self.session.get(QueueItem, self._active_queue_id)
            if self._active_queue_id
            else self.store.next_queue_item()
        )
        if qi is None:
            QMessageBox.warning(self, "Appel", "Aucun contact.")
            return
        tel = self.store.dial_phone_for_entreprise(qi.entreprise)
        if not tel:
            QMessageBox.warning(self, "Appel", "Pas de telephone.")
            return
        self._active_queue_id = qi.id
        cs = self.store.create_call_session(
            direction="out",
            phone_digits_val=phone_digits(tel),
            entreprise_id=qi.entreprise_id,
            queue_item_id=qi.id,
        )
        self._active_call_session_id = cs.id
        self.chat.clear()
        self.chat.add_system("Appel sortant — STT actif.")
        self._start_stt()
        self._begin_call_ui(f"Appel en cours — {qi.entreprise.raison_sociale}")
        self._start_call_worker("out", tel)
        self.shell.set_page(2)

    def _start_manual_dial(self) -> None:
        tel = self.ps.txt_dial.text().strip()
        if not tel:
            return
        self.chat.clear()
        self.chat.add_system("Appel manuel Line.")
        self._start_stt()
        self._begin_call_ui(f"Appel — {tel}")
        self._start_call_worker("out", tel)
        self.shell.set_page(2)

    def _ptt(self) -> None:
        if self.call_worker:
            self.call_worker.ptt()

    def _hangup_call(self) -> None:
        if self.call_worker:
            self.call_worker.hangup()

    def _on_call_worker_done(self) -> None:
        if self.stt:
            self.stt.commit_final()
            self.stt.stop()
            self.stt = None
        self.call_worker = None
        self._end_call_ui()
        self._refresh_kpis()

    def _close_call_sync(self) -> None:
        if not self._active_call_session_id:
            QMessageBox.warning(self, "Cloture", "Aucune session active.")
            return
        statut = self.pc.cmb_outcome.currentText()
        try:
            self.store.close_call_and_sync_pl(
                self._active_call_session_id,
                statut=statut,
                note=self.ps.txt_notes.toPlainText() or None,
                client=self.pl_client,
            )
            self._active_call_session_id = None
            self._active_queue_id = None
            self._refresh_queue_table()
            self._refresh_journal()
            self._refresh_kpis()
            QMessageBox.information(self, "Cloture", "Statut enregistre.")
            self.sounds.play("success")
        except Exception as exc:
            self.sounds.play("error")
            QMessageBox.warning(self, "Erreur", str(exc))

    def _start_listen(self) -> None:
        if self.listen_worker:
            return
        self.listen_worker = IncomingListenWorker(com_port=self._com_port())
        self.listen_worker.status.connect(self.pe.lbl_listen.setText)
        self.listen_worker.ring_detected.connect(self._on_incoming_ring)
        self.listen_worker.caller_detected.connect(self._on_incoming_cid)
        self.listen_worker.start()
        self.pe.lbl_listen.setText("Ecoute…")
        self.shell.footer.set_listen_active(True)

    def _stop_listen(self) -> None:
        if self.listen_worker:
            self.listen_worker.stop()
            self.listen_worker.wait(4000)
            self.listen_worker = None
        self.pe.lbl_listen.setText("Arrete")
        self.shell.footer.set_listen_active(False)

    def _on_incoming_ring(self) -> None:
        self._show_incoming_overlay(self._incoming_number or "Numero inconnu", "", "")

    def _on_incoming_cid(self, number: str, name: str) -> None:
        self._incoming_number = number
        ent = match_incoming_caller(self.session, number)
        company = ent.raison_sociale if ent else (name or "Inconnu")
        sub = ""
        if ent and ent.ville:
            sub = f"{ent.ville} · ProspectLab"
        self.store.log_incoming_ring(
            caller_raw=number,
            matched_entreprise_id=ent.id if ent else None,
            user_action="ringing",
        )
        self._show_incoming_overlay(number, company, sub)
        self._refresh_incoming_table()

    def _show_incoming_overlay(self, number: str, company: str, subtitle: str) -> None:
        if self._overlay:
            self._overlay.close()
        self._overlay = IncomingCallOverlay(
            self, number=number, company=company, subtitle=subtitle
        )
        self._overlay.answer.connect(self._answer_incoming)
        self._overlay.reject.connect(self._reject_incoming)
        self._overlay.ignore.connect(lambda: self._log_incoming_action("ignored"))
        self._overlay.voicemail.connect(lambda: self._log_incoming_action("voicemail"))
        self._overlay.add_queue.connect(self._incoming_add_queue)
        self._overlay.show()
        self._overlay.raise_()
        self.sounds.start_ring()

    def _on_call_failed(self, message: str) -> None:
        self.sounds.play("error")
        QMessageBox.warning(self, "Appel", message)

    def _log_incoming_action(self, action: str) -> None:
        self.sounds.stop_ring()
        ent = match_incoming_caller(self.session, self._incoming_number)
        self.store.log_incoming_ring(
            caller_raw=self._incoming_number,
            matched_entreprise_id=ent.id if ent else None,
            user_action=action,
        )
        self._refresh_incoming_table()

    def _incoming_add_queue(self) -> None:
        ent = match_incoming_caller(self.session, self._incoming_number)
        if ent:
            exists = self.store.list_queue_items(status="todo")
            if not any(q.entreprise_id == ent.id for q in exists):
                self.session.add(
                    QueueItem(entreprise_id=ent.id, local_status="todo", priority=1)
                )
                self.session.commit()
                self._refresh_queue_table()
        self._log_incoming_action("queued")

    def _answer_incoming(self) -> None:
        self.sounds.stop_ring()
        if self._overlay:
            self._overlay.close()
        num = self._incoming_number
        ent = match_incoming_caller(self.session, num)
        cs = self.store.create_call_session(
            direction="in",
            phone_digits_val=phone_digits(num),
            entreprise_id=ent.id if ent else None,
        )
        self._active_call_session_id = cs.id
        self.store.log_incoming_ring(
            caller_raw=num,
            matched_entreprise_id=ent.id if ent else None,
            user_action="answered",
            call_session_id=cs.id,
        )
        if ent:
            tel = self.store.dial_phone_for_entreprise(ent) or num
            self._update_contact_ui(ent, tel)
        self.chat.clear()
        self.chat.add_system("Appel entrant.")
        self._start_stt()
        self._begin_call_ui(f"Entrant — {num}")
        self._start_call_worker("incoming", num)
        self.shell.set_page(2)

    def _reject_incoming(self) -> None:
        self.sounds.stop_ring()
        if self._overlay:
            self._overlay.close()
        self._log_incoming_action("rejected")

    def _refresh_incoming_table(self) -> None:
        events = self.store.list_incoming_events(50)
        self.pe.table_incoming.setRowCount(len(events))
        for r, ev in enumerate(events):
            self.pe.table_incoming.setItem(
                r, 0, QTableWidgetItem(ev.rang_at.strftime("%Y-%m-%d %H:%M"))
            )
            self.pe.table_incoming.setItem(r, 1, QTableWidgetItem(ev.caller_id_raw or ""))
            self.pe.table_incoming.setItem(r, 2, QTableWidgetItem(ev.user_action or ""))
            match = ""
            if ev.matched_entreprise_id:
                ent = self.session.get(PlEntreprise, ev.matched_entreprise_id)
                match = ent.raison_sociale if ent else ""
            self.pe.table_incoming.setItem(r, 3, QTableWidgetItem(match))

    def _refresh_journal(self) -> None:
        rows = self.store.list_call_sessions(100)
        self._refresh_kpis()

    def _flush_outbox(self) -> None:
        try:
            n = self.store.flush_sync_outbox(self.pl_client)
            QMessageBox.information(self, "Sync", f"{n} requetes envoyees.")
            self.sounds.play("notify")
        except Exception as exc:
            self.sounds.play("error")
            QMessageBox.warning(self, "Erreur", str(exc))

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        overlay = getattr(self, "_overlay", None)
        if overlay:
            overlay.setGeometry(self.rect())
        super().resizeEvent(event)

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.sounds.stop_ring()
        self._stop_listen()
        self._hangup_call()
        self.session.close()
        super().closeEvent(event)


def main() -> int:
    load_prospector_env()
    prefs = load_prefs()
    theme: ThemeMode = "light" if prefs.get("theme", "light") == "light" else "dark"
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(prospector_stylesheet(theme))

    splash = ProspectorSplashScreen()
    splash.show_centered()
    splash.set_status("Preparation de la base locale…")
    get_engine.cache_clear()
    upgrade_head()

    splash.set_status("Peripheriques audio et modem…")
    splash.set_status("Construction de l'interface…")
    win = ProspectorWindow(skip_migrate=True)
    splash.finish(win)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
