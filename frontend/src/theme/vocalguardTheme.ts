import { createTheme, type Theme } from "@mui/material/styles";

/**
 * Cree le theme Material VocalGuard (dark ou light).
 *
 * @param mode Palette claire ou sombre.
 * @returns Theme MUI.
 */
export function createVocalGuardTheme(mode: "light" | "dark"): Theme {
  const isDark = mode === "dark";
  return createTheme({
    palette: {
      mode,
      primary: {
        main: "#22c55e",
        light: "#4ade80",
        dark: "#16a34a",
        contrastText: "#052e16"
      },
      secondary: {
        main: isDark ? "#94a3b8" : "#64748b"
      },
      success: {
        main: "#22c55e"
      },
      warning: {
        main: "#f59e0b"
      },
      error: {
        main: "#ef4444"
      },
      background: {
        default: isDark ? "#0f1419" : "#f8fafc",
        paper: isDark ? "#1a2332" : "#ffffff"
      },
      text: {
        primary: isDark ? "#f1f5f9" : "#0f172a",
        secondary: isDark ? "#94a3b8" : "#64748b"
      }
    },
    shape: {
      borderRadius: 12
    },
    typography: {
      fontFamily: '"Segoe UI", system-ui, -apple-system, sans-serif',
      h5: { fontWeight: 600 },
      h6: { fontWeight: 600 }
    },
    components: {
      MuiCard: {
        defaultProps: { elevation: 0 },
        styleOverrides: {
          root: {
            border: isDark ? "1px solid rgba(148,163,184,0.12)" : "1px solid rgba(15,23,42,0.08)"
          }
        }
      },
      MuiButton: {
        styleOverrides: {
          root: { textTransform: "none", fontWeight: 600 }
        }
      }
    }
  });
}
