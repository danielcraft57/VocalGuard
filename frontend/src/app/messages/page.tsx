"use client";

import React, { useCallback, useEffect, useState } from "react";
import { AppLayout } from "../../components/AppLayout";
import {
  deleteVoicemail,
  fetchVoicemails,
  markVoicemailRead,
  voicemailAudioUrl,
  Voicemail,
} from "../../services/voicemailsApi";

/**
 * Page Messages : boite vocale apres le bip (style callattendant).
 */
export default function MessagesPage() {
  const [items, setItems] = useState<Voicemail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [unreadOnly, setUnreadOnly] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await fetchVoicemails({
        limit: 100,
        is_read: unreadOnly ? false : undefined,
      });
      setItems(rows);
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
      } catch {
        // lecture audio prioritaire
      }
    }
  };

  const onDelete = async (id: number) => {
    if (!window.confirm("Supprimer ce message ?")) return;
    try {
      await deleteVoicemail(id);
      setItems((prev) => prev.filter((x) => x.id !== id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Suppression impossible");
    }
  };

  return (
    <AppLayout
      title="Messages"
      subtitle="Messages laisses apres le bip (sans le message d accueil)."
    >
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
                  {new Date(vm.created_at).toLocaleString("fr-FR")}
                  {vm.duration != null ? ` · ${vm.duration}s` : ""}
                  {vm.call_id != null ? ` · appel #${vm.call_id}` : ""}
                </div>
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
