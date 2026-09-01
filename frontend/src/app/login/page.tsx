"use client";

import React, { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { fetchUiSession, loginUi } from "../../services/authUiApi";

/**
 * Formulaire de connexion UI (mot de passe partage VocalGuard).
 */
function LoginForm() {
  const searchParams = useSearchParams();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetchUiSession()
      .then((session) => {
        if (!session.ui_password_enabled || session.authenticated) {
          const next = searchParams.get("next") || "/dashboard";
          // Navigation complete: le soft-nav Next casse avec l export statique derriere nginx
          window.location.replace(next);
        }
      })
      .catch(() => null);
  }, [searchParams]);

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await loginUi(password);
      const next = searchParams.get("next") || "/dashboard";
      window.location.replace(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Connexion impossible.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="vg-login-page">
      <div className="vg-login-card">
        <span className="material-icons vg-login-icon">lock</span>
        <h1 className="vg-login-title">VocalGuard</h1>
        <p className="vg-login-subtitle">Mot de passe requis pour acceder a l interface.</p>
        <form className="vg-login-form" onSubmit={onSubmit}>
          <label className="vg-login-label" htmlFor="vg-ui-password">
            Mot de passe
          </label>
          <input
            id="vg-ui-password"
            className="vg-login-input"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={busy}
            required
          />
          {error ? <p className="vg-login-error">{error}</p> : null}
          <button className="vg-login-button" type="submit" disabled={busy || !password.trim()}>
            {busy ? "Connexion..." : "Se connecter"}
          </button>
        </form>
      </div>
    </div>
  );
}

/**
 * Page login UI web.
 */
export default function LoginPage() {
  return (
    <Suspense fallback={<div className="vg-login-page"><p className="vg-login-subtitle">Chargement...</p></div>}>
      <LoginForm />
    </Suspense>
  );
}
