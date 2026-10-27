import React, { useMemo, useState } from "react";
import Link from "next/link";
import PhoneOutlinedIcon from "@mui/icons-material/PhoneOutlined";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import DeleteOutlinedIcon from "@mui/icons-material/DeleteOutlined";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import StarOutlinedIcon from "@mui/icons-material/StarOutlined";
import PlaceOutlinedIcon from "@mui/icons-material/PlaceOutlined";
import {
  Box,
  Chip,
  IconButton,
  MenuItem,
  Paper,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TableSortLabel,
  Tooltip,
  Typography,
} from "@mui/material";
import type { ProspectPhone, ProspectPhoneVerificationStatus } from "../../../services/prospectPhonesApi";
import { prospectDisplayCity } from "../prospectDisplayUtils";
import {
  NameMatchChip,
  OsintStatusChip,
  ProspectLabStatusChip,
} from "../prospectStatusUi";

type SortKey = "name" | "rating" | "reviews_count" | "city";

const cardSx = {
  borderRadius: 2.5,
  border: "1px solid var(--vg-color-border-subtle)",
  bgcolor: "var(--vg-color-bg)",
  transition: "border-color .2s ease, box-shadow .2s ease",
};

/**
 * Tableau et cartes prospects avec ville lisible (pas le nom de fichier).
 */
