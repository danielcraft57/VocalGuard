import React from "react";
import {
  Button,
  Checkbox,
  Chip,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
} from "@mui/material";
import type { Entreprise } from "../../../services/entreprisesApi";

export function EntreprisesListTable(props: {
  rows: Entreprise[];
  selectedIds: number[];
  onToggleSelected: (id: number) => void;
  onToggleSelectAll: () => void;
  onApplyCityFilter: (city: string | null | undefined) => void;
  onApplyCategoryFilter: (category: string | null | undefined) => void;
  onOpenDetails: (row: Entreprise) => void;
  onDeleteRow: (id: number) => void;
}) {
  const allSelected = props.rows.length > 0 && props.selectedIds.length === props.rows.length;

  return (
    <TableContainer
      component={Paper}
      sx={{
        mt: 1.25,
        borderRadius: 3,
        overflow: "hidden",
        border: "1px solid var(--vg-color-border-subtle)",
        bgcolor: "var(--vg-color-bg-soft)",
        color: "var(--vg-color-text)",
      }}
    >
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell padding="checkbox">
              <Checkbox
                checked={allSelected}
                onChange={props.onToggleSelectAll}
                size="small"
                sx={{ color: "var(--vg-color-text-muted)", "&.Mui-checked": { color: "var(--vg-color-primary)" } }}
              />
            </TableCell>
            <TableCell>Nom</TableCell>
            <TableCell>Téléphone</TableCell>
            <TableCell>Ville</TableCell>
            <TableCell>Catégorie</TableCell>
            <TableCell align="right">Actions</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {props.rows.map((e) => (
            <TableRow key={e.id} hover sx={{ transition: "background-color .15s ease" }}>
              <TableCell padding="checkbox">
                <Checkbox
                  checked={props.selectedIds.includes(e.id)}
                  onChange={() => props.onToggleSelected(e.id)}
                  size="small"
                  sx={{ color: "var(--vg-color-text-muted)", "&.Mui-checked": { color: "var(--vg-color-primary)" } }}
                />
              </TableCell>
              <TableCell sx={{ fontWeight: 600 }}>{e.name}</TableCell>
              <TableCell>{e.phone_number ?? "-"}</TableCell>
              <TableCell>
                {e.city ? (
                  <Chip label={e.city} size="small" clickable color="primary" variant="outlined" onClick={() => props.onApplyCityFilter(e.city)} />
                ) : (
                  "-"
                )}
              </TableCell>
              <TableCell>
                {e.categories?.length ? (
                  <Chip
                    label={e.categories[0]}
                    size="small"
                    clickable
                    color="secondary"
                    variant="outlined"
                    onClick={() => props.onApplyCategoryFilter(e.categories?.[0])}
                  />
                ) : (
                  "-"
                )}
              </TableCell>
              <TableCell align="right">
                <Stack direction="row" spacing={1} sx={{ justifyContent: "flex-end" }}>
                  <Button
                    size="small"
                    variant="outlined"
                    startIcon={<span className="material-icons" style={{ fontSize: 18 }}>visibility</span>}
                    onClick={() => props.onOpenDetails(e)}
                    sx={{ borderRadius: 999, textTransform: "none" }}
                  >
                    Détails
                  </Button>
                  <Button
                    size="small"
                    variant="contained"
                    color="error"
                    startIcon={<span className="material-icons" style={{ fontSize: 18 }}>delete_outline</span>}
                    onClick={() => props.onDeleteRow(e.id)}
                    sx={{ borderRadius: 999, textTransform: "none" }}
                  >
                    Supprimer
                  </Button>
                </Stack>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

