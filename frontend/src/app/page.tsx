import React from "react";
import Link from "next/link";

/**
 * Page racine: simple porte d'entree vers le dashboard
 * et la connexion.
 */
const HomePage: React.FC = () => {
  return (
    <div className="vg-layout">
      <div className="vg-main">
        <main className="vg-content">
          <h1 className="vg-page-title">Bienvenue sur VocalGuard</h1>
          <p className="vg-page-subtitle">
            Assistant telephonique intelligent pour DanielCraftFr. Connecte-toi pour acceder au tableau de bord.
          </p>
          <div style={{ display: "flex", gap: "1rem" }}>
            <Link href="/login" className="vg-sidebar-link vg-sidebar-link-active">
              Connexion
            </Link>
            <Link href="/signup" className="vg-sidebar-link">
              Creer un compte
            </Link>
          </div>
        </main>
      </div>
    </div>
  );
};

export default HomePage;

