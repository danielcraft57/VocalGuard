import React from "react";
import { Button, ButtonGroup, Stack, Typography } from "@mui/material";
import type { AgendaView } from "../types";

interface AgendaToolbarProps {
  view: AgendaView;
  onViewChange: (view: AgendaView) => void;
  periodLabel: string;
  onToday: () => void;
  onPrev: () => void;
  onNext: () => void;
}

export function AgendaToolbar(props: AgendaToolbarProps) {
  const { view, onViewChange, periodLabel, onToday, onPrev, onNext } = props;

  return (
    <Stack
      direction={{ xs: "column", md: "row" }}
      spacing={1}
      sx={{
        p: 1,
        border: "1px solid var(--vg-color-border-subtle)",
        borderRadius: 2,
        background: "var(--vg-color-surface)",
        alignItems: { xs: "stretch", md: "center" },
        justifyContent: "space-between"
      }}
    >
      <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
        <Button variant="contained" size="small" onClick={onToday}>Aujourd'hui</Button>
        <ButtonGroup size="small" variant="outlined">
          <Button onClick={onPrev}>{"<"}</Button>
          <Button onClick={onNext}>{">"}</Button>
        </ButtonGroup>
        <Typography variant="h6" sx={{ textTransform: "capitalize", fontSize: "1.05rem" }}>
          {periodLabel}
        </Typography>
      </Stack>

      <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
        <ButtonGroup size="small" variant="outlined">
          <Button variant={view === "day" ? "contained" : "outlined"} onClick={() => onViewChange("day")}>Jour</Button>
          <Button variant={view === "week" ? "contained" : "outlined"} onClick={() => onViewChange("week")}>Semaine</Button>
          <Button variant={view === "month" ? "contained" : "outlined"} onClick={() => onViewChange("month")}>Mois</Button>
        </ButtonGroup>
      </Stack>
    </Stack>
  );
}
