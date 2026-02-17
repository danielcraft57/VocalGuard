import React from "react";
import Link from "next/link";

/**
 * Page d'onboarding / creation de compte.
 */
const SignupPage: React.FC = () => {
  return (
    <div className="vg-layout">
      <div className="vg-main">
        <main className="vg-content">
          <h1 className="vg-page-title">Creer un compte VocalGuard</h1>
          <p className="vg-page-subtitle">
            Quelques infos de base pour configurer VocalGuard pour DanielCraftFr. Le reste pourra etre affine plus tard.
          </p>
          <form style={{ maxWidth: 420, display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <label>
              <span>Nom de l'entreprise</span>
              <input
                type="text"
                placeholder="DanielCraftFr"
                style={{ width: "100%", padding: "0.5rem", borderRadius: 8, border: "1px solid #1f2937" }}
              />
            </label>
            <label>
              <span>Email</span>
              <input
                type="email"
                placeholder="contact@danielcraft.fr"
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
            <label>
              <span>Numero principal gere par VocalGuard</span>
              <input
                type="tel"
                placeholder="+33..."
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
                background: "#16a34a",
                color: "#f9fafb",
                fontWeight: 600,
                cursor: "pointer"
              }}
            >
              Lancer VocalGuard
            </button>
          </form>
          <p style={{ marginTop: "1rem", fontSize: "0.9rem", color: "#9ca3af" }}>
            Deja un compte ?{" "}
            <Link href="/login" className="vg-sidebar-link-active">
              Se connecter
            </Link>
          </p>
        </main>
      </div>
    </div>
  );
};

export default SignupPage;

