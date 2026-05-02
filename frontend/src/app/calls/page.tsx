"use client";

import React, { useState, useEffect, useRef } from "react";
import { AppLayout } from "../../components/AppLayout";
import { OutgoingCallDialerModal } from "../../components/OutgoingCallDialerModal";
import {
  fetchCallsWithOsint,
  fetchCallWithOsintById,
  CallWithOsint,
  startOutgoingCall,
  sendOutgoingDtmf,
  hangupOutgoingCall,
  patchCallTag,
  queueCallOsint,
  bulkDeleteCalls,
  deleteCall,
  getCallRecordingUrl,
  type CallUiTag
} from "../../services/callsApi";
import { getWsBaseUrl } from "../../services/httpClient";
import { useOutgoingCallAudio } from "../../hooks/useOutgoingCallAudio";

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
type OutgoingStatus = "idle" | "dialing" | "connected" | "ended" | "error";

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

function readUiTagFromCall(call: CallWithOsint): CallUiTag {
  const ex = call.extra_data;
  if (ex && typeof ex === "object" && "ui_tag" in ex) {
    const v = String((ex as { ui_tag?: string }).ui_tag || "").toLowerCase();
    const allowed: CallUiTag[] = ["permitted", "restricted", "unknown", "blocked", "commercial", "none"];
    if (allowed.includes(v as CallUiTag)) return v as CallUiTag;
  }
  return "none";
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
  const [dialerOpen, setDialerOpen] = useState(false);
  const [dialerNumber, setDialerNumber] = useState("");
  const [dialerCallId, setDialerCallId] = useState<number | null>(null);
  const [dialerStatus, setDialerStatus] = useState<OutgoingStatus>("idle");
  const [dialerError, setDialerError] = useState<string | null>(null);
  const [dialerTranscriptConfirmed, setDialerTranscriptConfirmed] = useState("");
  const [dialerTranscriptLive, setDialerTranscriptLive] = useState("");
  const [dialerLoading, setDialerLoading] = useState(false);
  const [dialerLogs, setDialerLogs] = useState<{ t: string; level: string; message: string }[]>([]);
  const [liveListen, setLiveListen] = useState(true);
  const [liveMic, setLiveMic] = useState(false);
  const [detailCall, setDetailCall] = useState<CallWithOsint | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const dialerLogsEndRef = useRef<HTMLDivElement | null>(null);
  const dialerCallIdRef = useRef<number | null>(null);
  dialerCallIdRef.current = dialerCallId;

  const audioActive = dialerCallId !== null && (dialerStatus === "dialing" || dialerStatus === "connected");
  useOutgoingCallAudio(dialerCallId, audioActive && liveListen, audioActive && liveMic);

  useEffect(() => {
    if (!dialerOpen) return;
    const id = requestAnimationFrame(() => {
      dialerLogsEndRef.current?.scrollIntoView({ block: "nearest" });
    });
    return () => cancelAnimationFrame(id);
  }, [dialerLogs, dialerOpen]);

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

  const canSendDtmf = dialerCallId !== null && (dialerStatus === "dialing" || dialerStatus === "connected");

  const handleStartDial = async () => {
    setDialerError(null);
    const num = dialerNumber.trim();
    if (!num) {
      setDialerError("Saisissez un numero");
      return;
    }
    setDialerLoading(true);
    try {
      const result = await startOutgoingCall(num);
      dialerCallIdRef.current = result.call_id;
      setDialerCallId(result.call_id);
      setDialerStatus("dialing");
      setDialerTranscriptConfirmed("");
      setDialerTranscriptLive("");
      setDialerLogs([]);
      setLiveListen(true);
      setLiveMic(false);
    } catch (e) {
      setDialerStatus("error");
      setDialerError(e instanceof Error ? e.message : "Impossible de demarrer l'appel sortant");
    } finally {
      setDialerLoading(false);
    }
  };

  const handleHangup = async () => {
    if (dialerCallId === null) return;
    setDialerLoading(true);
    try {
      await hangupOutgoingCall(dialerCallId);
      setDialerStatus("ended");
      fetchCallsWithOsint().then(setCalls).catch(() => undefined);
    } catch {
      setDialerError("Echec du raccrochage");
    } finally {
      setDialerLoading(false);
    }
  };

  /** Fermeture modale : raccroche tout appel actif puis reinitialise l'etat local. */
  const handleCloseDialer = async () => {
    const id = dialerCallIdRef.current;
    if (id != null) {
      try {
        await hangupOutgoingCall(id);
        fetchCallsWithOsint().then(setCalls).catch(() => undefined);
      } catch {
        /* session deja terminee cote serveur : on ferme quand meme */
      }
    }
    dialerCallIdRef.current = null;
    setDialerCallId(null);
    setDialerStatus("idle");
    setDialerTranscriptConfirmed("");
    setDialerTranscriptLive("");
    setDialerLogs([]);
    setDialerError(null);
    setDialerOpen(false);
  };

  const handleSendDtmf = async (digit: string) => {
    if (!canSendDtmf || dialerCallId === null) return;
    try {
      await sendOutgoingDtmf(dialerCallId, digit);
    } catch {
      setDialerError(`DTMF ${digit} refuse par le modem`);
    }
  };

  const handleKeypadDigit = (digit: string) => {
    if (canSendDtmf && dialerCallId !== null) {
      void handleSendDtmf(digit);
      return;
    }
    if (dialerStatus === "idle" || dialerStatus === "ended" || dialerStatus === "error") {
      setDialerNumber((prev) => (prev + digit).slice(0, 28));
    }
  };

  const handleRowTag = async (callId: number, tag: CallUiTag) => {
    try {
      await patchCallTag(callId, tag);
      const data = await fetchCallsWithOsint();
      setCalls(data);
    } catch {
      setError("Impossible de mettre a jour le tag");
    }
  };

  const handleRowOsint = async (callId: number) => {
    try {
      await queueCallOsint(callId);
      const data = await fetchCallsWithOsint();
      setCalls(data);
    } catch {
      setError("Impossible de lancer l'OSINT");
    }
  };

  const openDialerWith = (num: string) => {
    setDialerNumber(num);
    setDialerOpen(true);
    dialerCallIdRef.current = null;
    setDialerCallId(null);
    setDialerStatus("idle");
    setDialerTranscriptConfirmed("");
    setDialerTranscriptLive("");
    setDialerLogs([]);
    setDialerError(null);
  };

  const openCallDetail = async (callId: number) => {
    setDetailLoading(true);
    setDetailCall(null);
    try {
      const c = await fetchCallWithOsintById(callId);
      setDetailCall(c);
    } catch {
      setError("Impossible de charger le detail de l appel");
    } finally {
      setDetailLoading(false);
    }
  };

  const handleDeleteDetailCall = async () => {
    if (!detailCall) return;
    if (!window.confirm("Supprimer cet appel et son enregistrement ?")) return;
    try {
      await deleteCall(detailCall.id);
      setDetailCall(null);
      setSelectedIds((s) => {
        const n = new Set(s);
        n.delete(detailCall.id);
        return n;
      });
      const data = await fetchCallsWithOsint();
      setCalls(data);
    } catch {
      setError("Echec de la suppression");
    }
  };

  const allFilteredSelected =
    filteredCalls.length > 0 && filteredCalls.every((c) => selectedIds.has(c.id));

  const toggleSelectAllFiltered = () => {
    if (allFilteredSelected) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(filteredCalls.map((c) => c.id)));
    }
  };

  const handleBulkDelete = async () => {
    if (selectedIds.size === 0) return;
    if (!window.confirm(`Supprimer ${selectedIds.size} appel(s) ?`)) return;
    try {
      const ids = [...selectedIds];
      await bulkDeleteCalls(ids);
      setSelectedIds(new Set());
      setDetailCall((d) => (d && ids.includes(d.id) ? null : d));
      const data = await fetchCallsWithOsint();
      setCalls(data);
    } catch {
      setError("Echec de la suppression groupée");
    }
  };

  const renderCallRow = (call: CallWithOsint): React.ReactNode => {
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
    const uiTag = readUiTagFromCall(call);

    return (
      <tr
        key={call.id}
        style={{ transition: "background-color 150ms ease-out" }}
        className="vg-table-row"
      >
        <td style={{ padding: "0.5rem 0.35rem", width: "2rem" }}>
          <input
            type="checkbox"
            checked={selectedIds.has(call.id)}
            onChange={() =>
              setSelectedIds((s) => {
                const n = new Set(s);
                if (n.has(call.id)) n.delete(call.id);
                else n.add(call.id);
                return n;
              })
            }
            aria-label={`Selectionner appel ${call.id}`}
          />
        </td>
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
                maxWidth: "12rem",
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
        <td style={{ padding: "0.5rem 0.75rem", minWidth: "7rem" }}>
          <select
            value={uiTag}
            onChange={(e) => void handleRowTag(call.id, e.target.value as CallUiTag)}
            className="vg-input"
            style={{ fontSize: "0.75rem", padding: "0.25rem", maxWidth: "100%" }}
            aria-label="Tag appel"
          >
            <option value="none">Tag...</option>
            <option value="permitted">Permis</option>
            <option value="restricted">Restreint</option>
            <option value="unknown">Inconnu</option>
            <option value="blocked">Bloque</option>
            <option value="commercial">Commercial</option>
          </select>
        </td>
        <td style={{ padding: "0.5rem 0.75rem" }}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem" }}>
            {call.phone_number && (
              <button
                type="button"
                title="Rappeler"
                onClick={() => openDialerWith(call.phone_number!)}
                style={{
                  border: "1px solid #4b5563",
                  background: "#1f2937",
                  color: "#e5e7eb",
                  borderRadius: "8px",
                  padding: "0.25rem 0.45rem",
                  cursor: "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "0.2rem",
                  fontSize: "0.7rem"
                }}
              >
                <span className="material-icons" style={{ fontSize: "14px" }}>
                  phone_callback
                </span>
              </button>
            )}
            <button
              type="button"
              title="File OSINT"
              onClick={() => void handleRowOsint(call.id)}
              style={{
                border: "1px solid #6366f1",
                background: "transparent",
                color: "#a5b4fc",
                borderRadius: "8px",
                padding: "0.25rem 0.45rem",
                cursor: "pointer",
                fontSize: "0.7rem"
              }}
            >
              OSINT
            </button>
            <button
              type="button"
              title="Detail"
              onClick={() => void openCallDetail(call.id)}
              style={{
                border: "1px solid #22c55e",
                background: "transparent",
                color: "#86efac",
                borderRadius: "8px",
                padding: "0.25rem 0.45rem",
                cursor: "pointer",
                fontSize: "0.7rem"
              }}
            >
              Detail
            </button>
          </div>
        </td>
      </tr>
    );
  };

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
    const wsUrl = `${getWsBaseUrl()}/ws/events`;
    const ws = new WebSocket(wsUrl);

    const dispose = () => {
      ws.onmessage = null;
      ws.onerror = null;
      try {
        if (ws.readyState === WebSocket.OPEN) {
          ws.close();
        } else if (ws.readyState === WebSocket.CONNECTING) {
          // En dev (React Strict Mode), le cleanup peut arriver avant OPEN : eviter ws.close()
          // immediat (bruit console "closed before the connection is established").
          let tid: ReturnType<typeof window.setTimeout> | undefined;
          const finish = () => {
            if (tid !== undefined) window.clearTimeout(tid);
            try {
              if (ws.readyState !== WebSocket.CLOSED) ws.close();
            } catch {
              /* ignore */
            }
          };
          ws.addEventListener("open", finish, { once: true });
          ws.addEventListener("error", finish, { once: true });
          tid = window.setTimeout(finish, 15_000);
        }
      } catch {
        /* ignore */
      }
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data as string) as {
          type?: string;
          data?: {
            call_id?: number;
            phone_number?: string | null;
            text?: string;
            live?: boolean;
            message?: string;
            level?: string;
          };
        };
        if (!msg || !msg.type || !msg.data || !msg.data.call_id) return;

        const activeDialerId = dialerCallIdRef.current;
        if (activeDialerId && msg.data.call_id === activeDialerId) {
          if (msg.type === "call.outgoing.dialing") {
            setDialerStatus("dialing");
          } else if (msg.type === "call.outgoing.connected") {
            setDialerStatus("connected");
          } else if (msg.type === "call.outgoing.ended") {
            setDialerStatus("ended");
            fetchCallsWithOsint().then(setCalls).catch(() => undefined);
          } else if (msg.type === "call.transcription.partial" && msg.data.text != null) {
            const piece = String(msg.data.text);
            if (msg.data.live === true) {
              setDialerTranscriptLive(piece);
            } else {
              const trimmed = piece.trim();
              if (trimmed) {
                setDialerTranscriptLive("");
                setDialerTranscriptConfirmed((prev) => (prev ? `${prev} ${trimmed}` : trimmed));
              }
            }
          } else if (msg.type === "call.transcription.final" && msg.data.text) {
            setDialerTranscriptLive("");
            setDialerTranscriptConfirmed(String(msg.data.text));
          } else if (msg.type === "call.session.log" && msg.data?.message) {
            const logMsg = String(msg.data.message);
            const logLevel = msg.data.level || "info";
            setDialerLogs((prev) =>
              [
                ...prev.slice(-250),
                {
                  t: new Date().toLocaleTimeString("fr-FR"),
                  level: logLevel,
                  message: logMsg
                }
              ]
            );
          }
        }

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
        if (ws.readyState === WebSocket.OPEN) ws.close();
      } catch {
        // ignore
      }
    };

    return () => {
      dispose();
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
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: "1rem" }}>
        <button
          type="button"
          onClick={() => {
            setDialerOpen(true);
            if (dialerStatus !== "dialing" && dialerStatus !== "connected") {
              dialerCallIdRef.current = null;
              setDialerCallId(null);
              setDialerStatus("idle");
              setDialerTranscriptConfirmed("");
              setDialerTranscriptLive("");
              setDialerLogs([]);
              setDialerError(null);
            }
          }}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "0.45rem",
            border: "none",
            borderRadius: "10px",
            padding: "0.6rem 0.95rem",
            cursor: "pointer",
            background: "#2563eb",
            color: "#fff",
            fontWeight: 600
          }}
        >
          <span className="material-icons" style={{ fontSize: "18px" }}>
            dialpad
          </span>
          Composer
        </button>
      </div>
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
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              alignItems: "center",
              gap: "0.5rem",
              marginBottom: "0.65rem"
            }}
          >
            <button
              type="button"
              onClick={toggleSelectAllFiltered}
              className="vg-input"
              style={{ fontSize: "0.8rem", padding: "0.35rem 0.65rem", cursor: "pointer" }}
            >
              {allFilteredSelected ? "Tout deselectionner" : "Tout selectionner (filtre)"}
            </button>
            <button
              type="button"
              disabled={selectedIds.size === 0}
              onClick={() => void handleBulkDelete()}
              style={{
                fontSize: "0.8rem",
                padding: "0.35rem 0.65rem",
                cursor: selectedIds.size === 0 ? "not-allowed" : "pointer",
                borderRadius: "8px",
                border: "1px solid #b91c1c",
                background: selectedIds.size === 0 ? "#374151" : "#7f1d1d",
                color: "#fecaca",
                opacity: selectedIds.size === 0 ? 0.5 : 1
              }}
            >
              Supprimer la selection ({selectedIds.size})
            </button>
          </div>
          <table className="vg-table">
            <thead>
              <tr>
                <th
                  style={{ textAlign: "left", padding: "0.5rem 0.35rem", width: "2rem", fontSize: "0.65rem", color: "#6b7280" }}
                >
                  Sel.
                </th>
                <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Date</th>
                <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Numero</th>
                <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Statut</th>
                <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Reputation OSINT</th>
                <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Lieu</th>
                <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Operateur</th>
                <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Tag</th>
                <th style={{ textAlign: "left", padding: "0.5rem 0.75rem" }}>Actions</th>
              </tr>
            </thead>
            <tbody>{filteredCalls.map(renderCallRow)}</tbody>
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
      <OutgoingCallDialerModal
        open={dialerOpen}
        onClose={() => void handleCloseDialer()}
        dialerNumber={dialerNumber}
        setDialerNumber={setDialerNumber}
        dialerStatus={dialerStatus}
        dialerCallId={dialerCallId}
        dialerError={dialerError}
        dialerLoading={dialerLoading}
        liveListen={liveListen}
        setLiveListen={setLiveListen}
        liveMic={liveMic}
        setLiveMic={setLiveMic}
        audioActive={audioActive}
        dialerLogs={dialerLogs}
        dialerLogsEndRef={dialerLogsEndRef}
        dialerTranscriptConfirmed={dialerTranscriptConfirmed}
        dialerTranscriptLive={dialerTranscriptLive}
        canSendDtmf={canSendDtmf}
        onStartDial={() => void handleStartDial()}
        onHangup={() => void handleHangup()}
        onKeypadDigit={handleKeypadDigit}
      />

      {(detailCall !== null || detailLoading) && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 1100,
            background: "rgba(0,0,0,0.65)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "1rem"
          }}
          role="dialog"
          aria-modal="true"
          aria-label="Detail appel"
          onClick={() => !detailLoading && setDetailCall(null)}
        >
          <div
            className="vg-card"
            style={{
              maxWidth: 560,
              width: "100%",
              maxHeight: "90vh",
              overflow: "auto",
              border: "1px solid #374151",
              padding: "1.25rem"
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {detailLoading ? (
              <div style={{ color: "#9ca3af", fontSize: "0.9rem" }}>Chargement...</div>
            ) : detailCall ? (
              <>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.75rem" }}>
                  <div>
                    <h2 style={{ margin: "0 0 0.25rem", fontSize: "1.15rem", color: "#f9fafb" }}>
                      Appel #{detailCall.id}
                    </h2>
                    <div style={{ fontSize: "0.85rem", color: "#9ca3af" }}>
                      {detailCall.phone_number ?? "Numero inconnu"}
                      {detailCall.caller_name ? ` · ${detailCall.caller_name}` : ""}
                    </div>
                    <div style={{ fontSize: "0.78rem", color: "#6b7280", marginTop: "0.35rem" }}>
                      {new Date(detailCall.call_time).toLocaleString("fr-FR")} · statut {detailCall.status}
                      {detailCall.duration != null ? ` · ${detailCall.duration}s` : ""}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setDetailCall(null)}
                    style={{ border: "none", background: "transparent", color: "#9ca3af", cursor: "pointer" }}
                    aria-label="Fermer"
                  >
                    <span className="material-icons">close</span>
                  </button>
                </div>

                <div style={{ marginTop: "1rem" }}>
                  <div style={{ fontSize: "0.72rem", color: "#64748b", textTransform: "uppercase", marginBottom: "0.35rem" }}>
                    Enregistrement
                  </div>
                  {detailCall.audio_file ? (
                    <audio
                      controls
                      src={getCallRecordingUrl(detailCall.id)}
                      style={{ width: "100%", maxHeight: "48px" }}
                      preload="metadata"
                    />
                  ) : (
                    <p style={{ margin: 0, fontSize: "0.85rem", color: "#6b7280" }}>Aucun fichier audio pour cet appel.</p>
                  )}
                </div>

                <div style={{ marginTop: "1rem" }}>
                  <div style={{ fontSize: "0.72rem", color: "#64748b", textTransform: "uppercase", marginBottom: "0.35rem" }}>
                    Transcription
                  </div>
                  <div
                    style={{
                      whiteSpace: "pre-wrap",
                      fontSize: "0.88rem",
                      color: "#e5e7eb",
                      background: "#111827",
                      borderRadius: "8px",
                      padding: "0.65rem",
                      border: "1px solid #374151",
                      minHeight: "3rem"
                    }}
                  >
                    {detailCall.transcription?.trim() || "—"}
                  </div>
                </div>

                <div style={{ marginTop: "1rem" }}>
                  <div style={{ fontSize: "0.72rem", color: "#64748b", textTransform: "uppercase", marginBottom: "0.35rem" }}>
                    OSINT (base)
                  </div>
                  {detailCall.osint ? (
                    <ul style={{ margin: 0, paddingLeft: "1.1rem", fontSize: "0.85rem", color: "#d1d5db", lineHeight: 1.5 }}>
                      <li>Reputation: {detailCall.osint.recommendation} / {detailCall.osint.reputation}</li>
                      <li>Operateur: {detailCall.osint.operator ?? "—"}</li>
                      <li>Lieu: {[detailCall.osint.city, detailCall.osint.region].filter(Boolean).join(", ") || "—"}</li>
                      <li>
                        Flags: spam {detailCall.osint.is_spam ? "oui" : "non"}, arnaque {detailCall.osint.is_scam ? "oui" : "non"},
                        demarchage: {detailCall.osint.is_telemarketer ? "oui" : "non"}
                      </li>
                    </ul>
                  ) : (
                    <p style={{ margin: 0, fontSize: "0.85rem", color: "#6b7280" }}>Pas de profil OSINT en base.</p>
                  )}
                  <button
                    type="button"
                    onClick={() => void handleRowOsint(detailCall.id)}
                    style={{
                      marginTop: "0.5rem",
                      fontSize: "0.78rem",
                      padding: "0.35rem 0.65rem",
                      borderRadius: "8px",
                      border: "1px solid #6366f1",
                      background: "transparent",
                      color: "#a5b4fc",
                      cursor: "pointer"
                    }}
                  >
                    Rafraichir OSINT (file)
                  </button>
                </div>

                <div style={{ display: "flex", gap: "0.5rem", marginTop: "1.25rem", flexWrap: "wrap" }}>
                  <button
                    type="button"
                    onClick={() => void handleDeleteDetailCall()}
                    style={{
                      fontSize: "0.82rem",
                      padding: "0.45rem 0.75rem",
                      borderRadius: "8px",
                      border: "1px solid #b91c1c",
                      background: "#7f1d1d",
                      color: "#fecaca",
                      cursor: "pointer"
                    }}
                  >
                    Supprimer cet appel
                  </button>
                  <button
                    type="button"
                    onClick={() => setDetailCall(null)}
                    style={{
                      fontSize: "0.82rem",
                      padding: "0.45rem 0.75rem",
                      borderRadius: "8px",
                      border: "1px solid #4b5563",
                      background: "transparent",
                      color: "#d1d5db",
                      cursor: "pointer"
                    }}
                  >
                    Fermer
                  </button>
                </div>
              </>
            ) : null}
          </div>
        </div>
      )}
    </AppLayout>
  );
}
