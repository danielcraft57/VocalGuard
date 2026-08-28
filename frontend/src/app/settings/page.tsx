"use client";

import React from "react";
import Link from "next/link";
import {
  Box,
  Card,
  CardActionArea,
  CardContent,
  CircularProgress,
  Grid,
  Stack,
  Typography
} from "@mui/material";
import FilterListIcon from "@mui/icons-material/FilterList";
import PatternIcon from "@mui/icons-material/Pattern";
import PhoneInTalkIcon from "@mui/icons-material/PhoneInTalk";
import RecordVoiceOverIcon from "@mui/icons-material/RecordVoiceOver";
import SettingsIcon from "@mui/icons-material/Settings";
import TuneIcon from "@mui/icons-material/Tune";
import VoicemailIcon from "@mui/icons-material/Voicemail";
import { AppLayout } from "../../components/AppLayout";
import { VgPageHeader } from "../../components/mui/VgPageHeader";
import { VgProfileChip } from "../../components/mui/VgProfileChip";
import { useIncomingCallConfig } from "../../hooks/useIncomingCallConfig";

type HubTile = {
  href: string;
  title: string;
  description: string;
  icon: React.ReactNode;
  ready: boolean;
};

const TILES: HubTile[] = [
  {
    href: "/settings/incoming-line",
    title: "Ligne entrante",
    description: "Repondeur, telephone parallele, whitelist ring-only",
    icon: <PhoneInTalkIcon color="primary" />,
    ready: true
  },
  {
    href: "/settings/incoming-profiles",
    title: "Profils et sonneries",
    description: "Autorises, inconnus, bloques — actions et rings",
    icon: <FilterListIcon color="primary" />,
    ready: true
  },
  {
    href: "/settings/incoming-audio",
    title: "Messages et audio",
    description: "Accueil TTS ou WAV, message bloque, bip",
    icon: <RecordVoiceOverIcon color="primary" />,
    ready: true
  },
  {
    href: "/settings/voicemail",
    title: "Messagerie et DTMF",
    description: "Filtre anti-robots, duree enregistrement",
    icon: <VoicemailIcon color="primary" />,
    ready: true
  },
  {
    href: "/settings/number-patterns",
    title: "Patterns numeros",
    description: "Regles par masque (+338%, masque P…)",
    icon: <PatternIcon color="primary" />,
    ready: true
  },
  {
    href: "/settings/incoming-advanced",
    title: "Avance",
    description: "CID, cadence ring, config effective JSON",
    icon: <TuneIcon color="primary" />,
    ready: true
  }
];

/**
 * Hub parametres Material (tuiles navigation).
 */
export default function SettingsHubPage() {
  const { config, loading } = useIncomingCallConfig();

  return (
    <AppLayout
      title="Parametres"
      subtitle="Configuration telephonie, messages et filtrage."
      hidePageHeader
    >
      <VgPageHeader
        title="Parametres"
        subtitle="Gere la ligne entrante, les profils appelants et l'audio."
        action={<SettingsIcon color="action" />}
      />

      {loading ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
          <CircularProgress />
        </Box>
      ) : config ? (
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap", gap: 1 }}>
              <Typography variant="body2" color="text.secondary">
                Mode actif :
              </Typography>
              <VgProfileChip
                profile={config.incoming_line_mode === "phone" ? "permitted" : "screened"}
              />
              <Typography variant="body2" color="text.secondary">
                {config.incoming_line_mode === "voicemail"
                  ? "Repondeur (coupe sonnerie)"
                  : "Telephone (fixe seul)"}
              </Typography>
            </Stack>
          </CardContent>
        </Card>
      ) : null}

      <Grid container spacing={2}>
        {TILES.map((tile) => (
          <Grid key={tile.href} size={{ xs: 12, sm: 6, md: 4 }}>
            <Card sx={{ opacity: tile.ready ? 1 : 0.72 }}>
              <CardActionArea component={Link} href={tile.href} disabled={!tile.ready}>
                <CardContent>
                  <Stack spacing={1}>
                    {tile.icon}
                    <Typography variant="h6">{tile.title}</Typography>
                    <Typography variant="body2" color="text.secondary">
                      {tile.description}
                    </Typography>
                    {!tile.ready ? (
                      <Typography variant="caption" color="text.secondary">
                        Bientot disponible
                      </Typography>
                    ) : null}
                  </Stack>
                </CardContent>
              </CardActionArea>
            </Card>
          </Grid>
        ))}
      </Grid>
    </AppLayout>
  );
}