export function VerificationProspectsTable(props: {
  rows: ProspectPhone[];
  statusLabels: Record<ProspectPhoneVerificationStatus, string>;
  onStatusChange: (row: ProspectPhone, status: ProspectPhoneVerificationStatus) => void;
  onEdit: (row: ProspectPhone) => void;
  onDelete: (row: ProspectPhone) => void;
  onViewDetail: (row: ProspectPhone) => void;
  enrichingProspectId?: number | null;
}) {
  const [sortKey, setSortKey] = useState<SortKey>("name");
  const [sortAsc, setSortAsc] = useState(true);

  const sorted = useMemo(() => {
    const copy = [...props.rows];
    copy.sort((a, b) => {
      let av: string | number | null | undefined;
      let bv: string | number | null | undefined;
      if (sortKey === "city") {
        av = prospectDisplayCity(a);
        bv = prospectDisplayCity(b);
      } else {
        av = a[sortKey];
        bv = b[sortKey];
      }
      if (typeof av === "number" && typeof bv === "number") {
        return sortAsc ? av - bv : bv - av;
      }
      const sa = String(av ?? "").toLowerCase();
      const sb = String(bv ?? "").toLowerCase();
      if (sa < sb) return sortAsc ? -1 : 1;
      if (sa > sb) return sortAsc ? 1 : -1;
      return 0;
    });
    return copy;
  }, [props.rows, sortKey, sortAsc]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortAsc(!sortAsc);
    else {
      setSortKey(key);
      setSortAsc(true);
    }
  };

  const rowActions = (row: ProspectPhone) => (
    <Stack direction="row" spacing={0}>
      <Tooltip title="Fiche complete">
        <IconButton size="small" aria-label="Voir le detail" onClick={() => props.onViewDetail(row)}>
          <InfoOutlinedIcon fontSize="small" />
        </IconButton>
      </Tooltip>
      <Tooltip title="Modifier">
        <IconButton size="small" aria-label="Modifier" onClick={() => props.onEdit(row)}>
          <EditOutlinedIcon fontSize="small" />
        </IconButton>
      </Tooltip>
      <Tooltip title="Supprimer">
        <IconButton size="small" aria-label="Supprimer" onClick={() => props.onDelete(row)}>
          <DeleteOutlinedIcon fontSize="small" />
        </IconButton>
      </Tooltip>
    </Stack>
  );

  const statusSelect = (row: ProspectPhone) => (
    <Select
      size="small"
      fullWidth
      value={row.verification_status}
      onChange={(e) => props.onStatusChange(row, e.target.value as ProspectPhoneVerificationStatus)}
      sx={{
        borderRadius: 2,
        bgcolor: "var(--vg-color-surface)",
        fontSize: 13,
      }}
    >
      {(Object.keys(props.statusLabels) as ProspectPhoneVerificationStatus[]).map((s) => (
        <MenuItem key={s} value={s}>{props.statusLabels[s]}</MenuItem>
      ))}
    </Select>
  );

  const cityChip = (row: ProspectPhone) => {
    const label = prospectDisplayCity(row);
    if (label === "—") return null;
    return (
      <Chip
        size="small"
        icon={<PlaceOutlinedIcon />}
        label={label}
        variant="outlined"
        sx={{ height: 24, maxWidth: 140, "& .MuiChip-label": { overflow: "hidden", textOverflow: "ellipsis" } }}
      />
    );
  };

  return (
    <>
      <Stack spacing={1.25} sx={{ display: { xs: "flex", md: "none" } }}>
        {sorted.length === 0 ? (
          <Box sx={{ py: 4, textAlign: "center" }}>
            <Typography variant="subtitle2">Rien a afficher</Typography>
            <Typography variant="body2" color="text.secondary">Importe un Excel ou elargis les filtres.</Typography>
          </Box>
        ) : null}
        {sorted.map((row) => {
          const enriching = props.enrichingProspectId === row.id;
          return (
            <Paper
              key={row.id}
              elevation={0}
              sx={{
                ...cardSx,
                p: 1.5,
                borderColor: enriching ? "var(--vg-color-primary)" : cardSx.border,
                boxShadow: enriching ? "0 0 0 1px var(--vg-color-primary-soft)" : "none",
              }}
            >
              <Stack direction="row" sx={{ alignItems: "flex-start", justifyContent: "space-between", gap: 1 }}>
                <Box sx={{ minWidth: 0, flex: 1 }}>
                  <Stack direction="row" spacing={0.75} sx={{ alignItems: "center", flexWrap: "wrap", gap: 0.5, mb: 0.4 }}>
                    {cityChip(row)}
                    {row.rating != null ? (
                      <Chip
                        size="small"
                        icon={<StarOutlinedIcon />}
                        label={row.rating.toFixed(1)}
                        sx={{ height: 24, fontWeight: 700 }}
                      />
                    ) : null}
                  </Stack>
                  <Typography
                    variant="subtitle1"
                    sx={{ fontWeight: 750, lineHeight: 1.25, cursor: "pointer" }}
                    onClick={() => props.onViewDetail(row)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => { if (e.key === "Enter") props.onViewDetail(row); }}
                  >
                    {row.name}
                  </Typography>
                </Box>
                {rowActions(row)}
              </Stack>

              <Stack
                direction="row"
                sx={{
                  mt: 1.25,
                  py: 0.75,
                  px: 1,
                  borderRadius: 2,
                  bgcolor: "var(--vg-color-surface)",
                  alignItems: "center",
                  justifyContent: "space-between",
                }}
              >
                <Typography
                  component="a"
                  href={row.phone_number ? `tel:${row.phone_number.replace(/\s/g, "")}` : undefined}
                  variant="body1"
                  sx={{ fontWeight: 700, fontVariantNumeric: "tabular-nums", textDecoration: "none", color: "inherit" }}
                >
                  {row.phone_number ?? "—"}
                </Typography>
                <IconButton
                  size="small"
                  component={Link}
                  href="/calls"
                  aria-label="Appeler"
                  sx={{ bgcolor: "var(--vg-color-primary-soft)" }}
                >
                  <PhoneOutlinedIcon fontSize="small" />
                </IconButton>
              </Stack>

              <Stack direction="row" sx={{ mt: 1, flexWrap: "wrap", gap: 0.5 }}>
                {(row.categories?.slice(0, 2) ?? []).map((c) => (
                  <Chip key={c} size="small" label={c} variant="outlined" color="primary" sx={{ height: 22 }} />
                ))}
                <OsintStatusChip status={row.osint_status} />
                <ProspectLabStatusChip status={row.prospectlab_status} />
                <NameMatchChip status={row.name_match_status} />
              </Stack>
              <Box sx={{ mt: 1.25 }}>{statusSelect(row)}</Box>
            </Paper>
          );
        })}
      </Stack>

      <TableContainer
        component={Paper}
        elevation={0}
        sx={{
          display: { xs: "none", md: "block" },
          borderRadius: 3,
          maxHeight: 720,
          border: "1px solid var(--vg-color-border-subtle)",
          bgcolor: "var(--vg-color-surface)",
          overflow: "hidden",
        }}
      >
        <Table stickyHeader size="small">
          <TableHead>
            <TableRow>
              {[
                { key: "name" as const, label: "Entreprise" },
                { key: "city" as const, label: "Ville" },
                { key: null, label: "Telephone" },
                { key: "rating" as const, label: "Note" },
                { key: null, label: "Enrichissement" },
                { key: null, label: "Verification" },
                { key: null, label: "" },
              ].map((col) => (
                <TableCell
                  key={col.label || "actions"}
                  sx={{
                    bgcolor: "var(--vg-color-bg)",
                    fontWeight: 700,
                    borderBottom: "1px solid var(--vg-color-border-subtle)",
                    py: 1.2,
                  }}
                >
                  {col.key ? (
                    <TableSortLabel
                      active={sortKey === col.key}
                      direction={sortAsc ? "asc" : "desc"}
                      onClick={() => toggleSort(col.key as SortKey)}
                    >
                      {col.label}
                    </TableSortLabel>
                  ) : (
                    col.label
                  )}
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {sorted.map((row, index) => (
              <TableRow
                key={row.id}
                hover
                sx={{
                  animation: "vgRowIn 280ms ease both",
                  animationDelay: `${Math.min(index, 12) * 28}ms`,
                  "@keyframes vgRowIn": {
                    from: { opacity: 0, transform: "translateY(6px)" },
                    to: { opacity: 1, transform: "none" },
                  },
                  bgcolor: index % 2 === 0 ? "transparent" : "rgba(15, 23, 42, 0.02)",
                  outline: props.enrichingProspectId === row.id ? "2px solid var(--vg-color-primary-soft)" : "none",
                  "&:hover": { bgcolor: "var(--vg-color-primary-soft)" },
                }}
              >
                <TableCell sx={{ maxWidth: 240 }}>
                  <Typography
                    variant="body2"
                    sx={{ fontWeight: 700, cursor: "pointer", lineHeight: 1.3, "&:hover": { textDecoration: "underline" } }}
                    onClick={() => props.onViewDetail(row)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => { if (e.key === "Enter") props.onViewDetail(row); }}
                  >
                    {row.name}
                  </Typography>
                  <Stack direction="row" spacing={0.5} sx={{ flexWrap: "wrap", mt: 0.5, gap: 0.35 }}>
                    {(row.categories?.slice(0, 2) ?? []).map((c) => (
                      <Chip key={c} size="small" label={c} variant="outlined" sx={{ height: 20, fontSize: 11 }} />
                    ))}
                  </Stack>
                  {row.address_1 ? (
                    <Typography variant="caption" color="text.secondary" component="div" noWrap sx={{ mt: 0.4, maxWidth: 220 }}>
                      {row.address_1}
                    </Typography>
                  ) : null}
                </TableCell>
                <TableCell sx={{ whiteSpace: "nowrap" }}>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    {prospectDisplayCity(row)}
                  </Typography>
                  {row.postal_code ? (
                    <Typography variant="caption" color="text.secondary" component="div">
                      {row.postal_code}
                    </Typography>
                  ) : null}
                </TableCell>
                <TableCell sx={{ whiteSpace: "nowrap" }}>
                  <Stack direction="row" spacing={0.5} sx={{ alignItems: "center" }}>
                    <Typography variant="body2" sx={{ fontVariantNumeric: "tabular-nums", fontWeight: 650 }}>
                      {row.phone_number ?? "—"}
                    </Typography>
                    <Tooltip title="Appeler">
                      <IconButton
                        size="small"
                        component="a"
                        href={row.phone_number ? `tel:${row.phone_number.replace(/\s/g, "")}` : undefined}
                        aria-label="Appeler"
                      >
                        <PhoneOutlinedIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </Stack>
                </TableCell>
                <TableCell>
                  {row.rating != null ? (
                    <Stack direction="row" spacing={0.5} sx={{ alignItems: "center" }}>
                      <StarOutlinedIcon sx={{ fontSize: 16, color: "warning.main" }} />
                      <Typography variant="body2" sx={{ fontWeight: 700 }}>{row.rating.toFixed(1)}</Typography>
                    </Stack>
                  ) : (
                    <Typography variant="body2" color="text.secondary">—</Typography>
                  )}
                  {row.reviews_count != null ? (
                    <Typography variant="caption" color="text.secondary" component="div">
                      {row.reviews_count} avis
                    </Typography>
                  ) : null}
                </TableCell>
                <TableCell sx={{ minWidth: 200 }}>
                  <Stack spacing={0.5} sx={{ alignItems: "flex-start" }}>
                    <OsintStatusChip status={row.osint_status} />
                    {row.osint_operator ? (
                      <Typography variant="caption" color="text.secondary" component="div" noWrap sx={{ maxWidth: 200 }}>
                        {row.osint_operator}
                      </Typography>
                    ) : null}
                    <ProspectLabStatusChip status={row.prospectlab_status} />
                    <NameMatchChip status={row.name_match_status} />
                  </Stack>
                </TableCell>
                <TableCell sx={{ minWidth: 160 }}>{statusSelect(row)}</TableCell>
                <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>{rowActions(row)}</TableCell>
              </TableRow>
            ))}
            {sorted.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7}>
                  <Box sx={{ py: 6, textAlign: "center" }}>
                    <Typography variant="subtitle2">Rien a afficher</Typography>
                    <Typography variant="body2" color="text.secondary">
                      Importe un Excel ou elargis les filtres.
                    </Typography>
                  </Box>
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </TableContainer>
    </>
  );
}
