import React from "react";
import { AppLayout } from "../../components/AppLayout";

/**
 * Page gestion de la base de connaissances.
 */
const KnowledgeBasePage: React.FC = () => {
  return (
    <AppLayout
      title="Base de connaissances"
      subtitle="Questions / reponses que VocalGuard utilise pour repondre aux appelants."
    >
      <div className="vg-card">
        <div className="vg-card-label" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
          <span className="material-icons" style={{ color: "#22c55e", fontSize: "18px" }}>
            help_outline
          </span>
          Aucune entree pour le moment
        </div>
        <div style={{ fontSize: "0.9rem", color: "#9ca3af" }}>
          Tu pourras bientot ajouter ici des FAQ (horaires, tarifs, services) exploitees par la voix.
        </div>
      </div>
    </AppLayout>
  );
};

export default KnowledgeBasePage;

