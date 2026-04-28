import React, { useEffect, useMemo, useState } from "react";
import {
  Box,
  Chip,
  Dialog,
  DialogContent,
  DialogTitle,
  Stack,
  Tab,
  Tabs,
  Typography,
} from "@mui/material";
import { fetchEntreprisePhoneAnalyses, fetchOsintProfile } from "../../../services/entreprisesApi";
import type { Entreprise, EntreprisePhoneAnalysis, PhoneNumberProfile } from "../../../services/entreprisesApi";
import type { EntrepriseCallStats, EntrepriseDetailsTab } from "../types";

export function EntrepriseDetailsDialog(props: {
  open: boolean;
  entreprise: Entreprise | null;
  tab: EntrepriseDetailsTab;
  onTabChange: (tab: EntrepriseDetailsTab) => void;
  callStats: EntrepriseCallStats | null;
  onClose: () => void;
}) {
  const e = props.entreprise;
  const phoneForOsint = useMemo(() => (e?.phone_number ?? "").trim(), [e?.phone_number]);
  const [osintAnalyses, setOsintAnalyses] = useState<EntreprisePhoneAnalysis[] | null>(null);
  const [osintProfile, setOsintProfile] = useState<PhoneNumberProfile | null>(null);
  const [osintLoading, setOsintLoading] = useState(false);
  const [osintError, setOsintError] = useState<string | null>(null);

  useEffect(() => {
    if (!props.open) return;
    if (props.tab !== "osint") return;
    if (!e?.id) return;
    if (!phoneForOsint) {
      setOsintAnalyses([]);
      setOsintProfile(null);
      setOsintError("Entreprise sans numéro de téléphone.");
      return;
    }

    let cancelled = false;
    setOsintLoading(true);
    setOsintError(null);
    (async () => {
      try {
        const analyses = await fetchEntreprisePhoneAnalyses(e.id);
        if (cancelled) return;
        setOsintAnalyses(analyses);

        const profile = await fetchOsintProfile(phoneForOsint);
        if (cancelled) return;
        setOsintProfile(profile);
      } catch (err) {
        if (cancelled) return;
        setOsintProfile(null);
        setOsintError((err as Error)?.message ?? "Impossible de charger le profil OSINT");
      } finally {
        if (!cancelled) setOsintLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [props.open, props.tab, e?.id, phoneForOsint]);

  if (!props.open || !e) return null;

  return (
    <Dialog
      open={props.open}
      onClose={props.onClose}
      fullWidth
      maxWidth="md"
      slots={{}}
      slotProps={{
        paper: {
          sx: {
            borderRadius: 3,
            border: "1px solid var(--vg-color-border-subtle)",
            bgcolor: "var(--vg-color-bg-soft)",
            color: "var(--vg-color-text)",
            boxShadow: "var(--vg-shadow-soft)",
          },
        },
      }}
    >
      <DialogTitle sx={{ pb: 1.25 }}>
        <Stack spacing={0.75}>
          <Typography variant="h6" sx={{ fontWeight: 800, letterSpacing: -0.2 }}>
            {e.name}
          </Typography>
          <Stack direction="row" sx={{ flexWrap: "wrap", gap: 0.75, alignItems: "center" }}>
            <Chip size="small" variant="outlined" label={e.phone_number ?? "Sans téléphone"} />
            <Chip size="small" color="primary" variant="outlined" label={e.city ?? "Ville inconnue"} />
            {e.categories?.length ? (
              e.categories.slice(0, 6).map((c) => <Chip key={c} size="small" color="secondary" variant="outlined" label={c} />)
            ) : (
              <Chip size="small" color="secondary" variant="outlined" label="Catégorie inconnue" />
            )}
            {e.categories && e.categories.length > 6 ? (
              <Chip size="small" variant="outlined" label={`+${e.categories.length - 6}`} />
            ) : null}
          </Stack>
        </Stack>
      </DialogTitle>
      <DialogContent>
        <Tabs
          value={props.tab}
          onChange={(_, v) => props.onTabChange(v)}
          variant="scrollable"
          allowScrollButtonsMobile
          sx={{
            mb: 2,
            borderBottom: "1px solid var(--vg-color-border-subtle)",
            "& .MuiTab-root": { textTransform: "none", minHeight: 44, color: "var(--vg-color-text-muted)" },
            "& .MuiTab-root.Mui-selected": { color: "var(--vg-color-text)" },
            "& .MuiTabs-indicator": { backgroundColor: "var(--vg-color-primary)" },
          }}
        >
          <Tab value="infos" label="Infos" />
          <Tab value="avis" label="Avis" />
          <Tab value="appels" label="Appels" />
          <Tab value="osint" label="OSINT" />
        </Tabs>

        {props.tab === "infos" ? (
          <Stack spacing={1.1}>
            <Typography variant="subtitle2" sx={{ color: "var(--vg-color-text)" }}>
              Coordonnées
            </Typography>
            {e.categories?.length ? (
              <Stack direction="row" sx={{ flexWrap: "wrap", gap: 0.75 }}>
                {e.categories.map((c) => (
                  <Chip key={c} size="small" color="secondary" variant="outlined" label={c} />
                ))}
              </Stack>
            ) : null}
            <Typography variant="body2">
              Adresse: {(e.address_1 ?? "").trim() || (e.address_2 ?? "").trim() ? `${e.address_1 ?? ""}${e.address_2 ? `, ${e.address_2}` : ""}` : "-"}
            </Typography>
            <Typography variant="body2">Lieu: {e.city ?? "-"} {e.country ? `(${e.country})` : ""}</Typography>
            <Typography variant="body2">GPS: {typeof e.latitude === "number" && typeof e.longitude === "number" ? `${e.latitude}, ${e.longitude}` : "-"}</Typography>
          </Stack>
        ) : null}

        {props.tab === "avis" ? (
          <Stack spacing={1.1}>
            <Typography variant="subtitle2" sx={{ color: "var(--vg-color-text)" }}>
              Avis
            </Typography>
            <Typography variant="body2">Note: {typeof e.rating === "number" ? e.rating.toFixed(1) : "-"}</Typography>
            <Typography variant="body2">Avis: {typeof e.reviews_count === "number" ? e.reviews_count : "-"}</Typography>
            <Typography variant="body2">Catégories: {e.categories?.length ? e.categories.join(", ") : "-"}</Typography>
          </Stack>
        ) : null}

        {props.tab === "appels" ? (
          <Stack spacing={1.1}>
            <Typography variant="subtitle2" sx={{ color: "var(--vg-color-text)" }}>
              Stats d’appels
            </Typography>
            {props.callStats ? (
              <Stack direction="row" sx={{ flexWrap: "wrap", gap: 0.75 }}>
                <Chip label={`Total ${props.callStats.total}`} color="primary" />
                {Object.entries(props.callStats.by_status).map(([k, v]) => (
                  <Chip key={k} label={`${k}: ${v}`} variant="outlined" />
                ))}
              </Stack>
            ) : (
              <Typography variant="body2" sx={{ color: "var(--vg-color-text-muted)" }}>
                Chargement...
              </Typography>
            )}
          </Stack>
        ) : null}

        {props.tab === "osint" ? (
          <Box>
            <Typography variant="subtitle2" gutterBottom sx={{ color: "var(--vg-color-text)" }}>
              OSINT
            </Typography>
            {osintLoading ? (
              <Typography variant="body2" sx={{ color: "var(--vg-color-text-muted)" }}>
                Chargement du profil OSINT...
              </Typography>
            ) : osintError ? (
              <Typography variant="body2" sx={{ color: "var(--vg-color-text-muted)" }}>
                {osintError}
              </Typography>
            ) : osintProfile ? (
              <Stack spacing={1.2}>
                <Stack direction="row" sx={{ flexWrap: "wrap", gap: 0.75 }}>
                  <Chip size="small" color="primary" label={`Réputation: ${osintProfile.reputation ?? "unknown"}`} />
                  {osintProfile.operator ? <Chip size="small" variant="outlined" label={`Opérateur: ${osintProfile.operator}`} /> : null}
                  {osintProfile.region ? <Chip size="small" variant="outlined" label={`Région: ${osintProfile.region}`} /> : null}
                  {osintProfile.city ? <Chip size="small" variant="outlined" label={`Ville: ${osintProfile.city}`} /> : null}
                  {typeof osintProfile.confidence === "number" ? <Chip size="small" variant="outlined" label={`Confiance: ${osintProfile.confidence}%`} /> : null}
                </Stack>

                <Stack direction="row" sx={{ flexWrap: "wrap", gap: 0.75 }}>
                  {osintProfile.is_spam ? <Chip size="small" color="warning" label="SPAM" /> : null}
                  {osintProfile.is_scam ? <Chip size="small" color="warning" label="SCAM" /> : null}
                  {osintProfile.is_commercial ? <Chip size="small" color="secondary" label="Commercial" /> : null}
                  {osintProfile.is_telemarketer ? <Chip size="small" color="secondary" label="Télémarketing" /> : null}
                </Stack>

                <Typography variant="body2" sx={{ color: "var(--vg-color-text-muted)" }}>
                  Dernière analyse: {osintProfile.last_checked_at ? new Date(osintProfile.last_checked_at).toLocaleString() : "-"}
                </Typography>

                {osintAnalyses?.length ? (
                  <Box>
                    <Typography variant="subtitle2" sx={{ color: "var(--vg-color-text)", mb: 0.5 }}>
                      Analyses liées à l’entreprise
                    </Typography>
                    <Stack direction="row" sx={{ flexWrap: "wrap", gap: 0.75 }}>
                      {osintAnalyses.slice(0, 6).map((a) => (
                        <Chip
                          key={a.id}
                          size="small"
                          variant="outlined"
                          label={`${a.status} • ${a.phone_number}`}
                        />
                      ))}
                    </Stack>
                  </Box>
                ) : null}
              </Stack>
            ) : (
              <Typography variant="body2" sx={{ color: "var(--vg-color-text-muted)" }}>
                Aucun profil OSINT trouvé pour ce numéro (pas encore analysé ?).
              </Typography>
            )}
          </Box>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

