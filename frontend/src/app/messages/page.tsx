"use client";

import React, { useCallback, useEffect, useState } from "react";
import { AppLayout } from "../../components/AppLayout";
import { fetchDashboardStats } from "../../services/dashboardStatsApi";
import {
  deleteVoicemail,
  fetchVoicemails,
  markVoicemailRead,
  voicemailAudioUrl,
  Voicemail,
} from "../../services/voicemailsApi";
import { formatApiDateTime } from "../../utils/dateTime";

/**
 * Page Messages : boite vocale apres le bip (style callattendant).
 */
export default function MessagesPage() {
  const [items, setItems] = useState<Voicemail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [stats, setStats] = useState<{
    today: number;
    unread: number;
    total: number;
  } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [rows, dash] = await Promise.all([
        fetchVoicemails({
          limit: 100,
          is_read: unreadOnly ? false : undefined,
        }),
        fetchDashboardStats().catch(() => null),
      ]);
      setItems(rows);
      if (dash) {
        setStats({
          today: dash.voicemails_today ?? 0,
          unread: dash.voicemails_unread ?? 0,
          total: dash.voicemails_total ?? 0,
        });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur de chargement");
    } finally {
      setLoading(false);
    }
  }, [unreadOnly]);

  useEffect(() => {
    load();
  }, [load]);

  const onPlay = async (vm: Voicemail) => {
    if (!vm.is_read) {
      try {
        await markVoicemailRead(vm.id);
        setItems((prev) =>
          prev.map((x) => (x.id === vm.id ? { ...x, is_read: true } : x))
        );
        setStats((s) =>
          s ? { ...s, unread: Math.max(0, s.unread - 1) } : s
        );
      } catch {
        // lecture audio prioritaire
      }
    }
  };

  const onDelete = async (id: number) => {
    if (!window.confirm("Supprimer ce message ?")) return;
    try {
      const wasUnread = items.find((x) => x.id === id)?.is_read === false;
      await deleteVoicemail(id);
      setItems((prev) => prev.filter((x) => x.id !== id));
      setStats((s) =>
        s
          ? {
              today: s.today,
              total: Math.max(0, s.total - 1),
              unread: wasUnread ? Math.max(0, s.unread - 1) : s.unread,
            }
          : s
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Suppression impossible");
    }
  };

  return (
    <AppLayout
      title="Messages"
      subtitle="Messages laisses apres le bip. Transcription auto via Vosk (STT)."
    >
      {stats ? (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
            gap: "0.75rem",
            marginBottom: "1.25rem",
          }}
        >
          <div className="vg-card">
            <div className="vg-card-label">Non lus</div>
            <div className="vg-card-value">{stats.unread}</div>
          </div>
          <div className="vg-card">
            <div className="vg-card-label">Aujourd hui</div>
            <div className="vg-card-value">{stats.today}</div>
          </div>
          <div className="vg-card">
            <div className="vg-card-label">Total</div>
            <div className="vg-card-value">{stats.total}</div>
          </div>
        </div>
      ) : null}

      <div style={{ display: "flex", gap: "1rem", alignItems: "center", marginBottom: "1rem" }}>
        <label style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <input
            type="checkbox"
            checked={unreadOnly}
            onChange={(e) => setUnreadOnly(e.target.checked)}
          />
          Non lus seulement
        </label>
        <button type="button" className="vg-btn" onClick={() => load()}>
          Rafraichir
        </button>
      </div>

      {loading ? <p>Chargement…</p> : null}
      {error ? <p className="vg-error">{error}</p> : null}

      {!loading && items.length === 0 ? (
        <p>Aucun message pour le moment. Appelle le repondeur pour en laisser un.</p>
      ) : null}

      <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {items.map((vm) => (
          <li
            key={vm.id}
            style={{
              borderBottom: "1px solid var(--vg-border, #333)",
              padding: "0.85rem 0",
              opacity: vm.is_read ? 0.85 : 1,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap" }}>
              <div>
                <strong>{vm.phone_number || "Numero inconnu"}</strong>
                {vm.caller_name ? ` — ${vm.caller_name}` : ""}
                {!vm.is_read ? (
                  <span style={{ marginLeft: "0.5rem", fontSize: "0.85rem" }}>nouveau</span>
                ) : null}
                <div style={{ fontSize: "0.9rem", opacity: 0.8 }}>
                  {formatApiDateTime(vm.created_at)}
                  {vm.duration != null ? ` · ${vm.duration}s` : ""}
                  {vm.call_id != null ? ` · appel #${vm.call_id}` : ""}
                </div>
                {vm.transcription ? (
                  <p style={{ margin: "0.4rem 0 0", fontStyle: "italic" }}>
                    « {vm.transcription} »
                  </p>
                ) : (
                  <p style={{ margin: "0.4rem 0 0", opacity: 0.55, fontSize: "0.9rem" }}>
                    Transcription en cours ou indisponible…
                  </p>
                )}
              </div>
              <button type="button" className="vg-btn" onClick={() => onDelete(vm.id)}>
                Supprimer
              </button>
            </div>
            <audio
              controls
              src={voicemailAudioUrl(vm.id)}
              style={{ width: "100%", marginTop: "0.5rem" }}
              onPlay={() => onPlay(vm)}
            />
          </li>
        ))}
      </ul>
    </AppLayout>
  );
}
