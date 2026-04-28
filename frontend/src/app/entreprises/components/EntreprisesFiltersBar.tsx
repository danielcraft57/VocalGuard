import React from "react";
import { Button, MenuItem, Stack, TextField } from "@mui/material";
import type { PhoneAvailabilityFilter } from "../types";

export function EntreprisesFiltersBar(props: {
  searchText: string;
  onSearchTextChange: (v: string) => void;
  city: string;
  onCityChange: (v: string) => void;
  category: string;
  onCategoryChange: (v: string) => void;
  phoneFilter: PhoneAvailabilityFilter;
  onPhoneFilterChange: (v: PhoneAvailabilityFilter) => void;
  pageSize: number;
  onPageSizeChange: (v: number) => void;
  loading: boolean;
  selectedCount: number;
  onRefresh: () => void;
  onDeleteSelection: () => void;
}) {
  return (
    <Stack direction="row" sx={{ gap: 1, flexWrap: "wrap", alignItems: "center", mt: 1.25 }}>
      <TextField
        size="small"
        value={props.searchText}
        onChange={(e) => props.onSearchTextChange(e.target.value)}
        placeholder="Filtre: nom / tel / adresse / catégorie..."
        sx={{
          minWidth: 280,
          "& .MuiOutlinedInput-root": {
            bgcolor: "var(--vg-color-surface)",
            color: "var(--vg-color-text)",
          },
        }}
      />
      <TextField
        size="small"
        value={props.city}
        onChange={(e) => props.onCityChange(e.target.value)}
        placeholder="Ville"
        sx={{ width: 170, "& .MuiOutlinedInput-root": { bgcolor: "var(--vg-color-surface)", color: "var(--vg-color-text)" } }}
      />
      <TextField
        size="small"
        value={props.category}
        onChange={(e) => props.onCategoryChange(e.target.value)}
        placeholder="Catégorie"
        sx={{ width: 170, "& .MuiOutlinedInput-root": { bgcolor: "var(--vg-color-surface)", color: "var(--vg-color-text)" } }}
      />
      <TextField
        size="small"
        select
        value={props.phoneFilter}
        onChange={(e) => props.onPhoneFilterChange(e.target.value as PhoneAvailabilityFilter)}
        sx={{ width: 160, "& .MuiOutlinedInput-root": { bgcolor: "var(--vg-color-surface)", color: "var(--vg-color-text)" } }}
      >
        <MenuItem value="">Téléphone: tous</MenuItem>
        <MenuItem value="true">Téléphone: oui</MenuItem>
        <MenuItem value="false">Téléphone: non</MenuItem>
      </TextField>
      <TextField
        size="small"
        select
        value={String(props.pageSize)}
        onChange={(e) => props.onPageSizeChange(Number(e.target.value))}
        sx={{ width: 120, "& .MuiOutlinedInput-root": { bgcolor: "var(--vg-color-surface)", color: "var(--vg-color-text)" } }}
      >
        <MenuItem value="25">25 / page</MenuItem>
        <MenuItem value="50">50 / page</MenuItem>
        <MenuItem value="100">100 / page</MenuItem>
      </TextField>
      <Button variant="outlined" startIcon={<span className="material-icons" style={{ fontSize: 18 }}>refresh</span>} onClick={props.onRefresh} disabled={props.loading}>
        Rafraîchir
      </Button>
      <Button
        variant="contained"
        color="error"
        startIcon={<span className="material-icons" style={{ fontSize: 18 }}>delete_sweep</span>}
        onClick={props.onDeleteSelection}
        disabled={props.selectedCount === 0 || props.loading}
      >
        Supprimer ({props.selectedCount})
      </Button>
    </Stack>
  );
}

