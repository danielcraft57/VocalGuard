import React from "react";
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
 * Page de gestion des devis.
 */
const QuotesPage = async () => {
  let quotes: Quote[] = [];
  let error: string | null = null;

  try {
    quotes = await fetchQuotes();
  } catch {
    error = "Impossible de charger les devis (verifie le backend).";
  }

  return (
    <AppLayout
      title="Devis"
      subtitle="Suivi des devis DanielCraftFr crees par VocalGuard."
    >
      {error ? (
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
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.9rem" }}>
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
};

export default QuotesPage;

