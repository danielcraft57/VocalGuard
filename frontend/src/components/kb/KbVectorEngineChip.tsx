/**
 * Chip statut moteur vectoriel (Qdrant / pgvector / local).
 */

"use client";

import React, { useEffect, useState } from "react";
import { Chip, Tooltip } from "@mui/material";
import StorageIcon from "@mui/icons-material/Storage";
import {
  fetchKbConversationStatus,
  isAbortError,
  type KbConversationStatus
} from "../../services/kbApi";

type Props = {
  /** Intervalle de refresh ms (0 = une seule fois). */
  pollMs?: number;
  /** Compact = petit chip sans points. */
  compact?: boolean;
};

/**
 * Affiche l'etat Qdrant (ou fallback) pour la page KB.
 *
 * @param props Options poll / compact.
 * @returns Chip MUI.
 */
export function KbVectorEngineChip({
  pollMs = 20000,
  compact = false
}: Props): React.ReactElement {
  const [status, setStatus] = useState<KbConversationStatus | null>(null);

  useEffect(() => {
    let cancelled = false;
    let current: AbortController | null = null;

    const reload = () => {
      current?.abort();
      const ac = new AbortController();
      current = ac;
      fetchKbConversationStatus(ac.signal)
        .then((data) => {
          if (!cancelled) setStatus(data);
        })
        .catch((e) => {
          if (isAbortError(e) || cancelled) return;
          setStatus(null);
        });
    };

    reload();
    if (pollMs <= 0) {
      return () => {
        cancelled = true;
        current?.abort();
      };
    }
    const id = window.setInterval(reload, pollMs);
    return () => {
      cancelled = true;
      window.clearInterval(id);
      current?.abort();
    };
  }, [pollMs]);

  if (!status) {
    return (
      <Chip
        size="small"
        icon={<StorageIcon />}
        label="Vecteurs…"
        variant="outlined"
      />
    );
  }

  const engine = (status.vector_engine || "local").toLowerCase();
  const qOk = Boolean(status.qdrant_ok);
  const points = Number(status.qdrant_points || 0);

  let color: "success" | "warning" | "default" | "error" = "default";
  let label = "Local";
  let tip = "Recherche cosine en memoire Python.";

  if (engine === "qdrant" && qOk) {
    color = "success";
    const ptsOut = Number(status.qdrant_points_outbound || 0);
    const coll = status.qdrant_collection || "intents_inbound";
    label = compact
      ? "Qdrant"
      : ptsOut > 0
        ? `Qdrant · in ${points} / out ${ptsOut}`
        : `Qdrant · ${points} pts`;
    tip = `Collections: ${coll}` +
      (status.qdrant_collection_outbound
        ? ` + ${status.qdrant_collection_outbound}`
        : "") +
      (status.qdrant_url ? ` (${status.qdrant_url})` : "");
  } else if (status.qdrant_configured && !qOk) {
    color = "warning";
    label = "Qdrant KO";
    tip = status.qdrant_detail || "Qdrant configure mais injoignable - fallback local.";
  } else if (engine === "pgvector") {
    color = "default";
    label = "pgvector";
    tip = "Recherche via Postgres pgvector.";
  }

  return (
    <Tooltip title={tip}>
      <Chip
        size="small"
        icon={<StorageIcon />}
        color={color}
        label={label}
        variant={color === "default" ? "outlined" : "filled"}
      />
    </Tooltip>
  );
}
