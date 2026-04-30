"use client";

import React, { useEffect, useMemo, useState } from "react";
import { AppLayout } from "../../components/AppLayout";
import {
  Alert,
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
  Switch,
  FormControlLabel,
} from "@mui/material";
import {
  createPublicToken,
  fetchPublicApiDocs,
  deletePublicToken,
  listPublicTokens,
  patchPublicToken,
  PublicApiDocsPayload,
  PublicApiToken,
  revealPublicToken,
  revokePublicToken,
} from "../../services/publicApiAdmin";

export default function ApiManagementPage() {
  const [docs, setDocs] = useState<PublicApiDocsPayload | null>(null);
  const [tokens, setTokens] = useState<PublicApiToken[]>([]);
  const [appUrl, setAppUrl] = useState("https://danielcraft.fr");
  const [canReadAgenda, setCanReadAgenda] = useState(true);
  const [canWriteAgenda, setCanWriteAgenda] = useState(true);
  const [canWriteEntreprises, setCanWriteEntreprises] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [revealMap, setRevealMap] = useState<Record<number, string>>({});
  const [showSystemTokens, setShowSystemTokens] = useState(false);
  const [expandedDoc, setExpandedDoc] = useState<string | null>(null);

  useEffect(() => {
    fetchPublicApiDocs().then(setDocs).catch(() => null);
  }, []);
  useEffect(() => {
    refreshTokens();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refreshTokens = async () => {
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const rows = await listPublicTokens();
      setTokens(rows);
      setSuccess(`${rows.length} token(s) chargé(s).`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Chargement impossible.");
    } finally {
      setBusy(false);
    }
  };

  const onCreate = async () => {
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const created = await createPublicToken({
        app_url: appUrl,
        can_read_agenda: canReadAgenda,
        can_write_agenda: canWriteAgenda,
        can_write_entreprises: canWriteEntreprises,
        can_manage_tokens: false,
      });
      setSuccess(`Token créé: ${created.name}. Clé: ${created.token ?? created.token_preview ?? "***"}`);
      await refreshTokens();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Création impossible.");
    } finally {
      setBusy(false);
    }
  };

  const onRevoke = async (tokenId: number) => {
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      await revokePublicToken(tokenId);
      setSuccess("Token révoqué.");
      await refreshTokens();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Révocation impossible.");
    } finally {
      setBusy(false);
    }
  };

  const onDelete = async (tokenId: number) => {
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      await deletePublicToken(tokenId);
      setSuccess("Token supprimé.");
      await refreshTokens();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Suppression impossible.");
    } finally {
      setBusy(false);
    }
  };

  const onReveal = async (tokenId: number) => {
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const row = await revealPublicToken(tokenId);
      const raw = row.token ?? "";
      setRevealMap((prev) => ({ ...prev, [tokenId]: raw }));
      setSuccess("Clé récupérée.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Impossible de voir la clé.");
    } finally {
      setBusy(false);
    }
  };

  const copyToClipboard = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setSuccess("Copié dans le presse-papier.");
    } catch {
      setError("Copie impossible (navigateur).");
    }
  };

  const togglePermission = async (
    tokenId: number,
    key: "can_read_agenda" | "can_write_agenda" | "can_write_entreprises",
    next: boolean,
  ) => {
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      await patchPublicToken(tokenId, { [key]: next } as any);
      await refreshTokens();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Modification impossible.");
    } finally {
      setBusy(false);
    }
  };

  const visibleTokens = useMemo(() => {
    if (showSystemTokens) return tokens;
    return tokens.filter((t) => !["bootstrap-admin", "local-token-manager"].includes((t.name || "").trim()));
  }, [showSystemTokens, tokens]);

  return (
    <AppLayout title="API publique" subtitle="Documentation, tokens et droits d'accès de l'API publique.">
      <Stack spacing={2}>
        <Card sx={{ borderRadius: 3, border: "1px solid var(--vg-color-border-subtle)" }}>
          <CardContent>
            <Typography variant="h6" sx={{ mb: 1 }}>
              Créer un token API public
            </Typography>
            <Typography sx={{ color: "var(--vg-color-text-muted)", mb: 2 }}>
              Tu mets juste l'URL du site qui va utiliser l'API. Le token est ensuite à envoyer en header `Authorization: Bearer ...`.
            </Typography>
            <Stack spacing={2}>
              <TextField
                label="URL du site"
                value={appUrl}
                onChange={(e) => setAppUrl(e.target.value)}
                fullWidth
                placeholder="https://danielcraft.fr"
              />
              <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
                <Chip
                  color={canReadAgenda ? "primary" : "default"}
                  variant={canReadAgenda ? "filled" : "outlined"}
                  label="Lire l'agenda"
                  onClick={() => setCanReadAgenda((v) => !v)}
                />
                <Chip
                  color={canWriteAgenda ? "primary" : "default"}
                  variant={canWriteAgenda ? "filled" : "outlined"}
                  label="Ecrire l'agenda"
                  onClick={() => setCanWriteAgenda((v) => !v)}
                />
                <Chip
                  color={canWriteEntreprises ? "primary" : "default"}
                  variant={canWriteEntreprises ? "filled" : "outlined"}
                  label="Ecrire les entreprises"
                  onClick={() => setCanWriteEntreprises((v) => !v)}
                />
              </Box>
              <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
                <Button variant="contained" onClick={onCreate} disabled={busy || !appUrl.trim()}>
                  Générer le token
                </Button>
                <Button variant="outlined" onClick={refreshTokens} disabled={busy}>
                  Rafraîchir
                </Button>
              </Box>
              {error ? <Alert severity="error">{error}</Alert> : null}
              {success ? <Alert severity="success">{success}</Alert> : null}
            </Stack>
          </CardContent>
        </Card>

        <Card sx={{ borderRadius: 3, border: "1px solid var(--vg-color-border-subtle)" }}>
          <CardContent>
            <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 2, flexWrap: "wrap" }}>
              <Box>
                <Typography variant="h6">Tokens existants</Typography>
                <Typography sx={{ color: "var(--vg-color-text-muted)" }}>
                  `bootstrap-admin` est un token système créé automatiquement quand il n'y avait aucun token au tout début. Il sert juste à démarrer la gestion.
                </Typography>
              </Box>
              <FormControlLabel
                control={<Switch checked={showSystemTokens} onChange={(e) => setShowSystemTokens(e.target.checked)} />}
                label="Afficher les tokens système"
              />
            </Box>
            <Divider sx={{ my: 2 }} />
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Nom</TableCell>
                  <TableCell>URL</TableCell>
                  <TableCell>Clé</TableCell>
                  <TableCell>Droits</TableCell>
                  <TableCell>Etat</TableCell>
                  <TableCell align="right">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {visibleTokens.map((item) => (
                  <TableRow key={item.id} hover>
                    <TableCell>{item.name}</TableCell>
                    <TableCell><code>{item.app_url ?? "-"}</code></TableCell>
                    <TableCell><code>{revealMap[item.id] ? revealMap[item.id] : (item.token_preview ?? "***")}</code></TableCell>
                    <TableCell>
                      <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap" }}>
                        <Chip
                          size="small"
                          label="Agenda lecture"
                          color={item.can_read_agenda ? "primary" : "default"}
                          variant={item.can_read_agenda ? "filled" : "outlined"}
                          onClick={() => togglePermission(item.id, "can_read_agenda", !item.can_read_agenda)}
                        />
                        <Chip
                          size="small"
                          label="Agenda écriture"
                          color={item.can_write_agenda ? "primary" : "default"}
                          variant={item.can_write_agenda ? "filled" : "outlined"}
                          onClick={() => togglePermission(item.id, "can_write_agenda", !item.can_write_agenda)}
                        />
                        <Chip
                          size="small"
                          label="Entreprises"
                          color={item.can_write_entreprises ? "primary" : "default"}
                          variant={item.can_write_entreprises ? "filled" : "outlined"}
                          onClick={() => togglePermission(item.id, "can_write_entreprises", !item.can_write_entreprises)}
                        />
                      </Stack>
                    </TableCell>
                    <TableCell>
                      {item.is_active ? <Chip size="small" color="success" label="Actif" /> : <Chip size="small" color="error" label="Inactif" />}
                    </TableCell>
                    <TableCell align="right">
                      <Button size="small" variant="outlined" onClick={() => onReveal(item.id)} disabled={busy}>Voir</Button>
                      <Button size="small" variant="outlined" onClick={() => copyToClipboard(revealMap[item.id] || item.token_preview || "")} disabled={busy} sx={{ ml: 1 }}>Copier</Button>
                      <Button size="small" color="warning" variant="contained" onClick={() => onRevoke(item.id)} disabled={busy || !item.is_active} sx={{ ml: 1 }}>Révoquer</Button>
                      <Button size="small" color="error" variant="contained" onClick={() => onDelete(item.id)} disabled={busy} sx={{ ml: 1 }}>Supprimer</Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <Card sx={{ borderRadius: 3, border: "1px solid var(--vg-color-border-subtle)" }}>
          <CardContent>
            <Typography variant="h6" sx={{ mb: 1 }}>Documentation API publique</Typography>
            <Typography sx={{ color: "var(--vg-color-text-muted)", mb: 2 }}>
              {docs ? `${docs.name} - Base: ${docs.base_url}` : "Chargement..."}
            </Typography>
            <Stack spacing={1}>
              {(docs?.endpoints || []).map((ep) => {
                const key = `${ep.method} ${ep.path}`;
                const open = expandedDoc === key;
                return (
                  <Accordion
                    key={key}
                    expanded={open}
                    onChange={() => setExpandedDoc(open ? null : key)}
                    disableGutters
                    sx={{
                      borderRadius: 2,
                      border: "1px solid var(--vg-color-border-subtle)",
                      background: "transparent",
                      "&:before": { display: "none" },
                    }}
                  >
                    <AccordionSummary
                      sx={{ px: 2, py: 0.5 }}
                      expandIcon={<span className="material-icons">expand_more</span>}
                    >
                      <Box sx={{ display: "flex", flexDirection: "column", gap: 0.3 }}>
                        <Typography sx={{ fontWeight: 800 }}>
                          <code>{ep.method}</code> <code>{ep.path}</code>
                        </Typography>
                        <Typography sx={{ color: "var(--vg-color-text-muted)" }}>
                          {ep.title ? ep.title : ep.permission}
                        </Typography>
                      </Box>
                    </AccordionSummary>
                    <AccordionDetails sx={{ px: 2, pb: 2, pt: 0 }}>
                      <Divider sx={{ mb: 1.5 }} />
                      {ep.description ? <Typography sx={{ mb: 1 }}>{ep.description}</Typography> : null}
                      <Typography sx={{ fontWeight: 700, mb: 0.5 }}>Permission</Typography>
                      <Typography sx={{ mb: 1 }}><code>{ep.permission}</code></Typography>
                      {ep.request ? (
                        <>
                          <Typography sx={{ fontWeight: 700, mb: 0.5 }}>Requête</Typography>
                          {ep.request.headers?.length ? (
                            <Typography sx={{ mb: 1 }}>
                              Headers: <code>{ep.request.headers.join(", ")}</code>
                            </Typography>
                          ) : null}
                          {ep.request.query && Object.keys(ep.request.query).length ? (
                            <Typography sx={{ mb: 1 }}>
                              Query: <code>{JSON.stringify(ep.request.query)}</code>
                            </Typography>
                          ) : null}
                          {ep.request.body ? (
                            <Box component="pre" sx={{ m: 0, p: 1.2, borderRadius: 2, bgcolor: "rgba(148,163,184,0.08)", overflow: "auto" }}>
                              {JSON.stringify(ep.request.body, null, 2)}
                            </Box>
                          ) : null}
                        </>
                      ) : null}
                      {ep.responses ? (
                        <>
                          <Typography sx={{ fontWeight: 700, mt: 2, mb: 0.5 }}>Réponses</Typography>
                          {Object.entries(ep.responses).map(([code, payload]) => (
                            <Box key={code} sx={{ mb: 1 }}>
                              <Typography sx={{ mb: 0.5 }}><code>{code}</code></Typography>
                              {payload?.example !== undefined ? (
                                <Box component="pre" sx={{ m: 0, p: 1.2, borderRadius: 2, bgcolor: "rgba(148,163,184,0.08)", overflow: "auto" }}>
                                  {JSON.stringify(payload.example, null, 2)}
                                </Box>
                              ) : null}
                            </Box>
                          ))}
                        </>
                      ) : null}
                    </AccordionDetails>
                  </Accordion>
                );
              })}
            </Stack>
          </CardContent>
        </Card>
      </Stack>
    </AppLayout>
  );
}
