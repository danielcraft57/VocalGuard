"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { QRCodeSVG } from "qrcode.react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  FormControl,
  Grid,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Step,
  StepContent,
  StepLabel,
  Stepper,
  Typography,
} from "@mui/material";
import SmartphoneIcon from "@mui/icons-material/Smartphone";
import QrCode2Icon from "@mui/icons-material/QrCode2";
import RefreshIcon from "@mui/icons-material/Refresh";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import CancelIcon from "@mui/icons-material/Cancel";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import NetworkCheckIcon from "@mui/icons-material/NetworkCheck";
import CloudQueueIcon from "@mui/icons-material/CloudQueue";
import ScheduleIcon from "@mui/icons-material/Schedule";
import ApiIcon from "@mui/icons-material/Api";
import { AppLayout } from "../../components/AppLayout";
import { VgPageHeader } from "../../components/mui/VgPageHeader";
import { VgSettingsSection } from "../../components/mui/VgSettingsSection";
import { listPublicTokens, PublicApiToken, revealPublicToken } from "../../services/publicApiAdmin";
import {
  createPairingSession,
  MobilePairingSession,
  MobilePingResult,
  testMobilePing,
} from "../../services/mobilePairingApi";

const PAIRING_STEPS = [
  {
    title: "Ouvre l'application VocalGuard",
    body: "Sur ton telephone, lance l'app et va sur l'ecran d'appairage (scan QR).",
  },
  {
    title: "Choisis un token d'acces",
    body: "Laisse « Creer automatiquement » pour un token mobile avec toutes les permissions utiles.",
  },
  {
    title: "Scanne le QR code",
    body: "Clique sur Generer, scanne le code affiche a droite : la connexion se fait en quelques secondes.",
  },
];

type ServiceStatusProps = {
  label: string;
  ok: boolean;
  okLabel: string;
  koLabel: string;
};

/**
 * Affiche l'etat d'un service (API, WebSocket, modem) sous forme de puce Material.
 */
function ServiceStatusChip({ label, ok, okLabel, koLabel }: ServiceStatusProps) {
  return (
    <Stack
      direction="row"
      sx={{
        alignItems: "center",
        justifyContent: "space-between",
        p: 1.25,
        borderRadius: 1,
        bgcolor: "action.hover",
      }}
    >
      <Typography variant="body2" sx={{ fontWeight: 500 }}>
        {label}
      </Typography>
      <Chip
        size="small"
        icon={ok ? <CheckCircleIcon /> : <CancelIcon />}
        label={ok ? okLabel : koLabel}
        color={ok ? "success" : "error"}
        variant="outlined"
      />
    </Stack>
  );
}

/**
 * Page d'appairage mobile : QR code ephemere pour lier le smartphone au serveur VocalGuard.
 */
