"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

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
 */
export const Sidebar: React.FC<SidebarProps> = ({ isOpen = false, onNavigate }) => {
  const pathname = usePathname();

  const items = [
    { href: "/dashboard", label: "Dashboard", icon: "dashboard" },
    { href: "/calls", label: "Appels", icon: "call" },
    { href: "/appointments", label: "RDV", icon: "event" },
    { href: "/quotes", label: "Devis", icon: "description" },
    { href: "/customers", label: "Clients", icon: "groups" },
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
    <aside className={`vg-sidebar ${isOpen ? "vg-sidebar-open" : ""}`}>
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
                <span className="material-icons" style={{ fontSize: "18px", marginRight: "0.5rem" }}>
                  {item.icon}
                </span>
              ) : null}
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
};

