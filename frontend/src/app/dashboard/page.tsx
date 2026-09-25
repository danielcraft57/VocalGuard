"use client";

import React, { useCallback } from "react";
import Link from "next/link";
import { Box } from "@mui/material";
import { AppLayout } from "../../components/AppLayout";
import { DashboardCharts } from "../../components/DashboardCharts";
import { VgTelephonyStatusStrip } from "../../components/mui/VgTelephonyStatusStrip";
import { VgSoftSyncBar } from "../../components/mui/VgSoftSyncBar";
import { VgCardsSkeleton } from "../../components/mui/VgListSkeleton";
import { fetchDashboardStats, DashboardStats } from "../../services/dashboardStatsApi";
import { useSoftCachedLoad } from "../../hooks/useSoftCachedLoad";
import { UI_CACHE_KEYS } from "../../services/uiPersist";

/**
 * Dashboard : stats chargees cote client pour afficher les vraies donnees.
 */
export default function DashboardPage() {
  const fetcher = useCallback(
    (signal: AbortSignal) => fetchDashboardStats(signal),
    []
  );
  const { data: stats, loading, syncing, error } = useSoftCachedLoad<DashboardStats>({
    cacheKey: UI_CACHE_KEYS.dashboardStats,
    fetcher
  });

  const cards: {
    label: string;
    value: string | number;
    icon: string;
    color: string;
    href?: string;
  }[] = [
    {
      label: "Appels aujourd'hui",
      value: stats?.calls_today ?? "-",
      icon: "call",
      color: "#22c55e",
    },
    {
      label: "Bloques aujourd'hui",
      value: stats?.blocked_today ?? "-",
      icon: "block",
      color: "#ef4444",
      href: "/calls"
    },
    {
      label: "Messages non lus",
      value: stats?.voicemails_unread ?? "-",
      icon: "voicemail",
      color: "#f59e0b",
    },
    {
      label: "Messages aujourd'hui",
      value: stats?.voicemails_today ?? "-",
      icon: "mic",
      color: "#0ea5e9",
    },
    {
      label: "Appels suspects (OSINT)",
      value: stats?.suspects_count ?? "-",
      icon: "report_gmailerrorred",
      color: "#ef4444",
    },
  ];

  return (
    <AppLayout
      title="Dashboard"
      subtitle="Vue d'ensemble des appels, RDV et devis VocalGuard."
    >
      <VgTelephonyStatusStrip />
      {syncing ? (
        <Box sx={{ display: "flex", justifyContent: "flex-end", mb: 1 }}>
          <VgSoftSyncBar label="Synchro stats…" />
        </Box>
      ) : null}
      {error && !stats ? (
        <div className="vg-card">
          <div className="vg-card-label" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <span className="material-icons" style={{ color: "#ef4444", fontSize: "18px" }}>
              error_outline
            </span>
            Erreur de chargement des stats
          </div>
          <div style={{ fontSize: "0.9rem", color: "#ef4444" }}>{error}</div>
        </div>
      ) : loading && !stats ? (
        <VgCardsSkeleton count={5} />
      ) : (
        <div className="vg-card-grid">
          {cards.map((card) => (
            <div key={card.label} className="vg-card">
              <div className="vg-card-label" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                <span className="material-icons" style={{ fontSize: "18px", color: card.color }}>
                  {card.icon}
                </span>
                {card.label}
              </div>
              <div className="vg-card-value">{card.value}</div>
              {"href" in card && card.href ? (
                <Link href={card.href} style={{ fontSize: "0.8rem", marginTop: "0.35rem", display: "inline-block" }}>
                  Voir les appels
                </Link>
              ) : null}
            </div>
          ))}
        </div>
      )}

      <DashboardCharts stats={stats} loading={loading && !stats} />
    </AppLayout>
  );
}