export default function MobileAppPage() {
  const [tokens, setTokens] = useState<PublicApiToken[]>([]);
  const [selectedTokenId, setSelectedTokenId] = useState<number | "auto">("auto");
  const [pairing, setPairing] = useState<MobilePairingSession | null>(null);
  const [ping, setPing] = useState<MobilePingResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const resolveBaseUrl = (): string => {
    if (typeof window === "undefined") return "";
    return window.location.origin.replace(/\/$/, "");
  };

  const mobileTokens = useMemo(() => tokens.filter((t) => t.is_active), [tokens]);

  const refreshTokens = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const rows = await listPublicTokens();
      setTokens(rows);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Impossible de charger les tokens d'API.";
      setError(message.includes("(401)") ? "Session expiree : reconnecte-toi sur /login." : message);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    refreshTokens();
  }, [refreshTokens]);

  const onGenerateQr = async () => {
    setBusy(true);
    setError(null);
    setSuccess(null);
    setPing(null);
    try {
      const base = resolveBaseUrl();
      if (!base) {
        throw new Error("Impossible de detecter l'adresse du serveur.");
      }
      const payload =
        selectedTokenId === "auto"
          ? { base_url: base, create_token_if_missing: true, token_name: "Token mobile" }
          : { base_url: base, api_token_id: selectedTokenId };
      const session = await createPairingSession(payload);
      setPairing(session);
      setSuccess("QR pret : scanne-le depuis l'app (valide 20 minutes).");
    } catch (err) {
      setPairing(null);
      const message = err instanceof Error ? err.message : "Generation QR impossible.";
      setError(message.includes("(401)") ? "Connecte-toi sur /login puis reviens ici." : message);
    } finally {
      setBusy(false);
    }
  };

  const onTestPing = async () => {
    setBusy(true);
    setError(null);
    setPing(null);
    try {
      let bearer: string | null = null;
      if (selectedTokenId !== "auto") {
        const revealed = await revealPublicToken(selectedTokenId);
        bearer = revealed.token ?? null;
      } else if (mobileTokens.length > 0) {
        const revealed = await revealPublicToken(mobileTokens[0].id);
        bearer = revealed.token ?? null;
      }
      if (!bearer) {
        throw new Error("Genere d'abord un QR pour creer un token mobile.");
      }
      const result = await testMobilePing(bearer);
      setPing(result);
      if (result.ok) {
        setSuccess("Connexion serveur OK.");
      } else {
        setError("Un ou plusieurs services ne repondent pas correctement.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Test ping impossible.");
    } finally {
      setBusy(false);
    }
  };

  const copyFallback = async () => {
    if (!pairing) return;
    try {
      await navigator.clipboard.writeText(`${pairing.qr_uri}\nCode: ${pairing.code}`);
      setSuccess("Lien et code copies.");
    } catch {
      setError("Copie impossible sur ce navigateur.");
    }
  };

  return (
    <AppLayout title="App mobile" subtitle="Appairage securise du smartphone VocalGuard.">
      <VgPageHeader
        title="App mobile"
        subtitle="Notifications, messages vocaux et sync en temps reel sur ton telephone."
        action={
          <Button
            component={Link}
            href="/api-doc"
            variant="outlined"
            size="small"
            startIcon={<ApiIcon />}
            sx={{ textTransform: "none", borderRadius: 999 }}
          >
            API publique
          </Button>
        }
      />

      <Stack spacing={2} sx={{ mb: 3 }}>
        {error ? (
          <Alert severity="error" onClose={() => setError(null)}>
            {error}
          </Alert>
        ) : null}
        {success && !error ? (
          <Alert severity="success" onClose={() => setSuccess(null)}>
            {success}
          </Alert>
        ) : null}
      </Stack>

      <Grid container spacing={3}>
        <Grid size={{ xs: 12, lg: 7 }}>
          <Stack spacing={2}>
            <VgSettingsSection
              title="Comment appairer ton telephone"
              description="Ta session web suffit : pas besoin de coller une URL ou un token admin."
              icon={<SmartphoneIcon color="primary" fontSize="small" />}
            >
              <Stepper orientation="vertical" activeStep={pairing ? 3 : 0}>
                {PAIRING_STEPS.map((step) => (
                  <Step key={step.title} expanded>
                    <StepLabel>{step.title}</StepLabel>
                    <StepContent>
                      <Typography variant="body2" color="text.secondary">
                        {step.body}
                      </Typography>
                    </StepContent>
                  </Step>
                ))}
              </Stepper>
            </VgSettingsSection>

            <VgSettingsSection
              title="Configuration"
              description="Le token mobile autorise l'app a lire les appels, messages et evenements live."
              icon={<QrCode2Icon color="info" fontSize="small" />}
            >
              <Stack spacing={2.5}>
                <FormControl fullWidth size="small">
                  <InputLabel id="token-select-label">Token mobile</InputLabel>
                  <Select
                    labelId="token-select-label"
                    id="vg-mobile-token-select"
                    value={selectedTokenId === "auto" ? "auto" : String(selectedTokenId)}
                    label="Token mobile"
                    onChange={(e) => {
                      const v = e.target.value;
                      setSelectedTokenId(v === "auto" ? "auto" : Number(v));
                    }}
                  >
                    <MenuItem value="auto">Creer un token mobile automatiquement (recommande)</MenuItem>
                    {mobileTokens.map((t) => (
                      <MenuItem key={t.id} value={String(t.id)}>
                        {t.name} (#{t.id})
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>

                <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} useFlexGap sx={{ flexWrap: "wrap" }}>
                  <Button
                    variant="contained"
                    onClick={onGenerateQr}
                    disabled={busy}
                    startIcon={busy ? <CircularProgress size={18} color="inherit" /> : <QrCode2Icon />}
                    sx={{ textTransform: "none", borderRadius: 999, px: 3 }}
                  >
                    {busy ? "Generation..." : "Generer le QR code"}
                  </Button>
                  <Button
                    variant="outlined"
                    onClick={onTestPing}
                    disabled={busy}
                    startIcon={<NetworkCheckIcon />}
                    sx={{ textTransform: "none", borderRadius: 999 }}
                  >
                    Tester la connexion
                  </Button>
                  <Button
                    variant="text"
                    onClick={refreshTokens}
                    disabled={busy}
                    startIcon={<RefreshIcon />}
                    sx={{ textTransform: "none", borderRadius: 999 }}
                  >
                    Actualiser
                  </Button>
                </Stack>
              </Stack>
            </VgSettingsSection>
          </Stack>
        </Grid>

        <Grid size={{ xs: 12, lg: 5 }}>
          <Box sx={{ position: { lg: "sticky" }, top: { lg: 88 } }}>
            <Stack spacing={2}>
              {pairing ? (
                <Card variant="outlined" sx={{ textAlign: "center" }}>
                  <CardContent sx={{ p: 3 }}>
                    <Typography variant="h6" sx={{ fontWeight: 600, mb: 1 }}>
                      QR code d'appairage
                    </Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                      Scanne avec l'app VocalGuard ou entre le code manuellement.
                    </Typography>

                    <Paper
                      variant="outlined"
                      sx={{
                        p: 2,
                        display: "inline-block",
                        bgcolor: "#fff",
                        mb: 2,
                      }}
                    >
                      <QRCodeSVG value={pairing.qr_uri} size={220} level="M" includeMargin={false} />
                    </Paper>

                    <Box
                      sx={{
                        px: 2,
                        py: 1.5,
                        mb: 2,
                        borderRadius: 1,
                        bgcolor: "action.hover",
                      }}
                    >
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                        Code manuel
                      </Typography>
                      <Typography
                        variant="h5"
                        sx={{
                          fontWeight: 700,
                          letterSpacing: 2,
                          fontFamily: "monospace",
                          color: "primary.main",
                        }}
                      >
                        {pairing.code}
                      </Typography>
                    </Box>

                    <Stack
                      direction="row"
                      spacing={0.5}
                      sx={{ justifyContent: "center", alignItems: "center", mb: 2 }}
                    >
                      <ScheduleIcon fontSize="small" color="action" />
                      <Typography variant="caption" color="text.secondary">
                        Expire le {new Date(pairing.expires_at).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" })}
                      </Typography>
                    </Stack>

                    <Button
                      fullWidth
                      variant="contained"
                      color="info"
                      onClick={copyFallback}
                      startIcon={<ContentCopyIcon />}
                      sx={{ textTransform: "none", borderRadius: 999 }}
                    >
                      Copier lien et code
                    </Button>
                  </CardContent>
                </Card>
              ) : (
                <Card
                  variant="outlined"
                  sx={{
                    minHeight: 320,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    borderStyle: "dashed",
                  }}
                >
                  <CardContent sx={{ textAlign: "center", maxWidth: 300 }}>
                    <QrCode2Icon sx={{ fontSize: 56, color: "action.disabled", mb: 1 }} />
                    <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>
                      Aucun QR actif
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Clique sur « Generer le QR code » pour afficher le code a scanner.
                    </Typography>
                  </CardContent>
                </Card>
              )}

              {ping ? (
                <VgSettingsSection
                  title="Diagnostic connexion"
                  icon={<CloudQueueIcon color="primary" fontSize="small" />}
                >
                  <Stack spacing={1} divider={<Divider flexItem />}>
                    <ServiceStatusChip label="API" ok={ping.api_ok} okLabel="OK" koLabel="Erreur" />
                    <ServiceStatusChip label="WebSocket" ok={ping.ws_ok} okLabel="Connecte" koLabel="Hors ligne" />
                    <ServiceStatusChip label="Modem" ok={ping.modem_ok} okLabel="Pret" koLabel="Indisponible" />
                  </Stack>
                </VgSettingsSection>
              ) : null}
            </Stack>
          </Box>
        </Grid>
      </Grid>
    </AppLayout>
  );
}
