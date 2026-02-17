import React from "react";
import { AppLayout } from "../../components/AppLayout";
import { fetchAppointments, Appointment } from "../../services/appointmentsApi";

function renderRow(appointment: Appointment): React.ReactNode {
  const start = new Date(appointment.start_time).toLocaleString("fr-FR");
  const end = new Date(appointment.end_time).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  return (
    <tr key={appointment.id}>
      <td style={{ padding: "0.5rem 0.75rem" }}>{start}</td>
      <td style={{ padding: "0.5rem 0.75rem" }}>{end}</td>
      <td style={{ padding: "0.5rem 0.75rem" }}>{appointment.title}</td>
      <td style={{ padding: "0.5rem 0.75rem" }}>{appointment.phone_number ?? ""}</td>
      <td style={{ padding: "0.5rem 0.75rem" }}>
        <span className="vg-badge vg-badge-success">
          <span className="material-icons" style={{ fontSize: "14px", marginRight: "0.25rem" }}>
            event_available
          </span>
          {appointment.status}
        </span>
      </td>
    </tr>
  );
}

/**
 * Page agenda / rendez-vous.
 */
const AppointmentsPage = async () => {
  let appointments: Appointment[] = [];
  let error: string | null = null;

  try {
    appointments = await fetchAppointments();
  } catch {
    error = "Impossible de charger les rendez-vous (verifie le backend).";
  }

  return (
    <AppLayout
      title="Rendez-vous"
      subtitle="Vue agenda des interventions et RDV DanielCraftFr."
    >
      {error ? (
        <div className="vg-card">
          <div className="vg-card-label" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <span className="material-icons" style={{ color: "#ef4444", fontSize: "18px" }}>
              error_outline
            </span>
            Erreur de chargement des rendez-vous
          </div>
          <div style={{ fontSize: "0.9rem", color: "#f97373" }}>{error}</div>
        </div>
      ) : appointments.length === 0 ? (
        <div className="vg-card">
          <div className="vg-card-label" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <span className="material-icons" style={{ color: "#9ca3af", fontSize: "18px" }}>
              event_busy
            </span>
            Aucun rendez-vous planifie
          </div>
          <div style={{ fontSize: "0.9rem", color: "#9ca3af" }}>
            Quand le moteur de prise de RDV sera branche, tu verras ici les prochains passages.
          </div>
        </div>
      ) : (
        <div className="vg-card">
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.9rem" }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Debut</th>
                <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Fin</th>
                <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Titre</th>
                <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Numero</th>
                <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Statut</th>
              </tr>
            </thead>
            <tbody>{appointments.map(renderRow)}</tbody>
          </table>
        </div>
      )}
    </AppLayout>
  );
};

export default AppointmentsPage;

