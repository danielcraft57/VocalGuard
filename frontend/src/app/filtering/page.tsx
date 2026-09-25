"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  Alert,
  Box,
  Button,
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
import { VgSoftSyncBar } from "../../components/mui/VgSoftSyncBar";
import { VgTableSkeleton } from "../../components/mui/VgListSkeleton";
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
import {
  isAbortError,
  isUiCacheFresh,
  loadUiCache,
  saveUiCache,
  UI_CACHE_KEYS
} from "../../services/uiPersist";

type TabKey = "whitelist" | "blocklist" | "rules";

/**
 * Filtrage Material : listes blanche/noire et regles DB (motifs legacy).
 * Hydrate depuis le cache session puis soft-sync reseau.
 */
export default function FilteringPage() {
  const [tab, setTab] = useState<TabKey>("whitelist");
  const cachedW = loadUiCache<Caller[]>(UI_CACHE_KEYS.whitelist);
  const cachedB = loadUiCache<Caller[]>(UI_CACHE_KEYS.blocklist);
  const cachedR = loadUiCache<BlockRule[]>(UI_CACHE_KEYS.blockRules);
  const [whitelist, setWhitelist] = useState<Caller[]>(() => cachedW ?? []);
  const [blocklist, setBlocklist] = useState<Caller[]>(() => cachedB ?? []);
  const [rules, setRules] = useState<BlockRule[]>(() => cachedR ?? []);
  const hasCache =
    Array.isArray(cachedW) || Array.isArray(cachedB) || Array.isArray(cachedR);
  const [loading, setLoading] = useState(() => !hasCache);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const [whitelistPhone, setWhitelistPhone] = useState("");
  const [whitelistName, setWhitelistName] = useState("");
  const [blocklistPhone, setBlocklistPhone] = useState("");
  const [blocklistNotes, setBlocklistNotes] = useState("");
  const [ruleName, setRuleName] = useState("");
  const [rulePattern, setRulePattern] = useState("");

  /**
   * Charge whitelist / blocklist / rules avec soft sync et abort.
   *
   * @param opts.soft Force le mode soft (garde l'UI, bandeau sync).
   * @param opts.force Ignore le TTL et refetch.
   */
  const load = useCallback(async (opts?: { soft?: boolean; force?: boolean }) => {
    const w0 = loadUiCache<Caller[]>(UI_CACHE_KEYS.whitelist);
    const b0 = loadUiCache<Caller[]>(UI_CACHE_KEYS.blocklist);
    const r0 = loadUiCache<BlockRule[]>(UI_CACHE_KEYS.blockRules);
    const already =
      Array.isArray(w0) || Array.isArray(b0) || Array.isArray(r0);

    const allFresh =
      isUiCacheFresh(UI_CACHE_KEYS.whitelist) &&
      isUiCacheFresh(UI_CACHE_KEYS.blocklist) &&
      isUiCacheFresh(UI_CACHE_KEYS.blockRules);

    if (!opts?.force && already && allFresh) {
      if (Array.isArray(w0)) setWhitelist(w0);
      if (Array.isArray(b0)) setBlocklist(b0);
      if (Array.isArray(r0)) setRules(r0);
      setLoading(false);
      setSyncing(false);
      return;
    }

    const soft = Boolean(opts?.soft) || already;
    if (soft) setSyncing(true);
    else setLoading(true);
    setError(null);

    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    try {
      const [w, b, r] = await Promise.all([
        fetchWhitelist(ac.signal),
        fetchBlocklist(ac.signal),
        fetchBlockRules(ac.signal)
      ]);
      if (ac.signal.aborted) return;
      setWhitelist(w);
      setBlocklist(b);
      setRules(r);
      saveUiCache(UI_CACHE_KEYS.whitelist, w);
      saveUiCache(UI_CACHE_KEYS.blocklist, b);
      saveUiCache(UI_CACHE_KEYS.blockRules, r);
    } catch (e) {
      if (isAbortError(e) || ac.signal.aborted) return;
      if (!already) {
        setError(e instanceof Error ? e.message : "Erreur de chargement");
      }
    } finally {
      if (!ac.signal.aborted) {
        setLoading(false);
        setSyncing(false);
      }
    }
  }, []);

  useEffect(() => {
    void load({ soft: hasCache });
    return () => {
      abortRef.current?.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount once
  }, []);

  const handleAddWhitelist = async (e: React.FormEvent) => {
    e.preventDefault();
    const phone = whitelistPhone.trim().replace(/\s/g, "");
    if (!phone) return;
    setSubmitting("whitelist");
    try {
      await addToWhitelist(phone, whitelistName.trim() || null, null);
      setWhitelistPhone("");
      setWhitelistName("");
      await load({ soft: true, force: true });
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
      await load({ soft: true, force: true });
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
      await load({ soft: true, force: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur");
    } finally {
      setSubmitting(null);
    }
  };

  const showSkeleton = loading && !hasCache && whitelist.length === 0 && blocklist.length === 0 && rules.length === 0;

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

      {syncing ? (
        <Box sx={{ display: "flex", justifyContent: "flex-end", mb: 1 }}>
          <VgSoftSyncBar label="Synchro filtrage…" />
        </Box>
      ) : null}

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

      {showSkeleton ? (
        <VgTableSkeleton rows={6} />
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
                  removeFromWhitelist(id)
                    .then(() => load({ soft: true, force: true }))
                    .catch((err) => setError(String(err)))
                    .finally(() => setSubmitting(null));
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
                  removeFromBlocklist(id)
                    .then(() => load({ soft: true, force: true }))
                    .catch((err) => setError(String(err)))
                    .finally(() => setSubmitting(null));
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
                            deleteBlockRule(r.id)
                              .then(() => load({ soft: true, force: true }))
                              .finally(() => setSubmitting(null));
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

/**
 * Tableau simple des callers (whitelist / blocklist).
 *
 * @param props.rows Lignes a afficher.
 * @param props.onRemove Callback retrait.
 * @param props.submitting Cle d'action en cours.
 */
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
              <TableCell>{c.name || c.notes || "-"}</TableCell>
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
