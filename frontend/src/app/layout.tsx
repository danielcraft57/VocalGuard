import React from "react";
import "../styles/globals.css";

export const metadata = {
  title: "VocalGuard - DanielCraftFr",
  description: "Tableau de bord VocalGuard pour la gestion des appels, RDV et devis."
};

export interface RootLayoutProps {
  children: React.ReactNode;
}

/**
 * Layout racine Next.js (app router).
 */
const RootLayout: React.FC<RootLayoutProps> = ({ children }) => {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
};

export default RootLayout;

