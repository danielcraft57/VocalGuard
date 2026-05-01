"use client";

import React, { useEffect, useState } from "react";
import { AppLayout } from "../../components/AppLayout";
import { fetchClients, Client } from "../../services/clientsApi";

function renderRow(client: Client): React.ReactNode {
  const created = new Date(client.created_at).toLocaleDateString("fr-FR");
  return (
    <tr key={client.id}>
      <td style={{ padding: "0.5rem 0.75rem" }}>{client.phone_number}</td>
      <td style={{ padding: "0.5rem 0.75rem" }}>{client.name ?? ""}</td>
      <td style={{ padding: "0.5rem 0.75rem" }}>{client.email ?? ""}</td>
      <td style={{ padding: "0.5rem 0.75rem" }}>{created}</td>
    </tr>
  );
}

export default function ClientsPage() {
  const [clients, setClients] = useState<Client[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchClients()
      .then((data) => {
        if (!cancelled) {
          setClients(data);
          setError(null);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError("Impossible de charger les clients (verifie le backend).");
          setClients([]);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <AppLayout title="Clients" subtitle="Contacts rattachés aux entreprises (personnes, emails, téléphone).">
      {loading ? (
        <div className="vg-card">
          <div className="vg-card-label" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <span className="material-icons" style={{ color: "#22c55e", fontSize: "18px" }}>
              hourglass_empty
            </span>
            Chargement des clients...
          </div>
        </div>
      ) : error ? (
        <div className="vg-card">
          <div className="vg-card-label" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <span className="material-icons" style={{ color: "#ef4444", fontSize: "18px" }}>
              error_outline
            </span>
            Erreur de chargement des clients
          </div>
          <div style={{ fontSize: "0.9rem", color: "#f97373" }}>{error}</div>
        </div>
      ) : clients.length === 0 ? (
        <div className="vg-card">
          <div className="vg-card-label" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <span className="material-icons" style={{ color: "#9ca3af", fontSize: "18px" }}>
              groups
            </span>
            Aucun client encore enregistré
          </div>
          <div style={{ fontSize: "0.9rem", color: "#9ca3af" }}>
            Dès qu’un RDV, un devis, ou un appel crée un contact, tu le verras ici.
          </div>
        </div>
      ) : (
        <div className="vg-card">
          <table className="vg-table">
            <thead>
              <tr>
                <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Numero</th>
                <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Nom</th>
                <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Email</th>
                <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Créé le</th>
              </tr>
            </thead>
            <tbody>{clients.map(renderRow)}</tbody>
          </table>
        </div>
      )}
    </AppLayout>
  );
}

