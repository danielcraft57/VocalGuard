"use client";

import React from "react";
import { usePageChrome } from "../contexts/PageChromeContext";

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
 * Compat pages existantes : pousse le titre vers le shell persistant
 * (ne remonte plus Sidebar / Topbar a chaque navigation).
 */
export const AppLayout: React.FC<AppLayoutProps> = ({
  children,
  title,
  subtitle,
  hidePageHeader = false
}) => {
  usePageChrome({ title, subtitle, hidePageHeader });
  return <>{children}</>;
};
