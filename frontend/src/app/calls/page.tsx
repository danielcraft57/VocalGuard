"use client";

import React, { useState, useEffect } from "react";
import { AppLayout } from "../../components/AppLayout";
import { fetchCallsWithOsint, CallWithOsint } from "../../services/callsApi";

function formatStatus(status: string): { label: string; className: string } {
  const normalized = status.toLowerCase();
  if (normalized === "answered" || normalized === "completed") {
    return { label: "Répondu", className: "vg-badge vg-badge-success" };
  }
  if (normalized === "missed") {
    return { label: "Manqué", className: "vg-badge vg-badge-warn" };
  }
  if (normalized === "blocked") {
    return { label: "Bloqué", className: "vg-badge vg-badge-danger" };
  }
  return { label: status, className: "vg-badge" };
}

/** Categorie de reputation pour affichage et filtres */
type ReputationCategory = "good" | "bad" | "neutral" | "unknown";

function getReputationCategory(osint?: CallWithOsint["osint"]): ReputationCategory {
  if (!osint) return "unknown";
  const rep = (osint.reputation || "unknown").toLowerCase();
  if (rep === "high") return "good";
  if (rep === "low" || osint.is_spam || osint.is_scam || osint.is_telemarketer) return "bad";
  if (rep === "neutral") return "neutral";
  return "unknown";
}

function formatReputation(osint?: CallWithOsint["osint"]): React.ReactNode {
  const cat = getReputationCategory(osint);
  if (cat === "good") {
    return (
      <span className="vg-chip">
        <span className="vg-chip-dot vg-chip-dot--good" />
        <span>Bonne</span>
      </span>
    );
  }
  if (cat === "bad") {
    return (
      <span className="vg-chip">
        <span className="vg-chip-dot vg-chip-dot--bad" />
        <span>Risque</span>
      </span>
    );
  }
  if (cat === "neutral") {
    return (
      <span className="vg-chip">
        <span className="vg-chip-dot vg-chip-dot--unknown" />
        <span>Non evaluee</span>
      </span>
    );
  }
  return (
    <span className="vg-chip">
      <span className="vg-chip-dot vg-chip-dot--unknown" />
      <span>Inconnue</span>
    </span>
  );
}

