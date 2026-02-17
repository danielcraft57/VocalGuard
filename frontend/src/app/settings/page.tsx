import React from "react";
import { AppLayout } from "../../components/AppLayout";

/**
 * Page des parametres VocalGuard.
 */
const SettingsPage: React.FC = () => {
  return (
    <AppLayout
      title="Parametres"
      subtitle="Horaires, messages vocaux et configuration generale."
    >
      <div className="vg-card">
        <div className="vg-card-label" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
          <span className="material-icons" style={{ color: "#22c55e", fontSize: "18px" }}>
            settings
          </span>
          Configuration
        </div>
        <div style={{ fontSize: "0.9rem", color: "#9ca3af" }}>
          Un appel a l'endpoint /api/v1/settings fournira les valeurs actuelles
          (horaires, modems, etc.) a afficher et modifier ici.
        </div>
      </div>
    </AppLayout>
  );
};

export default SettingsPage;

