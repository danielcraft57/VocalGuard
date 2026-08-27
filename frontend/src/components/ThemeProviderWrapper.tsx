"use client";

import React from "react";
import { CssBaseline, ThemeProvider as MuiThemeProvider } from "@mui/material";
import { ThemeProvider, useTheme } from "../contexts/ThemeContext";
import { createVocalGuardTheme } from "../theme/vocalguardTheme";

/**
 * Applique le theme MUI synchronise avec le mode dark/light VocalGuard.
 */
function MuiBridge({ children }: { children: React.ReactNode }) {
  const { isDark } = useTheme();
  const theme = React.useMemo(
    () => createVocalGuardTheme(isDark ? "dark" : "light"),
    [isDark]
  );
  return (
    <MuiThemeProvider theme={theme}>
      <CssBaseline enableColorScheme />
      {children}
    </MuiThemeProvider>
  );
}

/**
 * Wrapper client : theme CSS VocalGuard + Material UI.
 */
export function ThemeProviderWrapper({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider>
      <MuiBridge>{children}</MuiBridge>
    </ThemeProvider>
  );
}
