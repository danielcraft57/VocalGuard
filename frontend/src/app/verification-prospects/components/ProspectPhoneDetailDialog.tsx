"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import RefreshOutlinedIcon from "@mui/icons-material/RefreshOutlined";
import OpenInNewOutlinedIcon from "@mui/icons-material/OpenInNewOutlined";
import CloseIcon from "@mui/icons-material/Close";
import PhoneOutlinedIcon from "@mui/icons-material/PhoneOutlined";
import ContentCopyOutlinedIcon from "@mui/icons-material/ContentCopyOutlined";
import PlaceOutlinedIcon from "@mui/icons-material/PlaceOutlined";
import StarOutlinedIcon from "@mui/icons-material/StarOutlined";
import ManageSearchOutlinedIcon from "@mui/icons-material/ManageSearchOutlined";
import StorefrontOutlinedIcon from "@mui/icons-material/StorefrontOutlined";
import FactCheckOutlinedIcon from "@mui/icons-material/FactCheckOutlined";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  IconButton,
  LinearProgress,
  Link,
  Paper,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";
import type { PhoneNumberProfile } from "../../../services/entreprisesApi";
import {
  enrichProspectPhoneAgain,
  fetchProspectPhoneDetail,
  ProspectPhone,
  ProspectPhoneDetail,
} from "../../../services/prospectPhonesApi";
import {
  MATCH_STATUS_LABELS,
  NameMatchChip,
  OsintStatusChip,
  ProspectLabStatusChip,
} from "../prospectStatusUi";
import { prospectDisplayCity } from "../prospectDisplayUtils";

const sectionPaperSx = {
  p: 1.75,
  borderRadius: 2.5,
  border: "1px solid var(--vg-color-border-subtle)",
  bgcolor: "var(--vg-color-bg)",
  height: "100%",
};

/**
 * Affiche une paire label / valeur dans une carte.
 */
function Field(props: { label: string; value?: React.ReactNode; empty?: string }): React.ReactElement | null {
  const hasValue = props.value !== null && props.value !== undefined && props.value !== "";
  if (!hasValue && !props.empty) return null;
  return (
    <Box sx={{ mb: 1.1 }}>
      <Typography variant="caption" color="text.secondary" component="div" sx={{ mb: 0.2 }}>
        {props.label}
      </Typography>
      <Typography variant="body2" component="div" sx={{ fontWeight: hasValue ? 550 : 400, wordBreak: "break-word" }}>
        {hasValue ? props.value : (props.empty ?? "—")}
      </Typography>
    </Box>
  );
}

function formatDt(iso?: string | null): string | undefined {
  if (!iso) return undefined;
  try {
    return new Date(iso).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
  } catch {
    return iso;
  }
}

function reputationFlags(profile: PhoneNumberProfile): string[] {
  const flags: string[] = [];
  if (profile.is_spam) flags.push("spam");
  if (profile.is_scam) flags.push("arnaque");
  if (profile.is_commercial) flags.push("commercial");
  if (profile.is_telemarketer) flags.push("demarchage");
  if (profile.is_robocall) flags.push("robot");
  return flags;
}

function telHref(phone?: string | null): string | undefined {
  const raw = (phone ?? "").replace(/\s/g, "");
  return raw ? `tel:${raw}` : undefined;
}

/**
 * Carte de section avec titre et icone.
 */
function SectionCard(props: {
  icon: React.ReactNode;
  title: string;
  subtitle?: string;
  accent?: boolean;
  children: React.ReactNode;
}): React.ReactElement {
  return (
    <Paper elevation={0} sx={{
      ...sectionPaperSx,
      ...(props.accent
        ? {
          borderColor: "var(--vg-color-primary)",
          boxShadow: "0 0 0 1px var(--vg-color-primary-soft)",
        }
        : {}),
    }}
    >
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 1.25 }}>
        <Box
          sx={{
            width: 36,
            height: 36,
            borderRadius: 2,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            bgcolor: props.accent ? "var(--vg-color-primary-soft)" : "var(--vg-color-surface)",
            color: props.accent ? "var(--vg-color-primary)" : "text.secondary",
          }}
        >
          {props.icon}
        </Box>
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 700, lineHeight: 1.25 }}>
            {props.title}
          </Typography>
          {props.subtitle ? (
            <Typography variant="caption" color="text.secondary" component="div">
              {props.subtitle}
            </Typography>
          ) : null}
        </Box>
      </Stack>
      {props.children}
    </Paper>
  );
}

/**
 * Modal fiche prospect : lecture rapide + OSINT / ProspectLab mis en avant.
 */
