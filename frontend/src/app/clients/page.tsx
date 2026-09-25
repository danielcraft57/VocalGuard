"use client";

import React, { useCallback } from "react";
import { Box } from "@mui/material";
import { AppLayout } from "../../components/AppLayout";
import { fetchClients, Client } from "../../services/clientsApi";
import { useSoftCachedLoad } from "../../hooks/useSoftCachedLoad";
import { UI_CACHE_KEYS } from "../../services/uiPersist";
import { VgSoftSyncBar } from "../../components/mui/VgSoftSyncBar";
import { VgTableSkeleton } from "../../components/mui/VgListSkeleton";

function renderRow(client: Client): React.ReactNode {
  const created = new Date(client.created_at).toLocaleDateString("fr-FR");
  return (
    <tr key={client.id}>
      <td style={{ padding: "0.5rem 0.75rem" }}>{client.phone_number}</td>
      <td style={{ padding: "0.5rem 0.75rem" }}>{client.name ?? ""}</td>
      <td style={{ padding: "0.5rem 0.75rem" }}>{client.email ?? ""}</td>
      <td style={{ padding: "0.5rem 0.75rem" }}>{created}</td>
    </tr>
  );
}

export default function ClientsPage() {
  const fetcher = useCallback(
    (signal: AbortSignal) => fetchClients(undefined, signal),
    []
  );
  const {
    data: clients,
    loading,
    syncing,
    error
  } = useSoftCachedLoad<Client[]>({
    cacheKey: UI_CACHE_KEYS.clients,
    fetcher,
    hasData: (d) => Array.isArray(d)
  });

  const rows = clients ?? [];

  return (
    <AppLayout title="Clients" subtitle="Contacts rattachés aux entreprises (personnes, emails, téléphone).">
      {syncing ? (
        <Box sx={{ display: "flex", justifyContent: "flex-end", mb: 1 }}>
          <VgSoftSyncBar />
        </Box>
      ) : null}
      {loading && !clients ? (
        <div className="vg-card">
          <VgTableSkeleton rows={5} />
        </div>
      ) : error && !clients ? (
        <div className="vg-card">
          <div className="vg-card-label" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <span className="material-icons" style={{ color: "#ef4444", fontSize: "18px" }}>
              error_outline
            </span>
            Erreur de chargement des clients
          </div>
          <div style={{ fontSize: "0.9rem", color: "#f97373" }}>{error}</div>
        </div>
      ) : rows.length === 0 ? (
        <div className="vg-card">
          <div className="vg-card-label" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <span className="material-icons" style={{ color: "#9ca3af", fontSize: "18px" }}>
              groups
            </span>
            Aucun client encore enregistré
          </div>
          <div style={{ fontSize: "0.9rem", color: "#9ca3af" }}>
            Dès qu’un RDV, un devis, ou un appel crée un contact, tu le verras ici.
          </div>
        </div>
      ) : (
        <div className="vg-card">
          <table className="vg-table">
            <thead>
              <tr>
                <th style={{ padding: "0.5rem 0.75rem", textAlign: "left" }}>Téléphone</th>
                <th style={{ padding: "0.5rem 0.75rem", textAlign: "left" }}>Nom</th>
                <th style={{ padding: "0.5rem 0.75rem", textAlign: "left" }}>Email</th>
                <th style={{ padding: "0.5rem 0.75rem", textAlign: "left" }}>Créé</th>
              </tr>
            </thead>
            <tbody>{rows.map(renderRow)}</tbody>
          </table>
        </div>
      )}
    </AppLayout>
  );
}
