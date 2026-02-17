import React from "react";
import { AppLayout } from "../../components/AppLayout";

/**
 * Dashboard principal: vue synthese rapide.
 */
const DashboardPage: React.FC = () => {
  return (
    <AppLayout
      title="Dashboard"
      subtitle="Vue d'ensemble des appels, RDV et devis VocalGuard."
    >
      <div className="vg-card-grid">
        <div className="vg-card">
          <div className="vg-card-label">Appels aujourd'hui</div>
          <div className="vg-card-value">0</div>
        </div>
        <div className="vg-card">
          <div className="vg-card-label">RDV crees</div>
          <div className="vg-card-value">0</div>
        </div>
        <div className="vg-card">
          <div className="vg-card-label">Devis envoyes</div>
          <div className="vg-card-value">0</div>
        </div>
        <div className="vg-card">
          <div className="vg-card-label">Appels suspects (OSINT)</div>
          <div className="vg-card-value">0</div>
        </div>
      </div>
    </AppLayout>
  );
};

export default DashboardPage;

