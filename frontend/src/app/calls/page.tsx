import React from "react";
import { AppLayout } from "../../components/AppLayout";
import { fetchCallsWithOsint, CallWithOsint } from "../../services/callsApi";

function formatStatus(status: string): { label: string; className: string } {
  const normalized = status.toLowerCase();
  if (normalized === "answered" || normalized === "completed") {
    return { label: "Répondu", className: "vg-badge vg-badge-success" };
  }
  if (normalized === "missed") {
    return { label: "Manqué", className: "vg-badge vg-badge-warn" };
  }
  if (normalized === "blocked") {
    return { label: "Bloqué", className: "vg-badge vg-badge-danger" };
  }
  return { label: status, className: "vg-badge" };
}

function formatReputation(osint?: CallWithOsint["osint"]): React.ReactNode {
  if (!osint) {
    return (
      <span className="vg-chip">
        <span className="vg-chip-dot vg-chip-dot--unknown" />
        <span>Inconnue</span>
      </span>
    );
  }

  const rep = (osint.reputation || "unknown").toLowerCase();
  if (rep === "high") {
    return (
      <span className="vg-chip">
        <span className="vg-chip-dot vg-chip-dot--good" />
        <span>Bonne</span>
      </span>
    );
  }
  if (rep === "low" || osint.is_spam || osint.is_scam || osint.is_telemarketer) {
    return (
      <span className="vg-chip">
        <span className="vg-chip-dot vg-chip-dot--bad" />
        <span>Risque</span>
      </span>
    );
  }
  return (
    <span className="vg-chip">
      <span className="vg-chip-dot vg-chip-dot--unknown" />
      <span>Inconnue</span>
    </span>
  );
}

/**
 * Affiche une ligne dans le tableau d'appels avec quelques infos OSINT.
 */
function renderRow(call: CallWithOsint): React.ReactNode {
  const date = new Date(call.call_time).toLocaleString("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
  const phone = call.phone_number ?? "Inconnu";
  const { label: statusLabel, className: statusClass } = formatStatus(call.status);

  return (
    <tr
      key={call.id}
      style={{
        transition: "background-color 150ms ease-out"
      }}
      className="vg-table-row"
    >
      <td style={{ padding: "0.5rem 0.75rem" }}>{date}</td>
      <td style={{ padding: "0.5rem 0.75rem", display: "flex", alignItems: "center", gap: "0.35rem" }}>
        <span className="material-icons" style={{ fontSize: "16px", color: "#22c55e" }}>
          phone_in_talk
        </span>
        <span>{phone}</span>
      </td>
      <td style={{ padding: "0.5rem 0.75rem" }}>
        <span className={statusClass}>{statusLabel}</span>
      </td>
      <td style={{ padding: "0.5rem 0.75rem" }}>{formatReputation(call.osint)}</td>
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
          <div className="vg-card-label" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <span className="material-icons" style={{ color: "#ef4444", fontSize: "18px" }}>
              error_outline
            </span>
            Erreur de chargement des appels
          </div>
          <div style={{ fontSize: "0.9rem", color: "#ef4444" }}>{error}</div>
        </div>
      ) : calls.length === 0 ? (
        <div className="vg-card">
          <div className="vg-card-label" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <span className="material-icons" style={{ color: "#9ca3af", fontSize: "18px" }}>
              contact_phone
            </span>
            Aucun appel encore enregistre
          </div>
          <div style={{ fontSize: "0.9rem", color: "#6b7280", marginTop: "0.25rem" }}>
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

