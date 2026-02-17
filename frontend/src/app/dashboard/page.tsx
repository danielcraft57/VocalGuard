import React from "react";
import { AppLayout } from "../../components/AppLayout";
import { DashboardCharts } from "../../components/DashboardCharts";

/**
 * Dashboard principal: vue synthese rapide.
 * Pour l'instant, les stats sont simulées côté frontend.
 */
const DashboardPage: React.FC = () => {
  return (
    <AppLayout
      title="Dashboard"
      subtitle="Vue d'ensemble des appels, RDV et devis VocalGuard."
    >
      <div className="vg-card-grid">
        <div className="vg-card">
          <div className="vg-card-label" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <span className="material-icons" style={{ fontSize: "18px", color: "#22c55e" }}>
              call
            </span>
            Appels aujourd'hui
          </div>
          <div className="vg-card-value">28</div>
        </div>
        <div className="vg-card">
          <div className="vg-card-label" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <span className="material-icons" style={{ fontSize: "18px", color: "#0ea5e9" }}>
              event
            </span>
            RDV crees
          </div>
          <div className="vg-card-value">7</div>
        </div>
        <div className="vg-card">
          <div className="vg-card-label" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <span className="material-icons" style={{ fontSize: "18px", color: "#22c55e" }}>
              request_quote
            </span>
            Devis envoyes
          </div>
          <div className="vg-card-value">5</div>
        </div>
        <div className="vg-card">
          <div className="vg-card-label" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <span className="material-icons" style={{ fontSize: "18px", color: "#ef4444" }}>
              report_gmailerrorred
            </span>
            Appels suspects (OSINT)
          </div>
          <div className="vg-card-value">4</div>
        </div>
      </div>

      <DashboardCharts />
    </AppLayout>
  );
};

export default DashboardPage;

