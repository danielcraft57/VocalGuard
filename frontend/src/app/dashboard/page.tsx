"use client";

import React, { useState, useEffect } from "react";
import { AppLayout } from "../../components/AppLayout";
import { DashboardCharts } from "../../components/DashboardCharts";
import { fetchDashboardStats, DashboardStats } from "../../services/dashboardStatsApi";

/**
 * Dashboard : stats chargees cote client pour afficher les vraies donnees.
 */
export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchDashboardStats()
      .then((data) => {
        if (!cancelled) {
          setStats(data);
          setError(null);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError("Impossible de charger les stats (verifie le backend).");
          setStats(null);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const cards = [
    {
      label: "Appels aujourd'hui",
      value: stats?.calls_today ?? "-",
      icon: "call",
      color: "#22c55e",
    },
    {
      label: "Messages non lus",
      value: stats?.voicemails_unread ?? "-",
      icon: "voicemail",
      color: "#f59e0b",
    },
    {
      label: "Messages aujourd'hui",
      value: stats?.voicemails_today ?? "-",
      icon: "mic",
      color: "#0ea5e9",
    },
    {
      label: "Appels suspects (OSINT)",
      value: stats?.suspects_count ?? "-",
      icon: "report_gmailerrorred",
      color: "#ef4444",
    },
  ];

  return (
    <AppLayout
      title="Dashboard"
      subtitle="Vue d'ensemble des appels, RDV et devis VocalGuard."
    >
      {error ? (
        <div className="vg-card">
          <div className="vg-card-label" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <span className="material-icons" style={{ color: "#ef4444", fontSize: "18px" }}>
              error_outline
            </span>
            Erreur de chargement des stats
          </div>
          <div style={{ fontSize: "0.9rem", color: "#ef4444" }}>{error}</div>
        </div>
      ) : (
        <div className="vg-card-grid">
          {cards.map((card) => (
            <div key={card.label} className="vg-card">
              <div className="vg-card-label" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                <span className="material-icons" style={{ fontSize: "18px", color: card.color }}>
                  {card.icon}
                </span>
                {card.label}
              </div>
              <div className="vg-card-value">
                {loading ? (
                  <span className="material-icons" style={{ fontSize: "1.2rem", verticalAlign: "middle" }}>
                    hourglass_empty
                  </span>
                ) : (
                  card.value
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <DashboardCharts stats={stats} loading={loading} />
    </AppLayout>
  );
}
