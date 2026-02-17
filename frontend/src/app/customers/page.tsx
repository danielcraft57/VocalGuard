import React from "react";
import { AppLayout } from "../../components/AppLayout";
import { fetchCustomers, Customer } from "../../services/customersApi";

function renderRow(customer: Customer): React.ReactNode {
  const created = new Date(customer.created_at).toLocaleDateString("fr-FR");
  return (
    <tr key={customer.id}>
      <td style={{ padding: "0.5rem 0.75rem" }}>{customer.phone_number}</td>
      <td style={{ padding: "0.5rem 0.75rem" }}>{customer.name ?? ""}</td>
      <td style={{ padding: "0.5rem 0.75rem" }}>{customer.company_name ?? ""}</td>
      <td style={{ padding: "0.5rem 0.75rem" }}>{customer.email ?? ""}</td>
      <td style={{ padding: "0.5rem 0.75rem" }}>{created}</td>
    </tr>
  );
}

/**
 * Page liste des clients / mini CRM.
 */
const CustomersPage = async () => {
  let customers: Customer[] = [];
  let error: string | null = null;

  try {
    customers = await fetchCustomers();
  } catch {
    error = "Impossible de charger les clients (verifie le backend).";
  }

  return (
    <AppLayout
      title="Clients"
      subtitle="Dossiers clients centralises (appels, RDV, devis...)."
    >
      {error ? (
        <div className="vg-card">
          <div className="vg-card-label" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <span className="material-icons" style={{ color: "#ef4444", fontSize: "18px" }}>
              error_outline
            </span>
            Erreur de chargement des clients
          </div>
          <div style={{ fontSize: "0.9rem", color: "#f97373" }}>{error}</div>
        </div>
      ) : customers.length === 0 ? (
        <div className="vg-card">
          <div className="vg-card-label" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <span className="material-icons" style={{ color: "#9ca3af", fontSize: "18px" }}>
              groups
            </span>
            Aucun client encore enregistre
          </div>
          <div style={{ fontSize: "0.9rem", color: "#9ca3af" }}>
            Des que des appels ou RDV creeront des dossiers, tu les verras ici.
          </div>
        </div>
      ) : (
        <div className="vg-card">
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.9rem" }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Numero</th>
                <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Nom</th>
                <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Entreprise</th>
                <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Email</th>
                <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Cree le</th>
              </tr>
            </thead>
            <tbody>{customers.map(renderRow)}</tbody>
          </table>
        </div>
      )}
    </AppLayout>
  );
};

export default CustomersPage;

