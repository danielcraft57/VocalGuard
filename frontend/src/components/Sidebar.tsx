import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

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
export const Sidebar: React.FC = () => {
  const pathname = usePathname();

  const items = [
    { href: "/dashboard", label: "Dashboard" },
    { href: "/calls", label: "Appels" },
    { href: "/appointments", label: "RDV" },
    { href: "/quotes", label: "Devis" },
    { href: "/customers", label: "Clients" },
    { href: "/kb", label: "Base de connaissances" },
    { href: "/simulator", label: "Simulateur d'appel" },
    { href: "/settings", label: "Parametres" }
  ];

  return (
    <aside className="vg-sidebar">
      <div className="vg-sidebar-title">VocalGuard</div>
      <nav className="vg-sidebar-nav">
        {items.map((item) => {
          const active = isActive(pathname, item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`vg-sidebar-link ${active ? "vg-sidebar-link-active" : ""}`}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
};

