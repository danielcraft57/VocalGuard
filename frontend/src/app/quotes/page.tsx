"use client";

import React, { useCallback } from "react";
import { Box } from "@mui/material";
import { AppLayout } from "../../components/AppLayout";
import { fetchQuotes, Quote } from "../../services/quotesApi";
import { useSoftCachedLoad } from "../../hooks/useSoftCachedLoad";
import { UI_CACHE_KEYS } from "../../services/uiPersist";
import { VgSoftSyncBar } from "../../components/mui/VgSoftSyncBar";
import { VgTableSkeleton } from "../../components/mui/VgListSkeleton";

function renderRow(quote: Quote): React.ReactNode {
  const created = new Date(quote.created_at).toLocaleString("fr-FR");
  const totalTtc = (quote.total_ttc / 100).toFixed(2);
  return (
    <tr key={quote.id}>
      <td style={{ padding: "0.5rem 0.75rem" }}>{created}</td>
      <td style={{ padding: "0.5rem 0.75rem" }}>{quote.title}</td>
      <td style={{ padding: "0.5rem 0.75rem" }}>{quote.phone_number ?? ""}</td>
      <td style={{ padding: "0.5rem 0.75rem" }}>{totalTtc} €</td>
      <td style={{ padding: "0.5rem 0.75rem" }}>
        <span className="vg-badge vg-badge-success">
          <span className="material-icons" style={{ fontSize: "14px", marginRight: "0.25rem" }}>
            request_quote
          </span>
          {quote.status}
        </span>
      </td>
    </tr>
  );
}

/**
 * Page devis : chargement cote client pour les vraies donnees.
 */
export default function QuotesPage() {
  const fetcher = useCallback(
    (signal: AbortSignal) => fetchQuotes(undefined, signal),
    []
  );
  const {
    data: quotes,
    loading,
    syncing,
    error
  } = useSoftCachedLoad<Quote[]>({
    cacheKey: UI_CACHE_KEYS.quotes,
    fetcher,
    hasData: (d) => Array.isArray(d)
  });

  const rows = quotes ?? [];

  return (
    <AppLayout
      title="Devis"
      subtitle="Suivi des devis DanielCraftFr crees par VocalGuard."
    >
      {syncing ? (
        <Box sx={{ display: "flex", justifyContent: "flex-end", mb: 1 }}>
          <VgSoftSyncBar />
        </Box>
      ) : null}
      {loading && !quotes ? (
        <div className="vg-card">
          <VgTableSkeleton rows={5} />
        </div>
      ) : error && !quotes ? (
        <div className="vg-card">
          <div className="vg-card-label" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <span className="material-icons" style={{ color: "#ef4444", fontSize: "18px" }}>
              error_outline
            </span>
            Erreur de chargement des devis
          </div>
          <div style={{ fontSize: "0.9rem", color: "#f97373" }}>{error}</div>
        </div>
      ) : rows.length === 0 ? (
        <div className="vg-card">
          <div className="vg-card-label" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <span className="material-icons" style={{ color: "#9ca3af", fontSize: "18px" }}>
              description
            </span>
            Aucun devis pour le moment
          </div>
          <div style={{ fontSize: "0.9rem", color: "#9ca3af" }}>
            Quand tu commenceras a generer des devis depuis les appels, ils apparaitront ici.
          </div>
        </div>
      ) : (
        <div className="vg-card">
          <table className="vg-table">
            <thead>
              <tr>
                <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Date</th>
                <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Titre</th>
                <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Numero</th>
                <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Total TTC</th>
                <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Statut</th>
              </tr>
            </thead>
            <tbody>{rows.map(renderRow)}</tbody>
          </table>
        </div>
      )}
    </AppLayout>
  );
}
