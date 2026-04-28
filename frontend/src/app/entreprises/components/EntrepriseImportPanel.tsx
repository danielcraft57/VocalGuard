import React from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  Chip,
  FormControlLabel,
  LinearProgress,
  Stack,
  Typography,
} from "@mui/material";
import type { EntrepriseImportSummary } from "../../../services/entreprisesApi";
import type { ImportProgressCounters } from "../types";

export function EntrepriseImportPanel(props: {
  importing: boolean;
  analyzePhone: boolean;
  setAnalyzePhone: (v: boolean) => void;
  onFileChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  progressPercent: number | null;
  progressCounters: ImportProgressCounters | null;
  lastImportSummary: EntrepriseImportSummary | null;
  errorMessage: string | null;
}) {
  const fileInputId = "entreprise-upload-input";

  return (
    <Card
      sx={{
        mt: 0.5,
        borderRadius: 3,
        border: "1px solid var(--vg-color-border-subtle)",
        bgcolor: "var(--vg-color-bg-soft)",
        color: "var(--vg-color-text)",
        transition: "all .2s ease",
        "&:hover": { boxShadow: 6 },
      }}
    >
      <CardContent>
        <Stack spacing={1.5}>
          <Stack direction={{ xs: "column", md: "row" }} sx={{ alignItems: { xs: "flex-start", md: "center" }, justifyContent: "space-between", gap: 1 }}>
            <Stack direction="row" sx={{ alignItems: "center" }} spacing={1}>
              <span className="material-icons" style={{ fontSize: 18 }}>upload_file</span>
              <Typography variant="subtitle2">Import Excel (.xlsx)</Typography>
            </Stack>
            <FormControlLabel
              control={
                <Checkbox
                  checked={props.analyzePhone}
                  onChange={(ev) => props.setAnalyzePhone(ev.target.checked)}
                  disabled={props.importing}
                  size="small"
                  sx={{
                    color: "var(--vg-color-text-muted)",
                    "&.Mui-checked": { color: "var(--vg-color-primary)" },
                  }}
                />
              }
              label="Analyser les numéros via Celery (OSINT)"
              sx={{ m: 0 }}
            />
          </Stack>

          <Box
            sx={{
              p: 1.2,
              borderRadius: 2,
              border: "1px dashed var(--vg-color-border)",
              bgcolor: "var(--vg-color-surface)",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 1,
            }}
          >
            <Stack spacing={0.25}>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                Importer un fichier Excel
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Format accepté: `.xlsx`
              </Typography>
            </Stack>

            <Button
              component="label"
              htmlFor={fileInputId}
              variant="contained"
              disabled={props.importing}
              sx={{ borderRadius: 999 }}
            >
              Choisir un fichier
              <input id={fileInputId} type="file" accept=".xlsx" onChange={props.onFileChange} hidden />
            </Button>
          </Box>

          {props.importing ? <Typography variant="body2" color="text.secondary">Import en cours...</Typography> : null}

          {props.progressPercent !== null ? (
            <Stack spacing={0.75}>
              <Typography variant="body2" color="text.secondary">
                Avancement: <strong>{props.progressPercent}%</strong>
              </Typography>
              <LinearProgress
                variant="determinate"
                value={props.progressPercent}
                sx={{ height: 8, borderRadius: 99, "& .MuiLinearProgress-bar": { transition: "transform .2s ease-out" } }}
              />
              {props.progressCounters ? (
                <Stack direction="row" sx={{ flexWrap: "wrap", gap: 0.75 }}>
                  <Chip size="small" label={`Importées ${props.progressCounters.imported}`} color="success" variant="outlined" />
                  <Chip size="small" label={`Website ${props.progressCounters.skippedWebsite}`} color="warning" variant="outlined" />
                  <Chip size="small" label={`Invalides ${props.progressCounters.skippedInvalid}`} color="warning" variant="outlined" />
                  <Chip size="small" label={`Doublons ${props.progressCounters.skippedDuplicates}`} color="default" variant="outlined" />
                </Stack>
              ) : null}
            </Stack>
          ) : null}

          {props.lastImportSummary ? (
            <Box>
              <Typography variant="subtitle2" gutterBottom>Résumé import</Typography>
              <Stack direction="row" sx={{ gap: 0.75, flexWrap: "wrap" }}>
                <Chip size="small" label={`Batch ${props.lastImportSummary.batch_id}`} />
                <Chip size="small" label={`Total ${props.lastImportSummary.total_rows}`} />
                <Chip size="small" color="success" variant="outlined" label={`Importées ${props.lastImportSummary.imported_rows}`} />
                <Chip size="small" color="warning" variant="outlined" label={`Website ${props.lastImportSummary.skipped_with_website}`} />
                <Chip size="small" color="warning" variant="outlined" label={`Invalides ${props.lastImportSummary.skipped_invalid}`} />
                <Chip size="small" variant="outlined" label={`Doublons ${props.lastImportSummary.skipped_duplicates}`} />
              </Stack>
            </Box>
          ) : null}

          {props.errorMessage ? <Alert severity="error">{props.errorMessage}</Alert> : null}
        </Stack>
      </CardContent>
    </Card>
  );
}

