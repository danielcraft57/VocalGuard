"use client";

import React, { useState } from "react";
import Link from "next/link";
import { Button, Stack, Tab, Tabs, Typography } from "@mui/material";
import ForumIcon from "@mui/icons-material/Forum";
import CampaignIcon from "@mui/icons-material/Campaign";
import { AppLayout } from "../../components/AppLayout";
import { KbTchatchePanel } from "../../components/kb/KbTchatchePanel";
import { KbVectorEngineChip } from "../../components/kb/KbVectorEngineChip";
import { CommercialSimulatorPanel } from "../../components/CommercialSimulatorPanel";
import { VgPageHeader } from "../../components/mui/VgPageHeader";

type SimTab = "inbound" | "outbound";

/**
 * Simulateur d'appel : entrant (tchatche) ou commercial sortant (HP).
 */
export default function SimulatorPage(): React.ReactElement {
  const [tab, setTab] = useState<SimTab>("outbound");

  return (
    <AppLayout title="Simulateur d'appel" hidePageHeader>
      <VgPageHeader
        title="Simulateur d'appel"
        subtitle={
          tab === "outbound"
            ? "Commercial sortant : QCM 1-5 et voix sur les haut-parleurs (sans modem)."
            : "Entrant : tchatche comme un appelant (pipeline repondeur)."
        }
        action={
          <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap", gap: 1, alignItems: "center" }}>
            <KbVectorEngineChip />
            <Button component={Link} href="/kb" size="small" variant="outlined">
              Base de connaissances
            </Button>
          </Stack>
        }
      />

      <Tabs
        value={tab}
        onChange={(_, v: SimTab) => setTab(v)}
        sx={{ mb: 2 }}
      >
        <Tab
          value="outbound"
          icon={<CampaignIcon fontSize="small" />}
          iconPosition="start"
          label="Commercial sortant"
        />
        <Tab
          value="inbound"
          icon={<ForumIcon fontSize="small" />}
          iconPosition="start"
          label="Entrant / Tchatche"
        />
      </Tabs>

      {tab === "outbound" ? (
        <>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Tchat commercial : tu joues le prospect, Marie répond (DanielCraft,
            un peu taquin, mini-jeu). En dessous, le co-pilote QCM 1-5 pour
            tester les voix sur les HP.
          </Typography>
          <KbTchatchePanel profile="outbound_commercial" />
          <Typography variant="subtitle2" sx={{ mt: 3, mb: 1, fontWeight: 600 }}>
            Co-pilote voix (clavier 1-5)
          </Typography>
          <CommercialSimulatorPanel />
        </>
      ) : (
        <>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Tape ce que dirait le prospect / appelant. Les reponses viennent de
            la KB (meme pipeline que le repondeur conversation).
          </Typography>
          <KbTchatchePanel />
        </>
      )}
    </AppLayout>
  );
}
