import React from "react";
import Link from "next/link";

/**
 * Page de connexion simple pour VocalGuard.
 */
const LoginPage: React.FC = () => {
  return (
    <div className="vg-layout">
      <div className="vg-main">
        <main className="vg-content">
          <h1 className="vg-page-title">Connexion</h1>
          <p className="vg-page-subtitle">Connecte-toi pour acceder a ton tableau de bord VocalGuard.</p>
          <form style={{ maxWidth: 360, display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <label>
              <span>Email</span>
              <input
                type="email"
                placeholder="toi@danielcraft.fr"
                style={{ width: "100%", padding: "0.5rem", borderRadius: 8, border: "1px solid #1f2937" }}
              />
            </label>
            <label>
              <span>Mot de passe</span>
              <input
                type="password"
                placeholder="••••••••"
                style={{ width: "100%", padding: "0.5rem", borderRadius: 8, border: "1px solid #1f2937" }}
              />
            </label>
            <button
              type="submit"
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
              Se connecter
            </button>
          </form>
          <p style={{ marginTop: "1rem", fontSize: "0.9rem", color: "#9ca3af" }}>
            Pas encore de compte ?{" "}
            <Link href="/signup" className="vg-sidebar-link-active">
              Creer un compte
            </Link>
          </p>
        </main>
      </div>
    </div>
  );
};

export default LoginPage;

