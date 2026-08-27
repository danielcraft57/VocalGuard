"use client";

import React from "react";
import { Box, Stack, Typography } from "@mui/material";

export type VgPageHeaderProps = {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
};

/**
 * En-tete de page Material (titre + sous-titre + action optionnelle).
 */
export function VgPageHeader({ title, subtitle, action }: VgPageHeaderProps) {
  return (
    <Stack
      direction={{ xs: "column", sm: "row" }}
      spacing={1}
      sx={{
        mb: 3,
        justifyContent: "space-between",
        alignItems: { xs: "flex-start", sm: "center" }
      }}
    >
      <Box>
        <Typography variant="h5" component="h1">
          {title}
        </Typography>
        {subtitle ? (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            {subtitle}
          </Typography>
        ) : null}
      </Box>
      {action ? <Box>{action}</Box> : null}
    </Stack>
  );
}
