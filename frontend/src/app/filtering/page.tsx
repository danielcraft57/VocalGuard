"use client";

import React, { useState, useEffect, useCallback } from "react";
import { AppLayout } from "../../components/AppLayout";
import {
  fetchWhitelist,
  fetchBlocklist,
  addToWhitelist,
  addToBlocklist,
  removeFromWhitelist,
  removeFromBlocklist,
  Caller,
} from "../../services/callersFilterApi";
import {
  fetchBlockRules,
  createBlockRule,
  deleteBlockRule,
  BlockRule,
} from "../../services/blockRulesApi";

/**
 * Page Filtrage d'appels : liste blanche, liste noire, regles de blocage.
 * Inspire de l'interface callattendant (Permitted / Blocked / patterns).
 */
export default function FilteringPage() {
  const [whitelist, setWhitelist] = useState<Caller[]>([]);
  const [blocklist, setBlocklist] = useState<Caller[]>([]);
  const [rules, setRules] = useState<BlockRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [w, b, r] = await Promise.all([
        fetchWhitelist(),
        fetchBlocklist(),
        fetchBlockRules(),
      ]);
      setWhitelist(w);
      setBlocklist(b);
      setRules(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur de chargement");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const [whitelistPhone, setWhitelistPhone] = useState("");
  const [whitelistName, setWhitelistName] = useState("");
  const [blocklistPhone, setBlocklistPhone] = useState("");
  const [blocklistNotes, setBlocklistNotes] = useState("");
  const [ruleName, setRuleName] = useState("");
  const [rulePattern, setRulePattern] = useState("");
  const [ruleType, setRuleType] = useState<"exact" | "prefix" | "regex">("prefix");
  const [submitting, setSubmitting] = useState<string | null>(null);

  const handleAddWhitelist = async (e: React.FormEvent) => {
    e.preventDefault();
    const phone = whitelistPhone.trim().replace(/\s/g, "");
    if (!phone) return;
    setSubmitting("whitelist");
    try {
      await addToWhitelist(phone, whitelistName.trim() || null, null);
      setWhitelistPhone("");
      setWhitelistName("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur");
    } finally {
      setSubmitting(null);
    }
  };

  const handleRemoveWhitelist = async (id: number) => {
    setSubmitting(`w-${id}`);
    try {
      await removeFromWhitelist(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur");
    } finally {
      setSubmitting(null);
    }
  };

  const handleAddBlocklist = async (e: React.FormEvent) => {
    e.preventDefault();
    const phone = blocklistPhone.trim().replace(/\s/g, "");
    if (!phone) return;
    setSubmitting("blocklist");
    try {
      await addToBlocklist(phone, null, blocklistNotes.trim() || null);
      setBlocklistPhone("");
      setBlocklistNotes("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur");
    } finally {
      setSubmitting(null);
    }
  };

  const handleRemoveBlocklist = async (id: number) => {
    setSubmitting(`b-${id}`);
    try {
      await removeFromBlocklist(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur");
    } finally {
      setSubmitting(null);
    }
  };

  const handleAddRule = async (e: React.FormEvent) => {
    e.preventDefault();
    const name = ruleName.trim();
    const pattern = rulePattern.trim();
    if (!name || !pattern) return;
    setSubmitting("rule");
    try {
      await createBlockRule(name, pattern, ruleType);
      setRuleName("");
      setRulePattern("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur");
    } finally {
      setSubmitting(null);
    }
  };

  const handleDeleteRule = async (id: number) => {
    setSubmitting(`r-${id}`);
    try {
      await deleteBlockRule(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur");
    } finally {
      setSubmitting(null);
    }
  };

  return (
    <AppLayout
      title="Filtrage d'appels"
      subtitle="Liste blanche (autorisés), liste noire (bloqués) et règles par motif. Inspiré de callattendant."
    >
      {error ? (
        <div className="vg-card" style={{ marginBottom: "1rem" }}>
          <div className="vg-card-label" style={{ display: "flex", alignItems: "center", gap: "0.4rem", color: "#ef4444" }}>
            <span className="material-icons" style={{ fontSize: "18px" }}>error_outline</span>
            {error}
          </div>
          <button type="button" onClick={() => setError(null)} style={{ marginTop: "0.5rem", fontSize: "0.85rem" }}>
            Fermer
          </button>
        </div>
      ) : null}

      {loading ? (
        <div className="vg-card">
          <div className="vg-card-label" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <span className="material-icons" style={{ color: "#22c55e", fontSize: "18px" }}>hourglass_empty</span>
            Chargement des listes...
          </div>
        </div>
      ) : (
        <>
          {/* Liste blanche (Permitted) */}
          <div className="vg-card" style={{ marginBottom: "1.5rem" }}>
            <div className="vg-card-label" style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginBottom: "0.5rem" }}>
              <span className="material-icons" style={{ color: "#22c55e", fontSize: "18px" }}>verified_user</span>
              Liste blanche (numéros autorisés)
            </div>
            <p style={{ fontSize: "0.85rem", color: "var(--vg-color-text-muted)", marginBottom: "0.75rem" }}>
              Ces numéros ne sont jamais bloqués (priorité sur liste noire et règles).
            </p>
            <form onSubmit={handleAddWhitelist} style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginBottom: "1rem" }}>
              <input
                type="text"
                placeholder="Numéro (ex. 0612345678)"
                value={whitelistPhone}
                onChange={(e) => setWhitelistPhone(e.target.value)}
                style={{ padding: "0.4rem 0.6rem", borderRadius: "var(--vg-radius-sm)", border: "1px solid var(--vg-color-border-subtle)", minWidth: "140px" }}
              />
              <input
                type="text"
                placeholder="Nom (optionnel)"
                value={whitelistName}
                onChange={(e) => setWhitelistName(e.target.value)}
                style={{ padding: "0.4rem 0.6rem", borderRadius: "var(--vg-radius-sm)", border: "1px solid var(--vg-color-border-subtle)", minWidth: "120px" }}
              />
              <button type="submit" disabled={!!submitting} className="vg-btn-primary">
                {submitting === "whitelist" ? "..." : "Ajouter"}
              </button>
            </form>
            <table className="vg-table">
              <thead>
                <tr>
                  <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Numéro</th>
                  <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Nom</th>
                  <th style={{ textAlign: "right", padding: "0.5rem 0.75rem" }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {whitelist.length === 0 ? (
                  <tr><td colSpan={3} style={{ padding: "0.75rem", color: "var(--vg-color-text-muted)" }}>Aucun numéro en liste blanche.</td></tr>
                ) : (
                  whitelist.map((c) => (
                    <tr key={c.id} className="vg-table-row">
                      <td style={{ padding: "0.5rem 0.75rem" }}>{c.phone_number}</td>
                      <td style={{ padding: "0.5rem 0.75rem" }}>{c.name ?? "-"}</td>
                      <td style={{ padding: "0.5rem 0.75rem", textAlign: "right" }}>
                        <button type="button" onClick={() => handleRemoveWhitelist(c.id)} disabled={!!submitting} className="vg-btn-danger-sm">
                          Retirer
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Liste noire (Blocked) */}
          <div className="vg-card" style={{ marginBottom: "1.5rem" }}>
            <div className="vg-card-label" style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginBottom: "0.5rem" }}>
              <span className="material-icons" style={{ color: "#ef4444", fontSize: "18px" }}>block</span>
              Liste noire (numéros bloqués)
            </div>
            <p style={{ fontSize: "0.85rem", color: "var(--vg-color-text-muted)", marginBottom: "0.75rem" }}>
              Ces numéros sont bloqués à l'arrivée d'un appel (message court puis raccrochage).
            </p>
            <form onSubmit={handleAddBlocklist} style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginBottom: "1rem" }}>
              <input
                type="text"
                placeholder="Numéro à bloquer"
                value={blocklistPhone}
                onChange={(e) => setBlocklistPhone(e.target.value)}
                style={{ padding: "0.4rem 0.6rem", borderRadius: "var(--vg-radius-sm)", border: "1px solid var(--vg-color-border-subtle)", minWidth: "140px" }}
              />
              <input
                type="text"
                placeholder="Raison (optionnel)"
                value={blocklistNotes}
                onChange={(e) => setBlocklistNotes(e.target.value)}
                style={{ padding: "0.4rem 0.6rem", borderRadius: "var(--vg-radius-sm)", border: "1px solid var(--vg-color-border-subtle)", minWidth: "120px" }}
              />
              <button type="submit" disabled={!!submitting} className="vg-btn-danger">
                {submitting === "blocklist" ? "..." : "Bloquer"}
              </button>
            </form>
            <table className="vg-table">
              <thead>
                <tr>
                  <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Numéro</th>
                  <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Nom / notes</th>
                  <th style={{ textAlign: "right", padding: "0.5rem 0.75rem" }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {blocklist.length === 0 ? (
                  <tr><td colSpan={3} style={{ padding: "0.75rem", color: "var(--vg-color-text-muted)" }}>Aucun numéro en liste noire.</td></tr>
                ) : (
                  blocklist.map((c) => (
                    <tr key={c.id} className="vg-table-row">
                      <td style={{ padding: "0.5rem 0.75rem" }}>{c.phone_number}</td>
                      <td style={{ padding: "0.5rem 0.75rem" }}>{c.name || c.notes || "-"}</td>
                      <td style={{ padding: "0.5rem 0.75rem", textAlign: "right" }}>
                        <button type="button" onClick={() => handleRemoveBlocklist(c.id)} disabled={!!submitting} className="vg-btn-success-sm">
                          Débloquer
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Règles de blocage (patterns) */}
          <div className="vg-card">
            <div className="vg-card-label" style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginBottom: "0.5rem" }}>
              <span className="material-icons" style={{ color: "#0ea5e9", fontSize: "18px" }}>rule</span>
              Règles de blocage (motif)
            </div>
            <p style={{ fontSize: "0.85rem", color: "var(--vg-color-text-muted)", marginBottom: "0.75rem" }}>
              Bloquer par numéro exact, préfixe (ex. 089) ou expression régulière.
            </p>
            <form onSubmit={handleAddRule} style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginBottom: "1rem" }}>
              <input
                type="text"
                placeholder="Nom de la règle"
                value={ruleName}
                onChange={(e) => setRuleName(e.target.value)}
                style={{ padding: "0.4rem 0.6rem", borderRadius: "var(--vg-radius-sm)", border: "1px solid var(--vg-color-border-subtle)", minWidth: "120px" }}
              />
              <input
                type="text"
                placeholder="Pattern (ex. 089 ou ^089)"
                value={rulePattern}
                onChange={(e) => setRulePattern(e.target.value)}
                style={{ padding: "0.4rem 0.6rem", borderRadius: "var(--vg-radius-sm)", border: "1px solid var(--vg-color-border-subtle)", minWidth: "120px" }}
              />
              <select
                value={ruleType}
                onChange={(e) => setRuleType(e.target.value as "exact" | "prefix" | "regex")}
                style={{ padding: "0.4rem 0.6rem", borderRadius: "var(--vg-radius-sm)", border: "1px solid var(--vg-color-border-subtle)" }}
              >
                <option value="exact">Exact</option>
                <option value="prefix">Préfixe</option>
                <option value="regex">Regex</option>
              </select>
              <button type="submit" disabled={!!submitting} className="vg-btn-primary">
                {submitting === "rule" ? "..." : "Ajouter la règle"}
              </button>
            </form>
            <table className="vg-table">
              <thead>
                <tr>
                  <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Nom</th>
                  <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Pattern</th>
                  <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Type</th>
                  <th style={{ textAlign: "right", padding: "0.5rem 0.75rem" }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {rules.length === 0 ? (
                  <tr><td colSpan={4} style={{ padding: "0.75rem", color: "var(--vg-color-text-muted)" }}>Aucune règle.</td></tr>
                ) : (
                  rules.map((r) => (
                    <tr key={r.id} className="vg-table-row">
                      <td style={{ padding: "0.5rem 0.75rem" }}>{r.name}</td>
                      <td style={{ padding: "0.5rem 0.75rem", fontFamily: "monospace" }}>{r.pattern}</td>
                      <td style={{ padding: "0.5rem 0.75rem" }}><span className="vg-badge vg-badge-warn">{r.pattern_type}</span></td>
                      <td style={{ padding: "0.5rem 0.75rem", textAlign: "right" }}>
                        <button type="button" onClick={() => handleDeleteRule(r.id)} disabled={!!submitting} className="vg-btn-danger-sm">
                          Supprimer
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </AppLayout>
  );
}