function renderRow(call: CallWithOsint): React.ReactNode {
  const date = new Date(call.call_time).toLocaleString("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
  const phone = call.phone_number ?? "Inconnu";
  const { label: statusLabel, className: statusClass } = formatStatus(call.status);
  const intent =
    (call.extra_data && typeof call.extra_data === "object" && "ivr_intent" in call.extra_data
      ? (call.extra_data as { ivr_intent?: string | null }).ivr_intent
      : null) || null;
  const shortTranscript =
    (call.transcription && call.transcription.length > 80
      ? `${call.transcription.slice(0, 77)}...`
      : call.transcription) || null;

  const lieu = call.osint
    ? [call.osint.city, call.osint.region].filter(Boolean).join(", ") || "-"
    : "-";
  const operateur = call.osint?.operator ?? "-";

  return (
    <tr
      key={call.id}
      style={{ transition: "background-color 150ms ease-out" }}
      className="vg-table-row"
    >
      <td style={{ padding: "0.5rem 0.75rem" }}>{date}</td>
      <td style={{ padding: "0.5rem 0.75rem", display: "flex", alignItems: "center", gap: "0.35rem" }}>
        <span className="material-icons" style={{ fontSize: "16px", color: "#22c55e" }}>
          phone_in_talk
        </span>
        <span>{phone}</span>
      </td>
      <td style={{ padding: "0.5rem 0.75rem" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.15rem" }}>
          <span className={statusClass}>{statusLabel}</span>
          {intent && (
            <span
              style={{
                fontSize: "0.7rem",
                padding: "0.1rem 0.4rem",
                borderRadius: "999px",
                border: "1px solid #4b5563",
                color: "#e5e7eb",
                alignSelf: "flex-start"
              }}
            >
              Intent: {intent}
            </span>
          )}
        </div>
      </td>
      <td style={{ padding: "0.5rem 0.75rem" }}>
        {formatReputation(call.osint)}
        {shortTranscript && (
          <div
            style={{
              marginTop: "0.25rem",
              fontSize: "0.7rem",
              color: "#9ca3af",
              maxWidth: "14rem",
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis"
            }}
            title={call.transcription ?? undefined}
          >
            “{shortTranscript}”
          </div>
        )}
      </td>
      <td style={{ padding: "0.5rem 0.75rem" }}>{lieu}</td>
      <td style={{ padding: "0.5rem 0.75rem" }}>{operateur}</td>
    </tr>
  );
}

/** Valeur normalisee du statut pour les filtres */
function getStatusFilterValue(status: string): string {
  const n = status.toLowerCase();
  if (n === "answered" || n === "completed") return "answered";
  if (n === "missed") return "missed";
  if (n === "blocked") return "blocked";
  return status;
}

const FILTER_STATUS_ALL = "all";
const FILTER_REP_ALL = "all";

/** Mots-cles reconnus par la recherche pour statut / reputation */
const STATUS_KEYWORDS: Record<string, string> = {
  repondu: "answered",
  repondus: "answered",
  answered: "answered",
  manque: "missed",
  manques: "missed",
  missed: "missed",
  bloque: "blocked",
  bloques: "blocked",
  blocked: "blocked"
};
const REP_KEYWORDS: Record<string, string> = {
  bonne: "good",
  bon: "good",
  good: "good",
  risque: "bad",
  risques: "bad",
  spam: "bad",
  low: "bad",
  "non evaluee": "neutral",
  evaluee: "neutral",
  neutral: "neutral",
  inconnue: "unknown",
  inconnu: "unknown",
  unknown: "unknown"
};

/**
 * Parse la requete de recherche : extrait mots-cles statut/reputation et texte libre.
 * Reconnait "repondu", "manque", "bloque", "bonne", "risque", "non evaluee", "inconnue", etc.
 */
function parseSearchQuery(query: string): {
  status: string;
  reputation: string;
  text: string;
} {
  const q = (query || "").trim().toLowerCase();
  if (!q) return { status: FILTER_STATUS_ALL, reputation: FILTER_REP_ALL, text: "" };

  let status = FILTER_STATUS_ALL;
  let reputation = FILTER_REP_ALL;
  let rest = q;

  if (REP_KEYWORDS["non evaluee"] !== undefined && rest.includes("non evaluee")) {
    reputation = "neutral";
    rest = rest.replace(/non\s+evaluee/g, "").trim();
  }
  const words = rest.split(/\s+/).filter(Boolean);
  const remaining: string[] = [];
  for (const w of words) {
    if (STATUS_KEYWORDS[w] !== undefined) {
      status = STATUS_KEYWORDS[w];
      continue;
    }
    if (REP_KEYWORDS[w] !== undefined) {
      reputation = REP_KEYWORDS[w];
      continue;
    }
    remaining.push(w);
  }
  const text = remaining.join(" ").trim();
  return { status, reputation, text };
}

/**
 * Filtre un appel selon la requete texte (numero, operateur, lieu).
 */
function callMatchesText(call: CallWithOsint, text: string): boolean {
  if (!text) return true;
  const t = text.toLowerCase();
  const phone = (call.phone_number ?? "").toLowerCase();
  const operator = (call.osint?.operator ?? "").toLowerCase();
  const region = (call.osint?.region ?? "").toLowerCase();
  const city = (call.osint?.city ?? "").toLowerCase();
  const lieu = [call.osint?.city, call.osint?.region].filter(Boolean).join(" ").toLowerCase();
  return (
    phone.includes(t) ||
    operator.includes(t) ||
    region.includes(t) ||
    city.includes(t) ||
    lieu.includes(t)
  );
}

/**
 * Page liste des appels : chargement cote client pour avoir les vraies donnees
 * quand le front est servi par le backend (export statique).
 */
export default function CallsPage() {
  const [calls, setCalls] = useState<CallWithOsint[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [filterStatus, setFilterStatus] = useState<string>(FILTER_STATUS_ALL);
  const [filterReputation, setFilterReputation] = useState<string>(FILTER_REP_ALL);
  const [searchInput, setSearchInput] = useState("");
  const [filtersOpen, setFiltersOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchCallsWithOsint()
      .then((data) => {
        if (!cancelled) {
          setCalls(data);
          setError(null);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError("Impossible de contacter l'API VocalGuard (assure-toi que le backend tourne).");
          setCalls([]);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const parsed = React.useMemo(() => parseSearchQuery(searchInput), [searchInput]);
  const effectiveStatus = parsed.status !== FILTER_STATUS_ALL ? parsed.status : filterStatus;
  const effectiveRep = parsed.reputation !== FILTER_REP_ALL ? parsed.reputation : filterReputation;

  const filteredCalls = React.useMemo(() => {
    return calls.filter((call) => {
      if (effectiveStatus !== FILTER_STATUS_ALL && getStatusFilterValue(call.status) !== effectiveStatus)
        return false;
      if (effectiveRep !== FILTER_REP_ALL && getReputationCategory(call.osint) !== effectiveRep) return false;
      if (!callMatchesText(call, parsed.text)) return false;
      return true;
    });
  }, [calls, effectiveStatus, effectiveRep, parsed.text]);

  const hasActiveFilters =
    effectiveStatus !== FILTER_STATUS_ALL ||
    effectiveRep !== FILTER_REP_ALL ||
    parsed.text.length > 0;

  const clearAllFilters = () => {
    setSearchInput("");
    setFilterStatus(FILTER_STATUS_ALL);
    setFilterReputation(FILTER_REP_ALL);
  };

  const statusOptions = [
    { value: FILTER_STATUS_ALL, label: "Tous" },
    { value: "answered", label: "Repondu" },
    { value: "missed", label: "Manque" },
    { value: "blocked", label: "Bloque" }
  ];
  const repOptions = [
    { value: FILTER_REP_ALL, label: "Tous" },
    { value: "good", label: "Bonne" },
    { value: "bad", label: "Risque" },
    { value: "neutral", label: "Non evaluee" },
    { value: "unknown", label: "Inconnue" }
  ];

  const activeFilterCount = [
    effectiveStatus !== FILTER_STATUS_ALL,
    effectiveRep !== FILTER_REP_ALL,
    parsed.text.length > 0
  ].filter(Boolean).length;

  const filterBar = (
    <div className="vg-calls-filters" style={{ marginBottom: "1.25rem" }}>
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          gap: "0.5rem"
        }}
      >
        <div
          style={{
            flex: "1 1 200px",
            minWidth: 0,
            position: "relative",
            display: "flex",
            alignItems: "center"
          }}
        >
          <span
            className="material-icons"
            style={{
              position: "absolute",
              left: "0.65rem",
              fontSize: "20px",
              color: "#9ca3af",
              pointerEvents: "none"
            }}
          >
            search
          </span>
          <input
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Rechercher par numero, operateur, lieu ou mot-cle..."
            className="vg-input"
            style={{
              width: "100%",
              padding: "0.5rem 0.75rem 0.5rem 2.25rem",
              borderRadius: "8px",
              border: "1px solid #374151",
              background: "var(--vg-bg-secondary, #1f2937)",
              color: "var(--vg-text, #f9fafb)",
              fontSize: "0.875rem"
            }}
            aria-label="Recherche intelligente"
          />
          {searchInput.length > 0 && (
            <button
              type="button"
              onClick={() => setSearchInput("")}
              style={{
                position: "absolute",
                right: "0.5rem",
                background: "none",
                border: "none",
                color: "#9ca3af",
                cursor: "pointer",
                padding: "0.25rem",
                display: "flex",
                alignItems: "center",
                justifyContent: "center"
              }}
              aria-label="Effacer la recherche"
            >
              <span className="material-icons" style={{ fontSize: "18px" }}>
                close
              </span>
            </button>
          )}
        </div>
        <button
          type="button"
          onClick={() => setFiltersOpen(!filtersOpen)}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "0.4rem",
            padding: "0.5rem 0.75rem",
            fontSize: "0.875rem",
            borderRadius: "8px",
            border: "1px solid #4b5563",
            background: filtersOpen ? "#374151" : "transparent",
            color: "#d1d5db",
            cursor: "pointer",
            position: "relative"
          }}
          aria-expanded={filtersOpen}
          aria-label={filtersOpen ? "Fermer les filtres" : "Ouvrir les filtres avances"}
        >
          <span className="material-icons" style={{ fontSize: "20px" }}>
            filter_list
          </span>
          Filtres avances
          {activeFilterCount > 0 && (
            <span
              style={{
                marginLeft: "0.2rem",
                minWidth: "1.25rem",
                height: "1.25rem",
                padding: "0 0.35rem",
                borderRadius: "999px",
                background: "#6366f1",
                color: "#fff",
                fontSize: "0.75rem",
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center"
              }}
            >
              {activeFilterCount}
            </span>
          )}
        </button>
        {hasActiveFilters && (
          <button
            type="button"
            onClick={clearAllFilters}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "0.35rem",
              padding: "0.5rem 0.65rem",
              fontSize: "0.8125rem",
              borderRadius: "8px",
              border: "1px solid #4b5563",
              background: "transparent",
              color: "#9ca3af",
              cursor: "pointer"
            }}
          >
            <span className="material-icons" style={{ fontSize: "16px" }}>
              filter_alt_off
            </span>
            Tout effacer
          </button>
        )}
      </div>

      {filtersOpen && (
        <div
          style={{
            marginTop: "0.75rem",
            padding: "1rem",
            borderRadius: "8px",
            border: "1px solid #374151",
            background: "var(--vg-bg-secondary, #111827)"
          }}
        >
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "0.75rem" }}>
            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "0.5rem" }}>
              <span style={{ fontSize: "0.8125rem", color: "#9ca3af", marginRight: "0.25rem" }}>Statut</span>
              {statusOptions.map(({ value, label }) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setFilterStatus(value)}
                  style={{
                    cursor: "pointer",
                    border: "1px solid #4b5563",
                    borderRadius: "999px",
                    padding: "0.3rem 0.6rem",
                    fontSize: "0.8125rem",
                    background: effectiveStatus === value ? "#22c55e" : "transparent",
                    color: effectiveStatus === value ? "#fff" : "#d1d5db"
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "0.5rem" }}>
              <span style={{ fontSize: "0.8125rem", color: "#9ca3af", marginRight: "0.25rem" }}>Reputation</span>
              {repOptions.map(({ value, label }) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setFilterReputation(value)}
                  style={{
                    cursor: "pointer",
                    border: "1px solid #4b5563",
                    borderRadius: "999px",
                    padding: "0.3rem 0.6rem",
                    fontSize: "0.8125rem",
                    background: effectiveRep === value ? "#6366f1" : "transparent",
                    color: effectiveRep === value ? "#fff" : "#d1d5db",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "0.3rem"
                  }}
                >
                  {(value === "good" || value === "bad" || value === "neutral" || value === "unknown") && (
                    <span
                      className={`vg-chip-dot vg-chip-dot--${value === "good" ? "good" : value === "bad" ? "bad" : "unknown"}`}
                      style={{ margin: 0, flexShrink: 0 }}
                    />
                  )}
                  {label}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {hasActiveFilters && (
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "0.35rem", marginTop: "0.5rem" }}>
          <span style={{ fontSize: "0.75rem", color: "#6b7280" }}>Filtres actifs :</span>
          {effectiveStatus !== FILTER_STATUS_ALL && (
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "0.25rem",
                padding: "0.2rem 0.45rem",
                borderRadius: "6px",
                fontSize: "0.75rem",
                background: "#374151",
                color: "#d1d5db"
              }}
            >
              Statut {statusOptions.find((o) => o.value === effectiveStatus)?.label}
            </span>
          )}
          {effectiveRep !== FILTER_REP_ALL && (
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "0.25rem",
                padding: "0.2rem 0.45rem",
                borderRadius: "6px",
                fontSize: "0.75rem",
                background: "#374151",
                color: "#d1d5db"
              }}
            >
              Reputation {repOptions.find((o) => o.value === effectiveRep)?.label}
            </span>
          )}
          {parsed.text.length > 0 && (
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "0.25rem",
                padding: "0.2rem 0.45rem",
                borderRadius: "6px",
                fontSize: "0.75rem",
                background: "#374151",
                color: "#d1d5db"
              }}
            >
              &quot;{parsed.text}&quot;
            </span>
          )}
        </div>
      )}
    </div>
  );

  type LiveTag = "screened" | "permitted" | "blocked";

  const [liveCall, setLiveCall] = useState<{
    callId: number;
    phoneNumber: string | null;
    tag: LiveTag;
    eventType: string;
  } | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const wsUrl = `${protocol}://${window.location.host}/ws/events`;
    const ws = new WebSocket(wsUrl);

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data as string) as {
          type?: string;
          data?: { call_id?: number; phone_number?: string | null };
        };
        if (!msg || !msg.type || !msg.data || !msg.data.call_id) return;

        const t = msg.type;
        let tag: LiveTag | null = null;
        if (t === "call.incoming") tag = "screened";
        else if (t === "call.blocked") tag = "blocked";
        else if (t === "call.answered" || t === "call.completed") tag = "permitted";

        if (!tag) return;

        setLiveCall({
          callId: msg.data.call_id,
          phoneNumber: msg.data.phone_number ?? null,
          tag,
          eventType: t
        });

        // Rafraichir la liste des appels pour refleter l'etat courant sans recharger la page
        fetchCallsWithOsint()
          .then((data) => {
            setCalls(data);
          })
          .catch(() => {
            // on garde l'erreur eventuelle geree par l'effet initial
          });
      } catch {
        // Ignorer les messages invalides
      }
    };

    ws.onerror = () => {
      try {
        ws.close();
      } catch {
        // ignore
      }
    };

    return () => {
      try {
        ws.close();
      } catch {
        // ignore
      }
    };
  }, []);

  useEffect(() => {
    if (!liveCall || typeof window === "undefined") return;
    const id = window.setTimeout(() => {
      setLiveCall((current) => {
        if (!current) return null;
        // On garde eventuellement les appels bloques un peu plus longtemps
        if (current.tag === "blocked") return current;
        return null;
      });
    }, 20000);
    return () => {
      window.clearTimeout(id);
    };
  }, [liveCall]);

  function renderLiveTag(tag: LiveTag): React.ReactNode {
    if (tag === "blocked") {
      return <span className="vg-badge vg-badge-danger">Blocked</span>;
    }
    if (tag === "permitted") {
      return <span className="vg-badge vg-badge-success">Permitted</span>;
    }
    return <span className="vg-badge">Screened</span>;
  }

  return (
    <AppLayout
      title="Appels"
      subtitle="Historique des appels traites par VocalGuard, enrichis avec un premier score OSINT."
    >
      {liveCall && (
        <div
          className="vg-card"
          style={{
            marginBottom: "1rem",
            borderColor: liveCall.tag === "blocked" ? "#ef4444" : "#22c55e",
            borderWidth: "1px",
            borderStyle: "solid"
          }}
        >
          <div
            className="vg-card-label"
            style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}
          >
            <span className="material-icons" style={{ color: "#22c55e", fontSize: "20px" }}>
              phone_in_talk
            </span>
            <span>
              {liveCall.tag === "screened"
                ? "Nouvel appel entrant"
                : "Appel mis a jour"}
              {liveCall.phoneNumber ? ` depuis ${liveCall.phoneNumber}` : ""} (ID #
              {liveCall.callId})
            </span>
            {renderLiveTag(liveCall.tag)}
          </div>
        </div>
      )}
      {loading ? (
        <div className="vg-card">
          <div className="vg-card-label" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <span className="material-icons" style={{ color: "#22c55e", fontSize: "18px" }}>
              hourglass_empty
            </span>
            Chargement des appels...
          </div>
        </div>
      ) : error ? (
        <div className="vg-card">
          <div className="vg-card-label" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <span className="material-icons" style={{ color: "#ef4444", fontSize: "18px" }}>
              error_outline
            </span>
            Erreur de chargement des appels
          </div>
          <div style={{ fontSize: "0.9rem", color: "#ef4444" }}>{error}</div>
        </div>
      ) : calls.length === 0 ? (
        <div className="vg-card">
          <div className="vg-card-label" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <span className="material-icons" style={{ color: "#9ca3af", fontSize: "18px" }}>
              contact_phone
            </span>
            Aucun appel encore enregistre
          </div>
          <div style={{ fontSize: "0.9rem", color: "#6b7280", marginTop: "0.25rem" }}>
            Des que le modem et l'API seront en service, les nouveaux appels apparaitront ici avec leur reputation.
          </div>
        </div>
      ) : (
        <div className="vg-card">
          {filterBar}
          <table className="vg-table">
            <thead>
              <tr>
                <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Date</th>
                <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Numero</th>
                <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Statut</th>
                <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Reputation OSINT</th>
                <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Lieu</th>
                <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Operateur</th>
              </tr>
            </thead>
            <tbody>{filteredCalls.map(renderRow)}</tbody>
          </table>
          <div style={{ fontSize: "0.8125rem", color: "#9ca3af", marginTop: "0.5rem" }}>
            {filteredCalls.length === calls.length ? (
              <span>{calls.length} appel{calls.length > 1 ? "s" : ""}</span>
            ) : (
              <span>
                {filteredCalls.length} resultat{filteredCalls.length > 1 ? "s" : ""} sur {calls.length} appels
              </span>
            )}
          </div>
        </div>
      )}
    </AppLayout>
  );
}
