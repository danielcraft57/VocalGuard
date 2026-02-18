"use client";

import React, { useState, useEffect } from "react";
import { AppLayout } from "../../components/AppLayout";
import { fetchQuotes, Quote } from "../../services/quotesApi";

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
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchQuotes()
      .then((data) => {
        if (!cancelled) {
          setQuotes(data);
          setError(null);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError("Impossible de charger les devis (verifie le backend).");
          setQuotes([]);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <AppLayout
      title="Devis"
      subtitle="Suivi des devis DanielCraftFr crees par VocalGuard."
    >
      {loading ? (
        <div className="vg-card">
          <div className="vg-card-label" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <span className="material-icons" style={{ color: "#22c55e", fontSize: "18px" }}>
              hourglass_empty
            </span>
            Chargement des devis...
          </div>
        </div>
      ) : error ? (
        <div className="vg-card">
          <div className="vg-card-label" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <span className="material-icons" style={{ color: "#ef4444", fontSize: "18px" }}>
              error_outline
            </span>
            Erreur de chargement des devis
          </div>
          <div style={{ fontSize: "0.9rem", color: "#f97373" }}>{error}</div>
        </div>
      ) : quotes.length === 0 ? (
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
            <tbody>{quotes.map(renderRow)}</tbody>
          </table>
        </div>
      )}
    </AppLayout>
  );
}
