"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  IconButton,
  Stack,
  Tab,
  Tabs,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography
} from "@mui/material";
import DeleteIcon from "@mui/icons-material/Delete";
import PatternIcon from "@mui/icons-material/Pattern";
import { AppLayout } from "../../components/AppLayout";
import { VgPageHeader } from "../../components/mui/VgPageHeader";
import { VgProfileChip } from "../../components/mui/VgProfileChip";
import { VgSettingsSection } from "../../components/mui/VgSettingsSection";
import {
  fetchWhitelist,
  fetchBlocklist,
  addToWhitelist,
  addToBlocklist,
  removeFromWhitelist,
  removeFromBlocklist,
  type Caller
} from "../../services/callersFilterApi";
import {
  fetchBlockRules,
  createBlockRule,
  deleteBlockRule,
  type BlockRule
} from "../../services/blockRulesApi";

type TabKey = "whitelist" | "blocklist" | "rules";

/**
 * Filtrage Material : listes blanche/noire et regles DB (motifs legacy).
 */
export default function FilteringPage() {
  const [tab, setTab] = useState<TabKey>("whitelist");
  const [whitelist, setWhitelist] = useState<Caller[]>([]);
  const [blocklist, setBlocklist] = useState<Caller[]>([]);
  const [rules, setRules] = useState<BlockRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState<string | null>(null);

  const [whitelistPhone, setWhitelistPhone] = useState("");
  const [whitelistName, setWhitelistName] = useState("");
  const [blocklistPhone, setBlocklistPhone] = useState("");
  const [blocklistNotes, setBlocklistNotes] = useState("");
  const [ruleName, setRuleName] = useState("");
  const [rulePattern, setRulePattern] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [w, b, r] = await Promise.all([fetchWhitelist(), fetchBlocklist(), fetchBlockRules()]);
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
    void load();
  }, [load]);

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

  const handleAddRule = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ruleName.trim() || !rulePattern.trim()) return;
    setSubmitting("rule");
    try {
      await createBlockRule(ruleName.trim(), rulePattern.trim(), "prefix");
      setRuleName("");
      setRulePattern("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur");
    } finally {
      setSubmitting(null);
    }
  };

  return (
    <AppLayout title="Filtrage d'appels" hidePageHeader>
      <VgPageHeader
        title="Filtrage d'appels"
        subtitle="Listes par numero et regles DB. Patterns globaux : parametres."
        action={
          <Button
            component={Link}
            href="/settings/number-patterns"
            size="small"
            startIcon={<PatternIcon />}
            variant="outlined"
          >
            Patterns policy
          </Button>
        }
      />

      {error ? (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      ) : null}

      <Tabs value={tab} onChange={(_, v: TabKey) => setTab(v)} sx={{ mb: 2 }}>
        <Tab
          value="whitelist"
          label={
            <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
              <VgProfileChip profile="permitted" />
              <span>Liste blanche</span>
            </Stack>
          }
        />
        <Tab
          value="blocklist"
          label={
            <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
              <VgProfileChip profile="blocked" />
              <span>Liste noire</span>
            </Stack>
          }
        />
        <Tab value="rules" label="Regles DB (prefixe)" />
      </Tabs>

      {loading ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
          <CircularProgress />
        </Box>
      ) : (
        <>
          {tab === "whitelist" ? (
            <VgSettingsSection
              title="Numeros autorises"
              description="Priorite sur patterns et liste noire. Avec whitelist ring-only, le fixe sonne."
            >
              <Stack component="form" onSubmit={handleAddWhitelist} direction="row" spacing={1} sx={{ mb: 2, flexWrap: "wrap" }}>
                <TextField size="small" label="Numero" value={whitelistPhone} onChange={(e) => setWhitelistPhone(e.target.value)} />
                <TextField size="small" label="Nom" value={whitelistName} onChange={(e) => setWhitelistName(e.target.value)} />
                <Button type="submit" variant="contained" disabled={Boolean(submitting)}>
                  Ajouter
                </Button>
              </Stack>
              <CallerTable
                rows={whitelist}
                onRemove={(id) => {
                  setSubmitting(`w-${id}`);
                  removeFromWhitelist(id).then(load).catch((err) => setError(String(err))).finally(() => setSubmitting(null));
                }}
                submitting={submitting}
              />
            </VgSettingsSection>
          ) : null}

          {tab === "blocklist" ? (
            <VgSettingsSection title="Numeros bloques" description="Bloques via block_service a l'appel entrant.">
              <Stack component="form" onSubmit={handleAddBlocklist} direction="row" spacing={1} sx={{ mb: 2, flexWrap: "wrap" }}>
                <TextField size="small" label="Numero" value={blocklistPhone} onChange={(e) => setBlocklistPhone(e.target.value)} />
                <TextField size="small" label="Notes" value={blocklistNotes} onChange={(e) => setBlocklistNotes(e.target.value)} />
                <Button type="submit" variant="contained" color="error" disabled={Boolean(submitting)}>
                  Bloquer
                </Button>
              </Stack>
              <CallerTable
                rows={blocklist}
                onRemove={(id) => {
                  setSubmitting(`b-${id}`);
                  removeFromBlocklist(id).then(load).catch((err) => setError(String(err))).finally(() => setSubmitting(null));
                }}
                submitting={submitting}
              />
            </VgSettingsSection>
          ) : null}

          {tab === "rules" ? (
            <VgSettingsSection
              title="Regles de blocage (base de donnees)"
              description="Ancien systeme prefixe/regex. Pour la policy runtime, utilise Patterns policy."
            >
              <Stack component="form" onSubmit={handleAddRule} direction="row" spacing={1} sx={{ mb: 2, flexWrap: "wrap" }}>
                <TextField size="small" label="Nom" value={ruleName} onChange={(e) => setRuleName(e.target.value)} />
                <TextField size="small" label="Prefixe" value={rulePattern} onChange={(e) => setRulePattern(e.target.value)} placeholder="089" />
                <Button type="submit" variant="contained" disabled={Boolean(submitting)}>
                  Ajouter
                </Button>
              </Stack>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Nom</TableCell>
                    <TableCell>Pattern</TableCell>
                    <TableCell>Type</TableCell>
                    <TableCell align="right" />
                  </TableRow>
                </TableHead>
                <TableBody>
                  {rules.map((r) => (
                    <TableRow key={r.id}>
                      <TableCell>{r.name}</TableCell>
                      <TableCell sx={{ fontFamily: "monospace" }}>{r.pattern}</TableCell>
                      <TableCell>{r.pattern_type}</TableCell>
                      <TableCell align="right">
                        <IconButton
                          size="small"
                          color="error"
                          disabled={Boolean(submitting)}
                          onClick={() => {
                            setSubmitting(`r-${r.id}`);
                            deleteBlockRule(r.id).then(load).finally(() => setSubmitting(null));
                          }}
                        >
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </VgSettingsSection>
          ) : null}
        </>
      )}
    </AppLayout>
  );
}

function CallerTable({
  rows,
  onRemove,
  submitting
}: {
  rows: Caller[];
  onRemove: (id: number) => void;
  submitting: string | null;
}) {
  return (
    <Table size="small">
      <TableHead>
        <TableRow>
          <TableCell>Numero</TableCell>
          <TableCell>Nom / notes</TableCell>
          <TableCell align="right">Action</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {rows.length === 0 ? (
          <TableRow>
            <TableCell colSpan={3}>
              <Typography variant="body2" color="text.secondary">
                Aucune entree.
              </Typography>
            </TableCell>
          </TableRow>
        ) : (
          rows.map((c) => (
            <TableRow key={c.id}>
              <TableCell>{c.phone_number}</TableCell>
              <TableCell>{c.name || c.notes || "—"}</TableCell>
              <TableCell align="right">
                <Button size="small" color="inherit" disabled={Boolean(submitting)} onClick={() => onRemove(c.id)}>
                  Retirer
                </Button>
              </TableCell>
            </TableRow>
          ))
        )}
      </TableBody>
    </Table>
  );
}