export function ProspectPhoneDetailDialog(props: {
  prospectId: number | null;
  fallbackProspect?: ProspectPhone | null;
  statusLabels: Record<string, string>;
  open: boolean;
  onClose: () => void;
  onUpdated?: (prospect: ProspectPhone) => void;
}): React.ReactElement {
  const [detail, setDetail] = useState<ProspectPhoneDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [enriching, setEnriching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(async (id: number, seed?: ProspectPhone | null) => {
    setLoading(true);
    setError(null);
    if (seed) {
      setDetail({ prospect: seed, osint_profile: null });
    }
    try {
      const data = await fetchProspectPhoneDetail(id);
      setDetail(data);
      setError(null);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Chargement impossible";
      if (seed) {
        setDetail({ prospect: seed, osint_profile: null });
        setError(`Detail serveur partiel : ${msg}`);
      } else {
        setDetail(null);
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!props.open || props.prospectId == null) {
      setDetail(null);
      setError(null);
      setCopied(false);
      return;
    }
    const seed =
      props.fallbackProspect && props.fallbackProspect.id === props.prospectId
        ? props.fallbackProspect
        : null;
    void load(props.prospectId, seed);
  }, [props.open, props.prospectId, props.fallbackProspect, load]);

  const handleEnrich = async () => {
    if (props.prospectId == null) return;
    setEnriching(true);
    setError(null);
    try {
      const data = await enrichProspectPhoneAgain(props.prospectId);
      setDetail(data);
      props.onUpdated?.(data.prospect);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Enrichissement echoue");
    } finally {
      setEnriching(false);
    }
  };

  const p = detail?.prospect;
  const profile = detail?.osint_profile;

  const mapsUrl = useMemo(() => {
    if (p?.latitude == null || p?.longitude == null) return undefined;
    return `https://www.google.com/maps?q=${p.latitude},${p.longitude}`;
  }, [p?.latitude, p?.longitude]);

  const addressLine = useMemo(() => {
    if (!p) return "";
    return [p.address_1, p.address_2, [p.postal_code, p.city].filter(Boolean).join(" "), p.country]
      .filter(Boolean)
      .join(", ");
  }, [p]);

  const copyPhone = () => {
    const num = p?.phone_number?.trim();
    if (!num) return;
    void navigator.clipboard.writeText(num).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    });
  };

  const riskFlags = profile ? reputationFlags(profile) : [];

  return (
    <Dialog
      open={props.open}
      onClose={props.onClose}
      fullWidth
      maxWidth="md"
      scroll="paper"
      slotProps={{
        paper: {
          sx: {
            borderRadius: 3,
            overflow: "hidden",
            border: "1px solid var(--vg-color-border-subtle)",
            bgcolor: "var(--vg-color-surface)",
          },
        },
      }}
    >
      {(loading || enriching) ? <LinearProgress /> : null}

      <Box
        sx={{
          px: 2.5,
          pt: 2,
          pb: 2,
          background: "linear-gradient(135deg, var(--vg-color-primary-soft) 0%, var(--vg-color-bg) 55%)",
          borderBottom: "1px solid var(--vg-color-border-subtle)",
          position: "relative",
        }}
      >
        <IconButton
          aria-label="Fermer"
          onClick={props.onClose}
          sx={{ position: "absolute", right: 8, top: 8 }}
        >
          <CloseIcon />
        </IconButton>

        {p ? (
          <>
            <Stack direction="row" spacing={1} sx={{ alignItems: "flex-start", pr: 5 }}>
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography variant="h6" sx={{ fontWeight: 800, lineHeight: 1.25, mb: 0.4 }}>
                  {p.name}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {(() => {
                    const ville = prospectDisplayCity(p);
                    return ville !== "—" ? ville : "Ville inconnue";
                  })()}
                </Typography>
              </Box>
              {p.rating != null ? (
                <Chip
                  icon={<StarOutlinedIcon />}
                  label={`${p.rating.toFixed(1)}${p.reviews_count != null ? ` (${p.reviews_count})` : ""}`}
                  sx={{ fontWeight: 700, flexShrink: 0 }}
                />
              ) : null}
            </Stack>

            <Stack direction="row" spacing={1} sx={{ mt: 1.5, alignItems: "center", flexWrap: "wrap", gap: 1 }}>
              <Typography
                component="a"
                href={telHref(p.phone_number)}
                variant="h6"
                sx={{
                  fontWeight: 750,
                  fontVariantNumeric: "tabular-nums",
                  textDecoration: "none",
                  color: "inherit",
                  letterSpacing: "0.02em",
                }}
              >
                {p.phone_number ?? "Pas de numero"}
              </Typography>
              {p.phone_number ? (
                <>
                  <Tooltip title="Appeler">
                    <IconButton size="small" component="a" href={telHref(p.phone_number)} sx={{ bgcolor: "var(--vg-color-surface)" }}>
                      <PhoneOutlinedIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title={copied ? "Copie !" : "Copier le numero"}>
                    <IconButton size="small" onClick={copyPhone} sx={{ bgcolor: "var(--vg-color-surface)" }}>
                      <ContentCopyOutlinedIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </>
              ) : null}
            </Stack>

            <Stack direction="row" spacing={0.5} sx={{ mt: 1.25, flexWrap: "wrap", gap: 0.5 }}>
              <OsintStatusChip status={p.osint_status} />
              <ProspectLabStatusChip status={p.prospectlab_status} />
              <NameMatchChip status={p.name_match_status} />
              <Chip
                size="small"
                variant="outlined"
                label={props.statusLabels[p.verification_status] ?? p.verification_status}
              />
            </Stack>
          </>
        ) : (
          <Typography variant="subtitle1" sx={{ fontWeight: 700, pr: 5 }}>
            Fiche prospect
          </Typography>
        )}
      </Box>

      <Box sx={{ px: 2.5, py: 2, maxHeight: "min(70vh, 640px)", overflow: "auto" }}>
        {error ? (
          <Alert severity={p ? "warning" : "error"} sx={{ mb: 2 }}>
            {error}
          </Alert>
        ) : null}
        {loading && !p ? (
          <Typography variant="body2" color="text.secondary">Chargement…</Typography>
        ) : null}
        {loading && p ? (
          <Typography variant="caption" color="text.secondary" component="div" sx={{ mb: 1.5 }}>
            Synchronisation avec le serveur…
          </Typography>
        ) : null}

        {p ? (
          <Stack spacing={2}>
            <Box
              sx={{
                display: "grid",
                gap: 1.5,
                gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" },
              }}
            >
              <SectionCard
                icon={<ManageSearchOutlinedIcon fontSize="small" />}
                title="OSINT"
                subtitle={p.osint_status === "done" ? "Enrichissement termine" : "En attente ou en cours"}
                accent={p.osint_status === "done"}
              >
                <Field label="Entreprise detectee" value={p.osint_company_name} empty="Non renseigne" />
                <Field label="Operateur / reseau" value={p.osint_operator} empty="—" />
                <Field label="Zone" value={p.osint_region} empty="—" />
                <Field label="Reputation" value={p.osint_reputation} empty="—" />
                <Field label="Dernier enrichissement" value={formatDt(p.enriched_at)} empty="Jamais" />
              </SectionCard>

              <SectionCard
                icon={<StorefrontOutlinedIcon fontSize="small" />}
                title="ProspectLab"
                subtitle={
                  p.prospectlab_status === "matched"
                    ? "Fiche trouvee"
                    : p.prospectlab_status === "not_found"
                      ? "Aucune fiche"
                      : "Non cherche"
                }
              >
                <Field label="Nom ProspectLab" value={p.prospectlab_name} empty="—" />
                <Field
                  label="ID entreprise"
                  value={p.prospectlab_entreprise_id != null ? String(p.prospectlab_entreprise_id) : undefined}
                  empty="—"
                />
                <Field
                  label="Correspondance nom"
                  value={p.name_match_status ? (MATCH_STATUS_LABELS[p.name_match_status] ?? p.name_match_status) : undefined}
                  empty="—"
                />
              </SectionCard>
            </Box>

            {profile ? (
              <SectionCard
                icon={<ManageSearchOutlinedIcon fontSize="small" />}
                title="Profil OSINT complet"
                subtitle={`Sources : ${(profile.sources?.length ?? 0) > 0 ? profile.sources!.join(", ") : "non listees"}`}
                accent
              >
                <Box
                  sx={{
                    display: "grid",
                    gap: 1.5,
                    gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" },
                  }}
                >
                  <Field label="Societe" value={profile.company_name ?? profile.name} />
                  <Field label="Type de ligne" value={profile.line_type} />
                  <Field label="SIREN" value={profile.company_siren} />
                  <Field label="SIRET" value={profile.company_siret} />
                  <Field label="Activite" value={profile.company_activity} />
                  <Field label="Adresse societe" value={profile.company_address} />
                  <Field
                    label="Localisation"
                    value={[profile.city, profile.region, profile.department, profile.postal_code].filter(Boolean).join(" · ")}
                  />
                  <Field label="Numero normalise" value={profile.normalized_number} />
                </Box>
                <Stack direction="row" spacing={0.5} sx={{ mt: 0.5, flexWrap: "wrap", gap: 0.5 }}>
                  {riskFlags.length === 0 ? (
                    <Chip size="small" color="success" variant="outlined" label="Aucun signal negatif" />
                  ) : (
                    riskFlags.map((f) => (
                      <Chip key={f} size="small" color="warning" label={f} />
                    ))
                  )}
                  {profile.spam_score != null ? (
                    <Chip size="small" variant="outlined" label={`Score spam ${profile.spam_score}`} />
                  ) : null}
                </Stack>
                <Typography variant="caption" color="text.secondary" component="div" sx={{ mt: 1 }}>
                  Verifie le {formatDt(profile.last_checked_at) ?? "—"}
                </Typography>
              </SectionCard>
            ) : p.osint_status === "done" ? (
              <Alert severity="info" variant="outlined">
                Resume OSINT present sur la fiche, mais pas de profil detaille en base pour ce format de numero.
                Relance une recherche si tu veux SIREN, sources, etc.
              </Alert>
            ) : (
              <Alert severity="info" variant="outlined">
                Pas encore de profil OSINT detaille. Le bouton en bas relance OSINT + ProspectLab sur ce numero.
              </Alert>
            )}

            <Box
              sx={{
                display: "grid",
                gap: 1.5,
                gridTemplateColumns: { xs: "1fr", md: "1.2fr 1fr" },
              }}
            >
              <SectionCard icon={<PlaceOutlinedIcon fontSize="small" />} title="Adresse" subtitle="Import Excel / Google">
                <Typography variant="body2" sx={{ mb: 1, lineHeight: 1.5 }}>
                  {addressLine || "Adresse non renseignee"}
                </Typography>
                {mapsUrl ? (
                  <Button
                    size="small"
                    component="a"
                    href={mapsUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    startIcon={<OpenInNewOutlinedIcon />}
                    sx={{ borderRadius: 999 }}
                  >
                    Ouvrir sur la carte
                  </Button>
                ) : null}
              </SectionCard>

              <SectionCard icon={<StarOutlinedIcon fontSize="small" />} title="Google" subtitle="Categories et avis">
                <Stack direction="row" spacing={0.5} sx={{ flexWrap: "wrap", gap: 0.4, mb: 1 }}>
                  {(p.categories ?? []).map((c) => (
                    <Chip key={c} size="small" color="primary" variant="outlined" label={c} />
                  ))}
                  {(p.google_types ?? []).map((t) => (
                    <Chip key={t} size="small" variant="outlined" label={t} />
                  ))}
                </Stack>
                {p.website ? (
                  <Field
                    label="Site web"
                    value={
                      <Link href={p.website} target="_blank" rel="noopener noreferrer">
                        {p.website}
                      </Link>
                    }
                  />
                ) : (
                  <Field label="Site web" empty="—" />
                )}
              </SectionCard>
            </Box>

            <Accordion
              disableGutters
              elevation={0}
              sx={{
                border: "1px solid var(--vg-color-border-subtle)",
                borderRadius: "12px !important",
                "&:before": { display: "none" },
                bgcolor: "var(--vg-color-bg)",
              }}
            >
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                  <FactCheckOutlinedIcon fontSize="small" color="action" />
                  <Typography variant="body2" sx={{ fontWeight: 650 }}>Notes et donnees techniques</Typography>
                </Stack>
              </AccordionSummary>
              <AccordionDetails>
                <Field label="Notes de verification" value={p.verification_notes} empty="Aucune note" />
                <Field label="Verifie le" value={formatDt(p.verified_at)} empty="—" />
                <Field label="Lot d'import" value={p.import_batch_id != null ? `#${p.import_batch_id}` : undefined} empty="—" />
                <Field label="Profil OSINT (id)" value={p.phone_profile_id != null ? String(p.phone_profile_id) : undefined} empty="—" />
                <Field label="Categories brutes" value={p.google_categories_raw} />
                <Field label="Traduction categories" value={p.category_translate_raw} />
                <Field label="Cree le" value={formatDt(p.created_at)} />
                <Field label="Mis a jour" value={formatDt(p.updated_at)} />
              </AccordionDetails>
            </Accordion>
          </Stack>
        ) : null}
      </Box>

      <DialogActions
        sx={{
          flexWrap: "wrap",
          gap: 1,
          px: 2.5,
          py: 1.5,
          borderTop: "1px solid var(--vg-color-border-subtle)",
          bgcolor: "var(--vg-color-bg)",
        }}
      >
        <Button
          startIcon={<RefreshOutlinedIcon />}
          variant="contained"
          disabled={!p?.phone_number || enriching || loading}
          onClick={() => void handleEnrich()}
          sx={{ borderRadius: 999 }}
        >
          {enriching ? "Recherche en cours…" : "Chercher plus d'infos"}
        </Button>
        <Box sx={{ flex: 1 }} />
        <Button onClick={props.onClose} sx={{ borderRadius: 999 }}>Fermer</Button>
      </DialogActions>
    </Dialog>
  );
}
