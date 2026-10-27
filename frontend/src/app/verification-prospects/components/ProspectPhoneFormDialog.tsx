"use client";

import React, { useState } from "react";
import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Stack,
  TextField,
} from "@mui/material";
import type { ProspectPhone, ProspectPhoneVerificationStatus } from "../../../services/prospectPhonesApi";

export type ProspectPhoneFormValues = {
  name: string;
  phone_number: string;
  source_city: string;
  address_1: string;
  address_2: string;
  verification_status: ProspectPhoneVerificationStatus;
  verification_notes: string;
};

/**
 * Valeurs vides pour une creation.
 *
 * @returns Formulaire vierge.
 */
export function emptyProspectForm(): ProspectPhoneFormValues {
  return {
    name: "",
    phone_number: "",
    source_city: "",
    address_1: "",
    address_2: "",
    verification_status: "pending",
    verification_notes: "",
  };
}

/**
 * Recopie une ligne dans le formulaire.
 *
 * @param row Prospect affiche.
 * @returns Valeurs editables.
 */
export function formFromProspect(row: ProspectPhone): ProspectPhoneFormValues {
  return {
    name: row.name,
    phone_number: row.phone_number ?? "",
    source_city: row.source_city ?? "",
    address_1: row.address_1 ?? "",
    address_2: row.address_2 ?? "",
    verification_status: row.verification_status,
    verification_notes: row.verification_notes ?? "",
  };
}

/**
 * Dialogue creation ou edition d'un prospect.
 */
export function ProspectPhoneFormDialog(props: {
  open: boolean;
  title: string;
  initial: ProspectPhoneFormValues;
  statusLabels: Record<ProspectPhoneVerificationStatus, string>;
  saving: boolean;
  onClose: () => void;
  onSubmit: (values: ProspectPhoneFormValues) => void;
}): React.ReactElement {
  const [values, setValues] = useState(props.initial);

  const set = (key: keyof ProspectPhoneFormValues) => (event: React.ChangeEvent<HTMLInputElement>) => {
    setValues((prev) => ({ ...prev, [key]: event.target.value }));
  };

  return (
    <Dialog open={props.open} onClose={props.saving ? undefined : props.onClose} fullWidth maxWidth="sm">
      <DialogTitle>{props.title}</DialogTitle>
      <DialogContent>
        <Stack spacing={1.5} sx={{ mt: 0.5 }}>
          <TextField label="Nom" value={values.name} onChange={set("name")} required autoFocus fullWidth />
          <TextField label="Telephone" value={values.phone_number} onChange={set("phone_number")} fullWidth />
          <TextField label="Ville" value={values.source_city} onChange={set("source_city")} fullWidth />
          <TextField label="Adresse" value={values.address_1} onChange={set("address_1")} fullWidth />
          <TextField label="Complement" value={values.address_2} onChange={set("address_2")} fullWidth />
          <TextField
            select
            label="Verification"
            value={values.verification_status}
            onChange={set("verification_status")}
            fullWidth
          >
            {(Object.keys(props.statusLabels) as ProspectPhoneVerificationStatus[]).map((status) => (
              <MenuItem key={status} value={status}>{props.statusLabels[status]}</MenuItem>
            ))}
          </TextField>
          <TextField
            label="Notes"
            value={values.verification_notes}
            onChange={set("verification_notes")}
            fullWidth
            multiline
            minRows={2}
          />
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={props.onClose} disabled={props.saving}>Annuler</Button>
        <Button
          variant="contained"
          disabled={props.saving || !values.name.trim()}
          onClick={() => props.onSubmit(values)}
        >
          {props.saving ? "Enregistrement…" : "Enregistrer"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
