import React from "react";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

export interface AppLayoutProps {
  /** Contenu principal de la page. */
  children: React.ReactNode;
  /** Titre affiche dans la topbar. */
  title: string;
  /** Sous-titre optionnel affiche sous le titre. */
  subtitle?: string;
}

/**
 * Layout principal de l'application VocalGuard.
 *
 * Il affiche la sidebar de navigation, la topbar et le contenu
 * central passe en children.
 */
export const AppLayout: React.FC<AppLayoutProps> = ({ children, title, subtitle }) => {
  return (
    <div className="vg-layout">
      <Sidebar />
      <div className="vg-main">
        <Topbar title={title} />
        <main className="vg-content">
          <header>
            <h1 className="vg-page-title">{title}</h1>
            {subtitle ? <p className="vg-page-subtitle">{subtitle}</p> : null}
          </header>
          {children}
        </main>
      </div>
    </div>
  );
};

