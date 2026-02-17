"use client";

import React, { useMemo } from "react";
import { Area, AreaChart, CartesianGrid, Legend, Tooltip, XAxis, YAxis, PieChart, Pie, Cell } from "recharts";

type DailyStats = {
  day: string;
  calls: number;
  rdv: number;
  quotes: number;
  spam: number;
};

const COLORS = ["#22c55e", "#0ea5e9", "#ef4444"];

/**
 * Composant regroupant les graphiques du dashboard.
 * Pour l'instant, on utilise des données d'exemple en attendant
 * de brancher les vraies métriques.
 */
export const DashboardCharts: React.FC = () => {
  const data: DailyStats[] = useMemo(
    () => [
      { day: "Lun", calls: 18, rdv: 4, quotes: 2, spam: 3 },
      { day: "Mar", calls: 24, rdv: 6, quotes: 3, spam: 4 },
      { day: "Mer", calls: 19, rdv: 5, quotes: 4, spam: 2 },
      { day: "Jeu", calls: 27, rdv: 7, quotes: 5, spam: 5 },
      { day: "Ven", calls: 30, rdv: 9, quotes: 6, spam: 6 },
      { day: "Sam", calls: 14, rdv: 3, quotes: 2, spam: 1 },
      { day: "Dim", calls: 8, rdv: 1, quotes: 1, spam: 1 }
    ],
    []
  );

  const totalCalls = data.reduce((acc, d) => acc + d.calls, 0);
  const totalRdv = data.reduce((acc, d) => acc + d.rdv, 0);
  const totalQuotes = data.reduce((acc, d) => acc + d.quotes, 0);
  const totalSpam = data.reduce((acc, d) => acc + d.spam, 0);

  const conversionRate = totalCalls > 0 ? Math.round((totalRdv / totalCalls) * 100) : 0;
  const quoteRate = totalCalls > 0 ? Math.round((totalQuotes / totalCalls) * 100) : 0;

  const pieData = [
    { name: "Appels traités", value: totalCalls - totalSpam },
    { name: "Spams", value: totalSpam },
    { name: "Sans suite", value: Math.max(totalCalls - totalRdv - totalSpam, 0) }
  ];

  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 2fr) minmax(0, 1.2fr)", gap: "1.5rem", marginTop: "1.5rem" }}>
        <div className="vg-card">
        <div className="vg-card-label" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
          <span className="material-icons" style={{ fontSize: "18px", color: "#22c55e" }}>
            timeline
          </span>
          Volume d'appels & conversions
        </div>
        <div style={{ overflowX: "auto" }}>
          <AreaChart
            width={420}
            height={260}
            data={data}
            margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
          >
              <defs>
                <linearGradient id="colorCalls" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#22c55e" stopOpacity={0.8} />
                  <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" vertical={false} />
              <XAxis dataKey="day" stroke="#9ca3af" />
              <YAxis stroke="#9ca3af" />
              <Tooltip />
              <Legend />
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
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        <div className="vg-card">
          <div className="vg-card-label" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <span className="material-icons" style={{ fontSize: "18px", color: "#22c55e" }}>
              pie_chart
            </span>
            Répartition des appels
          </div>
          <div style={{ height: 180 }}>
            <PieChart width={220} height={180}>
              <Pie
                data={pieData}
                dataKey="value"
                nameKey="name"
                innerRadius={45}
                outerRadius={65}
                paddingAngle={3}
              >
                {pieData.map((entry, index) => (
                  <Cell key={entry.name} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </div>
        </div>

        <div className="vg-card">
          <div className="vg-card-label" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <span className="material-icons" style={{ fontSize: "18px", color: "#22c55e" }}>
              trending_up
            </span>
            Taux de conversion estimés
          </div>
          <div style={{ display: "flex", gap: "1rem" }}>
            <div style={{ flex: 1 }}>
              <div className="vg-card-label">Appels → RDV</div>
              <div className="vg-card-value">{conversionRate}%</div>
            </div>
            <div style={{ flex: 1 }}>
              <div className="vg-card-label">Appels → Devis</div>
              <div className="vg-card-value">{quoteRate}%</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

