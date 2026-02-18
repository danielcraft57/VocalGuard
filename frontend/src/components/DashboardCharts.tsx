"use client";

import React, { useMemo } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Tooltip,
  XAxis,
  YAxis,
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
} from "recharts";
import type { DashboardStats } from "../services/dashboardStatsApi";

const COLORS = ["#22c55e", "#0ea5e9", "#ef4444"];

export interface DashboardChartsProps {
  /** Stats retournees par l'API (valeurs reelles backend). */
  stats: DashboardStats | null;
  /** True pendant le chargement. */
  loading?: boolean;
}

/**
 * Graphiques du dashboard branches sur les donnees reelles du backend.
 */
export const DashboardCharts: React.FC<DashboardChartsProps> = ({ stats, loading = false }) => {
  const data = useMemo(() => stats?.daily_series ?? [], [stats?.daily_series]);

  const totalCalls = stats?.total_calls ?? 0;
  const totalBlocked = stats?.total_blocked ?? 0;
  const totalRdv = stats?.rdv_count ?? 0;
  const totalQuotes = stats?.quotes_count ?? 0;

  const conversionRate = totalCalls > 0 ? Math.round((totalRdv / totalCalls) * 100) : 0;
  const quoteRate = totalCalls > 0 ? Math.round((totalQuotes / totalCalls) * 100) : 0;

  const pieData = useMemo(
    () => [
      { name: "Appels traités", value: Math.max(totalCalls - totalBlocked, 0) },
      { name: "Spams", value: totalBlocked },
      {
        name: "Sans suite",
        value: Math.max(totalCalls - totalRdv - totalBlocked, 0),
      },
    ],
    [totalCalls, totalBlocked, totalRdv]
  );

  if (loading || !stats) {
    return (
      <div className="vg-charts-grid">
        <div className="vg-card vg-chart-area-wrap">
          <div className="vg-card-label vg-chart-label">
            <span className="material-icons vg-chart-icon">timeline</span>
            Volume d'appels & conversions
          </div>
          <div className="vg-chart-area-container" style={{ minHeight: 220, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--vg-color-text-muted)" }}>
            {loading ? "Chargement..." : "Données indisponibles"}
          </div>
        </div>
        <div className="vg-charts-side">
          <div className="vg-card">
            <div className="vg-card-label vg-chart-label">
              <span className="material-icons vg-chart-icon">pie_chart</span>
              Répartition des appels
            </div>
            <div className="vg-chart-pie-container" style={{ display: "flex", alignItems: "center", justifyContent: "center", color: "var(--vg-color-text-muted)" }}>
              {loading ? "Chargement..." : "Données indisponibles"}
            </div>
          </div>
          <div className="vg-card">
            <div className="vg-card-label vg-chart-label">
              <span className="material-icons vg-chart-icon">trending_up</span>
              Taux de conversion estimés
            </div>
            <div className="vg-chart-rates">
              <div className="vg-chart-rate-item">
                <div className="vg-card-label">Appels → RDV</div>
                <div className="vg-card-value">-</div>
              </div>
              <div className="vg-chart-rate-item">
                <div className="vg-card-label">Appels → Devis</div>
                <div className="vg-card-value">-</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="vg-charts-grid">
      <div className="vg-card vg-chart-area-wrap">
        <div className="vg-card-label vg-chart-label">
          <span className="material-icons vg-chart-icon">timeline</span>
          Volume d'appels & conversions
        </div>
        <div className="vg-chart-area-container">
          <ResponsiveContainer width="100%" height={260} minHeight={220}>
            <AreaChart
              data={data}
              margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
            >
              <defs>
                <linearGradient id="colorCalls" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#22c55e" stopOpacity={0.8} />
                  <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--vg-color-border-subtle)" vertical={false} />
              <XAxis dataKey="day" stroke="var(--vg-color-text-muted)" tick={{ fontSize: 12 }} />
              <YAxis stroke="var(--vg-color-text-muted)" tick={{ fontSize: 12 }} width={32} />
              <Tooltip />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Area
                type="monotone"
                dataKey="calls"
                stroke="#22c55e"
                fillOpacity={1}
                fill="url(#colorCalls)"
                name="Appels"
              />
              <Area
                type="monotone"
                dataKey="rdv"
                stroke="#0ea5e9"
                fillOpacity={0.3}
                fill="#0ea5e9"
                name="RDV"
              />
              <Area
                type="monotone"
                dataKey="quotes"
                stroke="#6366f1"
                fillOpacity={0.2}
                fill="#6366f1"
                name="Devis"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="vg-charts-side">
        <div className="vg-card">
          <div className="vg-card-label vg-chart-label">
            <span className="material-icons vg-chart-icon">pie_chart</span>
            Répartition des appels
          </div>
          <div className="vg-chart-pie-container">
            <ResponsiveContainer width="100%" height={180}>
              <PieChart>
                <Pie
                  data={pieData}
                  dataKey="value"
                  nameKey="name"
                  innerRadius="40%"
                  outerRadius="65%"
                  paddingAngle={3}
                >
                  {pieData.map((entry, index) => (
                    <Cell key={entry.name} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="vg-card">
          <div className="vg-card-label vg-chart-label">
            <span className="material-icons vg-chart-icon">trending_up</span>
            Taux de conversion estimés
          </div>
          <div className="vg-chart-rates">
            <div className="vg-chart-rate-item">
              <div className="vg-card-label">Appels → RDV</div>
              <div className="vg-card-value">{conversionRate}%</div>
            </div>
            <div className="vg-chart-rate-item">
              <div className="vg-card-label">Appels → Devis</div>
              <div className="vg-card-value">{quoteRate}%</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

