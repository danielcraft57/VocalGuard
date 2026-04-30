"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "../contexts/ThemeContext";

export interface SidebarProps {
  /** Etat d'ouverture sur mobile. */
  isOpen?: boolean;
  /** Appelé lorsqu'on clique sur un lien (pratique pour refermer sur mobile). */
  onNavigate?: () => void;
}

/**
 * Determine si un lien est actif pour la route courante.
 *
 * @param pathname Route courante.
 * @param href Lien a tester.
 * @returns True si le lien doit etre considere comme actif.
 */
function isActive(pathname: string, href: string): boolean {
  if (href === "/dashboard") {
    return pathname === "/" || pathname.startsWith("/dashboard");
  }
  return pathname.startsWith(href);
}

/**
 * Sidebar principale de navigation pour VocalGuard.
 * Le theme (sombre par defaut) est gere par le context et s'applique a toute l'app.
 */
export const Sidebar: React.FC<SidebarProps> = ({ isOpen = false, onNavigate }) => {
  const pathname = usePathname();
  const { isDark, setTheme } = useTheme();

  const items = [
    { href: "/dashboard", label: "Dashboard", icon: "dashboard" },
    { href: "/calls", label: "Appels", icon: "call" },
    { href: "/filtering", label: "Filtrage d'appels", icon: "phonelink_erase" },
    { href: "/agenda", label: "Agenda", icon: "calendar_month" },
    { href: "/api", label: "API publique", icon: "api" },
    { href: "/quotes", label: "Devis", icon: "description" },
    { href: "/entreprises", label: "Entreprises", icon: "business" },
    { href: "/clients", label: "Clients", icon: "groups" },
    { href: "/kb", label: "Base de connaissances", icon: "help_outline" },
    { href: "/simulator", label: "Simulateur d'appel", icon: "mic" },
    { href: "/settings", label: "Parametres", icon: "settings" }
  ];

  const handleClick = () => {
    if (onNavigate) {
      onNavigate();
    }
  };

  return (
    <aside
      className={`vg-sidebar ${isOpen ? "vg-sidebar-open" : ""} ${!isDark ? "vg-sidebar--light" : ""}`}
    >
      <div className="vg-sidebar-title">VocalGuard</div>
      <nav className="vg-sidebar-nav">
        {items.map((item) => {
          const active = isActive(pathname, item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`vg-sidebar-link ${active ? "vg-sidebar-link-active" : ""}`}
              onClick={handleClick}
            >
              {item.icon ? (
                <span className="material-icons vg-sidebar-icon">{item.icon}</span>
              ) : null}
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>
      <div className="vg-sidebar-line" aria-hidden="true" />
      <div className="vg-sidebar-footer">
        <span className="vg-sidebar-theme-label">Theme</span>
        <div className="vg-sidebar-theme-toggle" role="group" aria-label="Mode clair / sombre">
          <button
            type="button"
            className={`vg-sidebar-theme-btn ${isDark ? "vg-sidebar-theme-btn--active" : ""}`}
            onClick={() => setTheme(true)}
            aria-pressed={isDark}
            aria-label="Mode sombre"
          >
            <span className="material-icons">dark_mode</span>
            <span>Sombre</span>
          </button>
          <button
            type="button"
            className={`vg-sidebar-theme-btn ${!isDark ? "vg-sidebar-theme-btn--active" : ""}`}
            onClick={() => setTheme(false)}
            aria-pressed={!isDark}
            aria-label="Mode clair"
          >
            <span className="material-icons">light_mode</span>
            <span>Clair</span>
          </button>
        </div>
      </div>
    </aside>
  );
};

