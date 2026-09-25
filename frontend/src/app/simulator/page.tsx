"use client";

import React from "react";
import Link from "next/link";
import { Button, Stack, Typography } from "@mui/material";
import { AppLayout } from "../../components/AppLayout";
import { KbTchatchePanel } from "../../components/kb/KbTchatchePanel";
import { KbVectorEngineChip } from "../../components/kb/KbVectorEngineChip";
import { VgPageHeader } from "../../components/mui/VgPageHeader";

/**
 * Simulateur d'appel : Tchatche + historique des conversations.
 */
export default function SimulatorPage(): React.ReactElement {
  return (
    <AppLayout title="Simulateur d'appel" hidePageHeader>
      <VgPageHeader
        title="Simulateur d'appel"
        subtitle="Tchatche comme un appelant : intents, Qdrant, historique des conversations."
        action={
          <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap", gap: 1, alignItems: "center" }}>
            <KbVectorEngineChip />
            <Button component={Link} href="/kb" size="small" variant="outlined">
              Base de connaissances
            </Button>
          </Stack>
        }
      />
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Tape ce que dirait le prospect / appelant. Les reponses viennent de la KB
        (meme pipeline que le repondeur conversation).
      </Typography>
      <KbTchatchePanel />
    </AppLayout>
  );
}
