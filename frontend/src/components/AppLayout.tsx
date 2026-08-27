"use client";

import React, { Suspense, useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { PageLoader } from "./PageLoader";

export interface AppLayoutProps {
  /** Contenu principal de la page. */
  children: React.ReactNode;
  /** Titre affiche dans la topbar. */
  title: string;
  /** Sous-titre optionnel affiche sous le titre. */
  subtitle?: string;
  /** Permet de masquer le header de page (titre + sous-titre). */
  hidePageHeader?: boolean;
}

/**
 * Layout principal de l'application VocalGuard.
 * Menu sticky + loader de transition sur toutes les pages.
 */
export const AppLayout: React.FC<AppLayoutProps> = ({
  children,
  title,
  subtitle,
  hidePageHeader = false
}) => {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const pathname = usePathname();
  const [routeLoading, setRouteLoading] = useState(false);
  const isFirstPath = useRef(true);

  useEffect(() => {
    if (isFirstPath.current) {
      isFirstPath.current = false;
      return;
    }
    setRouteLoading(true);
    const t = window.setTimeout(() => setRouteLoading(false), 320);
    return () => window.clearTimeout(t);
  }, [pathname]);

  const handleToggleSidebar = () => {
    setSidebarOpen((prev) => !prev);
  };

  const handleCloseSidebar = () => {
    setSidebarOpen(false);
  };

  return (
    <div className="vg-layout">
      <Sidebar isOpen={sidebarOpen} onNavigate={handleCloseSidebar} />
      <div className="vg-main">
        <Topbar title={title} onMenuClick={handleToggleSidebar} />
        <main className="vg-content">
          {!hidePageHeader ? (
            <header className="vg-page-header">
              <h1 className="vg-page-title">{title}</h1>
              {subtitle ? <p className="vg-page-subtitle">{subtitle}</p> : null}
            </header>
          ) : null}
          <Suspense fallback={<PageLoader variant="inline" />}>{children}</Suspense>
        </main>
        <footer className="vg-footer">
          <span className="vg-footer-brand">VocalGuard</span>
          <span className="vg-footer-sep">·</span>
          <span className="vg-footer-copy">DanielCraftFr</span>
        </footer>
      </div>
      {sidebarOpen ? <div className="vg-sidebar-backdrop" onClick={handleCloseSidebar} /> : null}
      {routeLoading ? <PageLoader variant="overlay" label="Chargement…" /> : null}
    </div>
  );
};
