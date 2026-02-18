"use client";

import React, { useState, useEffect } from "react";
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
 * Page agenda / rendez-vous : chargement cote client pour les vraies donnees.
 */
export default function AppointmentsPage() {
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchAppointments()
      .then((data) => {
        if (!cancelled) {
          setAppointments(data);
          setError(null);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError("Impossible de charger les rendez-vous (verifie le backend).");
          setAppointments([]);
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
      title="Rendez-vous"
      subtitle="Vue agenda des interventions et RDV DanielCraftFr."
    >
      {loading ? (
        <div className="vg-card">
          <div className="vg-card-label" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <span className="material-icons" style={{ color: "#22c55e", fontSize: "18px" }}>
              hourglass_empty
            </span>
            Chargement des rendez-vous...
          </div>
        </div>
      ) : error ? (
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
          <table className="vg-table">
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
}
