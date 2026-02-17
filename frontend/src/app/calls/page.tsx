import React from "react";
import { AppLayout } from "../../components/AppLayout";
import { fetchCallsWithOsint, CallWithOsint } from "../../services/callsApi";

/**
 * Affiche une ligne dans le tableau d'appels avec quelques infos OSINT.
 */
function renderRow(call: CallWithOsint): React.ReactNode {
  const date = new Date(call.call_time).toLocaleString("fr-FR");
  const phone = call.phone_number ?? "Inconnu";
  const status = call.status;
  const reputation = call.osint?.reputation ?? "unknown";
  const reputationLabel =
    reputation === "high"
      ? "Bonne"
      : reputation === "low"
      ? "Mauvaise"
      : "Inconnue";

  return (
    <tr key={call.id}>
      <td style={{ padding: "0.5rem 0.75rem" }}>{date}</td>
      <td style={{ padding: "0.5rem 0.75rem" }}>{phone}</td>
      <td style={{ padding: "0.5rem 0.75rem" }}>{status}</td>
      <td style={{ padding: "0.5rem 0.75rem" }}>{reputationLabel}</td>
    </tr>
  );
}

/**
 * Page liste des appels avec integration API + OSINT de base.
 */
const CallsPage = async () => {
  let calls: CallWithOsint[] = [];
  let error: string | null = null;

  try {
    calls = await fetchCallsWithOsint();
  } catch (e) {
    error = "Impossible de contacter l'API VocalGuard (assure-toi que le backend tourne).";
  }

  return (
    <AppLayout
      title="Appels"
      subtitle="Historique des appels traites par VocalGuard, enrichis avec un premier score OSINT."
    >
      {error ? (
        <div className="vg-card">
          <div className="vg-card-label">Erreur</div>
          <div style={{ fontSize: "0.9rem", color: "#f97373" }}>{error}</div>
        </div>
      ) : calls.length === 0 ? (
        <div className="vg-card">
          <div className="vg-card-label">Aucun appel encore enregistre.</div>
          <div style={{ fontSize: "0.9rem", color: "#9ca3af", marginTop: "0.25rem" }}>
            Des que le modem et l'API seront en service, les nouveaux appels apparaitront ici avec leur reputation.
          </div>
        </div>
      ) : (
        <div className="vg-card">
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.9rem" }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Date</th>
                <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Numero</th>
                <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Statut</th>
                <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Reputation OSINT</th>
              </tr>
            </thead>
            <tbody>{calls.map(renderRow)}</tbody>
          </table>
        </div>
      )}
    </AppLayout>
  );
};

export default CallsPage;

