"use client";

import React, { createContext, useContext, useState, useCallback, useEffect } from "react";

const STORAGE_KEY = "vg-theme";

export interface ThemeContextValue {
  /** True = mode sombre pour toute l'app (sidebar + contenu). */
  isDark: boolean;
  setTheme: (dark: boolean) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function readStoredTheme(): boolean {
  if (typeof window === "undefined") return true;
  try {
    let stored = localStorage.getItem(STORAGE_KEY);
    if (stored === null) {
      stored = localStorage.getItem("vg-sidebar-theme");
    }
    return stored !== "light";
  } catch {
    return true;
  }
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [isDark, setIsDarkState] = useState(true);

  const setTheme = useCallback((dark: boolean) => {
    setIsDarkState(dark);
    try {
      localStorage.setItem(STORAGE_KEY, dark ? "dark" : "light");
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    setIsDarkState(readStoredTheme());
  }, []);

  const value: ThemeContextValue = { isDark, setTheme };

  return (
    <ThemeContext.Provider value={value}>
      <ThemeClassSync />
      {children}
    </ThemeContext.Provider>
  );
}

function ThemeClassSync() {
  const { isDark } = useTheme();
  useEffect(() => {
    document.documentElement.classList.toggle("vg-theme-dark", isDark);
    document.documentElement.classList.toggle("vg-theme-light", !isDark);
    return () => {
      document.documentElement.classList.remove("vg-theme-dark", "vg-theme-light");
    };
  }, [isDark]);
  return null;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error("useTheme doit etre utilise dans un ThemeProvider");
  }
  return ctx;
}
