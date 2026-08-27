"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  fetchSettings,
  fetchTelephonyStatus,
  setIncomingLineMode,
  type IncomingLineMode,
  type TelephonyStatus
} from "../services/settingsApi";

export interface TopbarProps {
  /** Titre de la page courante. */
  title: string;
  /** Callback pour le bouton menu (mobile). */
  onMenuClick?: () => void;
}

/**
 * Bandeau superieur : menu, switch mode ligne (Material), titre, pastille modem.
 */
export const Topbar: React.FC<TopbarProps> = ({ title, onMenuClick }) => {
  const [mode, setMode] = useState<IncomingLineMode>("voicemail");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tel, setTel] = useState<TelephonyStatus | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchSettings()
      .then((s) => {
        if (!cancelled) setMode(s.incoming_line_mode || "voicemail");
      })
      .catch(() => {
        /* ignore: UI garde le defaut */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const tick = () => {
      fetchTelephonyStatus()
        .then((s) => {
          if (!cancelled) setTel(s);
        })
        .catch(() => {
          if (!cancelled) {
            setTel({
              status: "unreachable",
              modem_initialized: false,
              incoming_line_mode: mode,
              in_call: false,
              relay_failures: 0,
              daemon_reachable: false
            });
          }
        });
    };
    tick();
    const id = window.setInterval(tick, 8000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [mode]);

  const switchMode = useCallback(async (next: IncomingLineMode) => {
    if (busy || next === mode) return;
    setBusy(true);
    setError(null);
    try {
      const s = await setIncomingLineMode(next);
      setMode(s.incoming_line_mode);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Impossible de changer le mode");
    } finally {
      setBusy(false);
    }
  }, [busy, mode]);

  const modeLabel =
    mode === "voicemail" ? "Répondeur (coupe sonnerie)" : "Téléphone (fixe seul)";

  const modemOk = Boolean(tel?.modem_initialized);
  const modemLabel = !tel
    ? "Modem…"
    : tel.daemon_reachable === false
      ? "Daemon HS"
      : modemOk
        ? tel.in_call
          ? "En appel"
          : "Modem OK"
        : "Modem KO";
  const modemTitle = tel
    ? [
        `status=${tel.status}`,
        tel.modem_port ? `port=${tel.modem_port}` : null,
        tel.firmware_ati3 ? `fw=${tel.firmware_ati3}` : null,
        tel.last_cid_raw ? `cid=${tel.last_cid_raw}` : null,
        tel.last_error ? `err=${tel.last_error}` : null
      ]
        .filter(Boolean)
        .join(" | ")
    : "Chargement état téléphonie";

  return (
    <header className="vg-topbar">
      <div className="vg-topbar-left">
        {onMenuClick ? (
          <button
            type="button"
            className="vg-topbar-menu-button"
            onClick={onMenuClick}
            aria-label="Ouvrir le menu"
          >
            <span className="material-icons">menu</span>
          </button>
        ) : null}

        <div
          className={`vg-line-mode ${busy ? "vg-line-mode--busy" : ""}`}
          role="group"
          aria-label="Mode prise d'appel"
          title={modeLabel}
        >
          <button
            type="button"
            className={`vg-line-mode-btn ${mode === "voicemail" ? "vg-line-mode-btn--active" : ""}`}
            disabled={busy}
            aria-pressed={mode === "voicemail"}
            onClick={() => void switchMode("voicemail")}
          >
            <span className="material-icons" aria-hidden>
              voicemail
            </span>
            <span className="vg-line-mode-text">Répondeur</span>
          </button>
          <button
            type="button"
            className={`vg-line-mode-btn ${mode === "phone" ? "vg-line-mode-btn--active" : ""}`}
            disabled={busy}
            aria-pressed={mode === "phone"}
            onClick={() => void switchMode("phone")}
          >
            <span className="material-icons" aria-hidden>
              phone_in_talk
            </span>
            <span className="vg-line-mode-text">Téléphone</span>
          </button>
        </div>

        <div className="vg-topbar-title">{title}</div>
      </div>

      <div className="vg-topbar-right">
        {error ? <span className="vg-topbar-mode-error">{error}</span> : null}
        <div
          className={`vg-modem-pill ${
            !tel
              ? "vg-modem-pill--pending"
              : modemOk
                ? "vg-modem-pill--ok"
                : "vg-modem-pill--ko"
          }`}
          title={modemTitle}
          aria-label={modemLabel}
        >
          <span
            className={`vg-modem-pill-dot ${modemOk ? "vg-modem-pill-dot--ok" : "vg-modem-pill-dot--ko"}`}
            aria-hidden
          />
          <span className="vg-modem-pill-text">{modemLabel}</span>
        </div>
        <div className="vg-topbar-status" title={modeLabel}>
          <span className="material-icons vg-topbar-status-icon">
            {mode === "voicemail" ? "ring_volume" : "phone"}
          </span>
          <span className="vg-topbar-status-text">
            {mode === "voicemail" ? "Répondeur actif" : "Fixe actif"}
          </span>
        </div>
      </div>
    </header>
  );
};
