"use client";

import React from "react";
import { Card, CardContent, Stack, Typography } from "@mui/material";

export type VgSettingsSectionProps = {
  title: string;
  description?: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
};

/**
 * Section de parametres dans une Card Material.
 */
export function VgSettingsSection({
  title,
  description,
  icon,
  children
}: VgSettingsSectionProps) {
  return (
    <Card sx={{ mb: 2 }}>
      <CardContent>
        <Stack
          direction="row"
          spacing={1}
          sx={{ mb: description ? 0.5 : 1.5, alignItems: "center" }}
        >
          {icon}
          <Typography variant="h6" component="h2">
            {title}
          </Typography>
        </Stack>
        {description ? (
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            {description}
          </Typography>
        ) : null}
        {children}
      </CardContent>
    </Card>
  );
}
