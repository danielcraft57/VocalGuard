import React from "react";
import "../styles/globals.css";
import { ThemeProviderWrapper } from "../components/ThemeProviderWrapper";

export const metadata = {
  title: "VocalGuard - DanielCraftFr",
  description: "Tableau de bord VocalGuard pour la gestion des appels, RDV et devis."
};

export interface RootLayoutProps {
  children: React.ReactNode;
}

/**
 * Layout racine Next.js (app router).
 * ThemeProviderWrapper applique le theme (dark/light) a toute l'app.
 */
const RootLayout: React.FC<RootLayoutProps> = ({ children }) => {
  return (
    <html lang="fr">
      <head>
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/icon?family=Material+Icons"
        />
        <link
          rel="stylesheet"
          href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css"
          integrity="sha512-DTOQO9RWCH3ppGqcWaEA1BIZOC6xxalwEsw9c2QQeAIftl+Vegovlnee1c9QX4TctnWMn13TZye+giMm8e2LwA=="
          crossOrigin="anonymous"
          referrerPolicy="no-referrer"
        />
      </head>
      <body>
        <ThemeProviderWrapper>{children}</ThemeProviderWrapper>
      </body>
    </html>
  );
};

export default RootLayout;

