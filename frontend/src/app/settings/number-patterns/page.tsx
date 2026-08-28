"use client";

import React, { useCallback, useMemo, useState } from "react";
import Link from "next/link";
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  IconButton,
  InputLabel,
  MenuItem,
  Select,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import DeleteIcon from "@mui/icons-material/Delete";
import { AppLayout } from "../../../components/AppLayout";
import { VgPageHeader } from "../../../components/mui/VgPageHeader";
import { VgProfileChip } from "../../../components/mui/VgProfileChip";
import { VgSaveBar } from "../../../components/mui/VgSaveBar";
import { VgSettingsSection } from "../../../components/mui/VgSettingsSection";
import { useIncomingCallConfig } from "../../../hooks/useIncomingCallConfig";

type PatternRule = {
  pattern: string;
  action: "permitted" | "screened" | "blocked";
  reason: string;
  enabled: boolean;
};

type PatternsBlock = {
  enabled?: boolean;
  rules?: PatternRule[];
};

const EMPTY_RULE: PatternRule = {
  pattern: "",
  action: "blocked",
  reason: "",
  enabled: true
};

/**
 * Gestion des patterns numeriques (policy incoming_call).
 */
export default function NumberPatternsSettingsPage() {
  const {
    config,
    loading,
    saving,
    dirty,
    error,
    success,
    setError,
    setSuccess,
    patchField,
    save
  } = useIncomingCallConfig();

  const patterns = useMemo(
    () => (config?.number_patterns || {}) as PatternsBlock,
    [config?.number_patterns]
  );
  const rules = patterns.rules || [];

  const [dialogOpen, setDialogOpen] = useState(false);
  const [draftRule, setDraftRule] = useState<PatternRule>(EMPTY_RULE);
  const [editIndex, setEditIndex] = useState<number | null>(null);

  const patchPatterns = useCallback(
    (partial: Partial<PatternsBlock>) => {
      patchField("number_patterns", { ...patterns, ...partial });
    },
    [patchField, patterns]
  );

  const openAdd = () => {
    setDraftRule({ ...EMPTY_RULE });
    setEditIndex(null);
    setDialogOpen(true);
  };

  const openEdit = (idx: number) => {
    setDraftRule({ ...rules[idx] });
    setEditIndex(idx);
    setDialogOpen(true);
  };

  const saveRule = () => {
    if (!draftRule.pattern.trim()) return;
    const next = [...rules];
    const row = { ...draftRule, pattern: draftRule.pattern.trim() };
    if (editIndex === null) next.push(row);
    else next[editIndex] = row;
    patchPatterns({ rules: next });
    setDialogOpen(false);
  };

  const removeRule = (idx: number) => {
    patchPatterns({ rules: rules.filter((_, i) => i !== idx) });
  };

  return (
    <AppLayout title="Patterns numeros" hidePageHeader>
      <VgPageHeader
        title="Patterns numeros"
        subtitle="Regles par masque appliquees avant listes blanche/noire (sauf whitelist explicite)."
        action={
          <Link href="/settings" style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <ArrowBackIcon fontSize="small" />
            <Typography variant="body2">Parametres</Typography>
          </Link>
        }
      />

      {loading || !config ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
          <CircularProgress />
        </Box>
      ) : (
        <>
          <Alert severity="info" sx={{ mb: 2 }}>
            Formats : <code>+338%</code> (prefixe), <code>P</code> / <code>O</code> (masque),{" "}
            <code>^08</code> (regex). Voir aussi{" "}
            <Link href="/filtering">Filtrage</Link> pour les listes et regles DB.
          </Alert>

          <VgSettingsSection title="Activation" description="Active les patterns ci-dessous a l'appel entrant.">
            <FormControlLabel
              control={
                <Switch
                  checked={Boolean(patterns.enabled)}
                  onChange={(e) => patchPatterns({ enabled: e.target.checked })}
                />
              }
              label="Patterns numeriques actifs"
            />
          </VgSettingsSection>

          <VgSettingsSection
            title="Regles"
            description="La premiere regle qui correspond determine le profil."
          >
            <Box sx={{ display: "flex", justifyContent: "flex-end", mb: 1 }}>
              <Button startIcon={<AddIcon />} variant="outlined" size="small" onClick={openAdd}>
                Ajouter
              </Button>
            </Box>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Pattern</TableCell>
                  <TableCell>Profil</TableCell>
                  <TableCell>Raison</TableCell>
                  <TableCell>Actif</TableCell>
                  <TableCell align="right">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {rules.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={5}>
                      <Typography variant="body2" color="text.secondary">
                        Aucune regle. Les defauts FR sont proposes a l'ajout manuel.
                      </Typography>
                    </TableCell>
                  </TableRow>
                ) : (
                  rules.map((r, idx) => (
                    <TableRow key={`${r.pattern}-${idx}`} hover sx={{ cursor: "pointer" }} onClick={() => openEdit(idx)}>
                      <TableCell sx={{ fontFamily: "monospace" }}>{r.pattern}</TableCell>
                      <TableCell>
                        <VgProfileChip profile={r.action} />
                      </TableCell>
                      <TableCell>{r.reason || "—"}</TableCell>
                      <TableCell>{r.enabled ? "oui" : "non"}</TableCell>
                      <TableCell align="right" onClick={(e) => e.stopPropagation()}>
                        <IconButton size="small" color="error" onClick={() => removeRule(idx)}>
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </VgSettingsSection>

          <VgSaveBar
            saving={saving}
            dirty={dirty}
            error={error}
            success={success}
            onSave={() => void save()}
            onDismissError={() => setError(null)}
            onDismissSuccess={() => setSuccess(null)}
          />

          <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
            <DialogTitle>{editIndex === null ? "Nouvelle regle" : "Modifier la regle"}</DialogTitle>
            <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 2, pt: 1 }}>
              <TextField
                label="Pattern"
                value={draftRule.pattern}
                onChange={(e) => setDraftRule((d) => ({ ...d, pattern: e.target.value }))}
                placeholder="+338% ou P ou ^08"
                fullWidth
                size="small"
              />
              <FormControl size="small" fullWidth>
                <InputLabel>Profil</InputLabel>
                <Select
                  label="Profil"
                  value={draftRule.action}
                  onChange={(e) =>
                    setDraftRule((d) => ({
                      ...d,
                      action: e.target.value as PatternRule["action"]
                    }))
                  }
                >
                  <MenuItem value="permitted">Autorise</MenuItem>
                  <MenuItem value="screened">Inconnu</MenuItem>
                  <MenuItem value="blocked">Bloque</MenuItem>
                </Select>
              </FormControl>
              <TextField
                label="Raison (optionnel)"
                value={draftRule.reason}
                onChange={(e) => setDraftRule((d) => ({ ...d, reason: e.target.value }))}
                fullWidth
                size="small"
              />
              <FormControlLabel
                control={
                  <Switch
                    checked={draftRule.enabled}
                    onChange={(e) => setDraftRule((d) => ({ ...d, enabled: e.target.checked }))}
                  />
                }
                label="Regle active"
              />
            </DialogContent>
            <DialogActions>
              <Button onClick={() => setDialogOpen(false)}>Annuler</Button>
              <Button variant="contained" onClick={saveRule}>
                OK
              </Button>
            </DialogActions>
          </Dialog>
        </>
      )}
    </AppLayout>
  );
}
