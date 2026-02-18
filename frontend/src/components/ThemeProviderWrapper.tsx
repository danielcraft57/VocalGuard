"use client";

import React from "react";
import { ThemeProvider } from "../contexts/ThemeContext";

/**
 * Wrapper client qui fournit le theme a toute l'app.
 * Utilise dans le layout racine pour que le choix Dark/Clair persiste a la navigation.
 */
export function ThemeProviderWrapper({ children }: { children: React.ReactNode }) {
  return <ThemeProvider>{children}</ThemeProvider>;
}
