"""Tokens couleur M3 — themes clair et sombre Prospector."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Tuple

ThemeMode = Literal["dark", "light"]


@dataclass(frozen=True)
class ThemeTokens:
    """
    Palette complete pour la feuille Qt.

    Le mode clair vise un white mode net (neutres froids) avec plusieurs
    accents metier (indigo, teal, ambre, ciel, rose) pour eviter le monochrome.
    """

    bg: str
    bg_grad_top: str
    bg_grad_bottom: str
    surface: str
    surface_card: str
    surface_nav: str
    header_grad_start: str
    header_grad_end: str
    border: str
    border_strong: str
    primary: str
    primary_container: str
    on_primary: str
    on_primary_container: str
    secondary: str
    secondary_container: str
    tertiary: str
    tertiary_container: str
    info: str
    info_container: str
    warning: str
    warning_container: str
    on_surface: str
    on_surface_variant: str
    success: str
    error: str
    nav_badge_bg: str
    nav_badge_active: str
    nav_active_bg: str
    nav_indicator: str
    table_bg: str
    table_alt: str
    input_bg: str
    button_bg: str
    button_hover: str
    overlay_dim: str
    splash_border: str
    shadow: str
    chart_1: str
    chart_2: str
    chart_3: str
    chart_4: str


# Accents navigation (identiques clair / sombre, adaptes a l'icone)
NAV_ACCENTS: Tuple[str, ...] = (
    "#4f46e5",  # dashboard — indigo
    "#0d9488",  # campagnes — teal
    "#2563eb",  # cockpit — bleu
    "#d97706",  # line — ambre
    "#db2777",  # entrants — rose
    "#64748b",  # parametres — slate
)


DARK = ThemeTokens(
    bg="#0e0f14",
    bg_grad_top="#12141c",
    bg_grad_bottom="#0a0b10",
    surface="#161822",
    surface_card="#1c1f2b",
    surface_nav="#12141a",
    header_grad_start="#15171f",
    header_grad_end="#1a1d28",
    border="rgba(255,255,255,0.08)",
    border_strong="rgba(255,255,255,0.14)",
    primary="#a5b4fc",
    primary_container="#4f46e5",
    on_primary="#0f1220",
    on_primary_container="#eef2ff",
    secondary="#5eead4",
    secondary_container="rgba(13, 148, 136, 0.28)",
    tertiary="#fbbf24",
    tertiary_container="rgba(217, 119, 6, 0.28)",
    info="#7dd3fc",
    info_container="rgba(37, 99, 235, 0.28)",
    warning="#fbbf24",
    warning_container="rgba(217, 119, 6, 0.22)",
    on_surface="#eceef4",
    on_surface_variant="#9aa3b5",
    success="#34d399",
    error="#fca5a5",
    nav_badge_bg="rgba(79, 70, 229, 0.22)",
    nav_badge_active="#4f46e5",
    nav_active_bg="rgba(79, 70, 229, 0.22)",
    nav_indicator="#4f46e5",
    table_bg="#12141a",
    table_alt="#181b24",
    input_bg="#1a1d28",
    button_bg="#252836",
    button_hover="#32364a",
    overlay_dim="rgba(8, 9, 14, 0.88)",
    splash_border="rgba(165, 180, 252, 0.35)",
    shadow="rgba(0, 0, 0, 0.45)",
    chart_1="#6366f1",
    chart_2="#14b8a6",
    chart_3="#f59e0b",
    chart_4="#ec4899",
)

LIGHT = ThemeTokens(
    bg="#f3f4f7",
    bg_grad_top="#f8f9fb",
    bg_grad_bottom="#eef0f4",
    surface="#ffffff",
    surface_card="#ffffff",
    surface_nav="#ffffff",
    header_grad_start="#ffffff",
    header_grad_end="#f7f8fb",
    border="rgba(15, 23, 42, 0.08)",
    border_strong="rgba(15, 23, 42, 0.14)",
    primary="#3730a3",
    primary_container="#4f46e5",
    on_primary="#ffffff",
    on_primary_container="#ffffff",
    secondary="#0f766e",
    secondary_container="#ccfbf1",
    tertiary="#b45309",
    tertiary_container="#fef3c7",
    info="#1d4ed8",
    info_container="#dbeafe",
    warning="#b45309",
    warning_container="#ffedd5",
    on_surface="#0f172a",
    on_surface_variant="#64748b",
    success="#0f766e",
    error="#b91c1c",
    nav_badge_bg="#eef2ff",
    nav_badge_active="#4f46e5",
    nav_active_bg="#eef2ff",
    nav_indicator="#4f46e5",
    table_bg="#ffffff",
    table_alt="#f8fafc",
    input_bg="#f1f5f9",
    button_bg="#f1f5f9",
    button_hover="#e2e8f0",
    overlay_dim="rgba(15, 23, 42, 0.42)",
    splash_border="rgba(79, 70, 229, 0.22)",
    shadow="rgba(15, 23, 42, 0.10)",
    chart_1="#4f46e5",
    chart_2="#0d9488",
    chart_3="#d97706",
    chart_4="#db2777",
)


def tokens_for(mode: ThemeMode) -> ThemeTokens:
    """Retourne la palette pour le mode demande."""
    return LIGHT if mode == "light" else DARK


def nav_accent_for(index: int) -> str:
    """
    Couleur d'accent pour une entree de navigation.

    @param index Index 0-based dans le rail.
    @returns Hex couleur.
    """
    if not NAV_ACCENTS:
        return "#4f46e5"
    return NAV_ACCENTS[index % len(NAV_ACCENTS)]
