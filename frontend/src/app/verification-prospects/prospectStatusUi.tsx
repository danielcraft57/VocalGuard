import React from "react";
import CheckCircleOutlinedIcon from "@mui/icons-material/CheckCircleOutlined";
import ErrorOutlinedIcon from "@mui/icons-material/ErrorOutlined";
import HourglassEmptyIcon from "@mui/icons-material/HourglassEmpty";
import ManageSearchIcon from "@mui/icons-material/ManageSearch";
import QueueIcon from "@mui/icons-material/Queue";
import StorefrontOutlinedIcon from "@mui/icons-material/StorefrontOutlined";
import BlockIcon from "@mui/icons-material/Block";
import HelpOutlinedIcon from "@mui/icons-material/HelpOutlined";
import FactCheckOutlinedIcon from "@mui/icons-material/FactCheckOutlined";
import { Chip, ChipProps } from "@mui/material";

export const OSINT_STATUS_LABELS: Record<string, string> = {
  pending: "OSINT en attente",
  queued: "OSINT en file",
  done: "OSINT OK",
  failed: "OSINT echec",
  skipped: "OSINT ignore",
};

export const PROSPECTLAB_STATUS_LABELS: Record<string, string> = {
  pending: "ProspectLab…",
  matched: "ProspectLab OK",
  not_found: "ProspectLab vide",
  skipped: "ProspectLab ignore",
};

export const MATCH_STATUS_LABELS: Record<string, string> = {
  match: "Nom OK",
  partial: "Nom proche",
  mismatch: "Nom different",
  unknown: "Nom inconnu",
};

const OSINT_COLORS: Record<string, ChipProps["color"]> = {
  done: "success",
  queued: "info",
  pending: "default",
  failed: "error",
  skipped: "warning",
};

function osintIcon(status: string): React.ReactElement | undefined {
  if (status === "done") return <CheckCircleOutlinedIcon />;
  if (status === "failed") return <ErrorOutlinedIcon />;
  if (status === "queued") return <QueueIcon />;
  if (status === "pending") return <HourglassEmptyIcon />;
  if (status === "skipped") return <BlockIcon />;
  return <ManageSearchIcon />;
}

function plIcon(status: string): React.ReactElement | undefined {
  if (status === "matched") return <StorefrontOutlinedIcon />;
  if (status === "not_found") return <HelpOutlinedIcon />;
  if (status === "pending") return <HourglassEmptyIcon />;
  if (status === "skipped") return <BlockIcon />;
  return <StorefrontOutlinedIcon />;
}

/**
 * Chip OSINT avec libelle francais et icone.
 */
export function OsintStatusChip(props: { status: string; sx?: ChipProps["sx"] }): React.ReactElement {
  const st = props.status || "pending";
  return (
    <Chip
      size="small"
      icon={osintIcon(st)}
      label={OSINT_STATUS_LABELS[st] ?? st}
      color={OSINT_COLORS[st] ?? "default"}
      variant={st === "done" ? "filled" : "outlined"}
      sx={{ height: 24, ...props.sx }}
    />
  );
}

/**
 * Chip ProspectLab avec libelle francais et icone.
 */
export function ProspectLabStatusChip(props: { status: string; sx?: ChipProps["sx"] }): React.ReactElement {
  const st = props.status || "pending";
  return (
    <Chip
      size="small"
      icon={plIcon(st)}
      label={PROSPECTLAB_STATUS_LABELS[st] ?? st}
      color={st === "matched" ? "success" : "default"}
      variant={st === "matched" ? "filled" : "outlined"}
      sx={{ height: 24, ...props.sx }}
    />
  );
}

/**
 * Chip correspondance de nom (match OSINT / Excel).
 */
export function NameMatchChip(props: { status?: string | null }): React.ReactElement | null {
  if (!props.status) return null;
  const colors: Record<string, ChipProps["color"]> = {
    match: "success",
    partial: "warning",
    mismatch: "error",
  };
  return (
    <Chip
      size="small"
      icon={<FactCheckOutlinedIcon />}
      label={MATCH_STATUS_LABELS[props.status] ?? props.status}
      color={colors[props.status] ?? "default"}
      variant="outlined"
      sx={{ height: 24 }}
    />
  );
}
