import React from "react";
import { AppLayout } from "../../components/AppLayout";

/**
 * Page simulateur d'appel pour tester les flux de conversation
 * sans passer par la vraie ligne telephonique.
 */
const SimulatorPage: React.FC = () => {
  return (
    <AppLayout
      title="Simulateur d'appel"
      subtitle="Teste les reponses de VocalGuard avec des phrases saisies au clavier."
    >
      <div className="vg-card">
        <div className="vg-card-label" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
          <span className="material-icons" style={{ color: "#22c55e", fontSize: "18px" }}>
            mic
          </span>
          Simulation rapide
        </div>
        <p style={{ fontSize: "0.9rem", color: "#9ca3af", marginBottom: "0.75rem" }}>
          Plus tard, cette page pourra appeler directement l'API pour simuler un appel et afficher la reponse.
        </p>
        <textarea
          placeholder="Tape ici ce que dirait l'appelant..."
          style={{
            width: "100%",
            minHeight: 80,
            padding: "0.5rem",
            borderRadius: 8,
            border: "1px solid #1f2937",
            background: "#020617",
            color: "#e5e7eb"
          }}
        />
        <button
          type="button"
          style={{
            marginTop: "0.5rem",
            padding: "0.6rem 1rem",
            borderRadius: 999,
            border: "none",
            background: "#2563eb",
            color: "#f9fafb",
            fontWeight: 600,
            cursor: "pointer"
          }}
        >
          <span className="material-icons" style={{ fontSize: "16px", marginRight: "0.25rem", verticalAlign: "middle" }}>
            play_arrow
          </span>
          Simuler la reponse
        </button>
      </div>
    </AppLayout>
  );
};

export default SimulatorPage;

