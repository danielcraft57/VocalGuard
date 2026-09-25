"use client";

import React from "react";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Stack,
  Typography
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";

export type VgCollapsibleAudioSectionProps = {
  /** Titre principal (ex. Intro musicale). */
  title: string;
  /** Sous-texte style maquette sous / a cote du titre. */
  description: string;
  /** Icone Material a gauche du titre. */
  icon?: React.ReactNode;
  /** Resume court a droite (ex. mode actif). */
  summary?: string;
  /** Ouvert par defaut (mode non controle). */
  defaultExpanded?: boolean;
  /** Ouverture controlee (si fourni avec onExpandedChange). */
  expanded?: boolean;
  /** Callback quand l'utilisateur ouvre / ferme. */
  onExpandedChange?: (expanded: boolean) => void;
  /** Contenu de la section. */
  children: React.ReactNode;
};

/**
 * Section audio repliable (style maquette Messages et audio).
 *
 * Titre + description + chevron, contenu detaille a l'ouverture.
 * Supporte mode controle (`expanded` + `onExpandedChange`) ou non controle.
 */
export function VgCollapsibleAudioSection({
  title,
  description,
  icon,
  summary,
  defaultExpanded = false,
  expanded,
  onExpandedChange,
  children
}: VgCollapsibleAudioSectionProps) {
  const controlled = typeof expanded === "boolean";

  return (
    <Accordion
      {...(controlled
        ? {
            expanded,
            onChange: (_: React.SyntheticEvent, next: boolean) => {
              onExpandedChange?.(next);
            }
          }
        : { defaultExpanded })}
      disableGutters
      elevation={0}
      sx={{
        border: 1,
        borderColor: "divider",
        borderRadius: 2,
        overflow: "hidden",
        bgcolor: "background.paper",
        "&:before": { display: "none" },
        "&.Mui-expanded": { margin: 0 }
      }}
    >
      <AccordionSummary
        expandIcon={<ExpandMoreIcon />}
        sx={{
          px: 2,
          py: 0.5,
          minHeight: 64,
          "& .MuiAccordionSummary-content": {
            my: 1.25,
            alignItems: "center",
            gap: 1.5
          }
        }}
      >
        <Stack
          direction="row"
          spacing={1.5}
          sx={{ alignItems: "center", flex: 1, minWidth: 0, pr: 1 }}
        >
          {icon}
          <Stack spacing={0.25} sx={{ minWidth: 0, flex: 1 }}>
            <Stack direction="row" spacing={1} sx={{ alignItems: "baseline", flexWrap: "wrap" }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                {title}
              </Typography>
              {summary ? (
                <Typography variant="caption" color="primary.main" sx={{ fontWeight: 600 }}>
                  {summary}
                </Typography>
              ) : null}
            </Stack>
            <Typography variant="body2" color="text.secondary">
              {description}
            </Typography>
          </Stack>
        </Stack>
      </AccordionSummary>
      <AccordionDetails sx={{ px: 2, pt: 0, pb: 2.5 }}>{children}</AccordionDetails>
    </Accordion>
  );
}
