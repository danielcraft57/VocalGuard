import React from "react";
import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Checkbox,
  Chip,
  Collapse,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Fade,
  FormControlLabel,
  IconButton,
  MenuItem,
  Slide,
  Stack,
  TextField
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import type { AppointmentPayload, AppointmentSettings } from "../../../services/appointmentsApi";
import type { Entreprise } from "../../../services/entreprisesApi";

const ICON_OPTIONS = [
  { value: "", label: "Aucune", color: "#94a3b8" },
  { value: "event", label: "Evenement", color: "#38bdf8" },
  { value: "check_circle", label: "Valide", color: "#22c55e" },
  { value: "schedule", label: "Planifie", color: "#a855f7" },
  { value: "priority_high", label: "Urgent", color: "#ef4444" },
  { value: "warning", label: "Attention", color: "#f59e0b" },
  { value: "phone", label: "Appel", color: "#14b8a6" },
  { value: "build", label: "Intervention", color: "#64748b" },
  { value: "inventory_2", label: "Livraison", color: "#0ea5e9" },
  { value: "description", label: "Devis", color: "#6366f1" },
  { value: "support_agent", label: "Support", color: "#06b6d4" }
];

const COLOR_OPTIONS = [
  { value: "#38bdf8", label: "Bleu primaire" },
  { value: "#22c55e", label: "Vert primaire" },
  { value: "#a855f7", label: "Violet primaire" },
  { value: "#f59e0b", label: "Orange primaire" },
  { value: "#ef4444", label: "Rouge primaire" },
  { value: "#14b8a6", label: "Turquoise primaire" },
  { value: "#6366f1", label: "Indigo primaire" },
  { value: "#06b6d4", label: "Cyan primaire" },
  { value: "#64748b", label: "Ardoise" }
];

const TAG_STYLES: Record<string, { bg: string; border: string; text: string }> = {
  nouveau: { bg: "rgba(56, 189, 248, 0.14)", border: "#38bdf8", text: "#7dd3fc" },
  confirme: { bg: "rgba(34, 197, 94, 0.14)", border: "#22c55e", text: "#86efac" },
  en_attente: { bg: "rgba(245, 158, 11, 0.14)", border: "#f59e0b", text: "#fcd34d" },
  passe: { bg: "rgba(148, 163, 184, 0.14)", border: "#94a3b8", text: "#cbd5e1" },
  annule: { bg: "rgba(239, 68, 68, 0.14)", border: "#ef4444", text: "#fca5a5" },
  urgent: { bg: "rgba(244, 63, 94, 0.18)", border: "#f43f5e", text: "#fda4af" },
  devis: { bg: "rgba(99, 102, 241, 0.14)", border: "#6366f1", text: "#c7d2fe" },
  support: { bg: "rgba(6, 182, 212, 0.14)", border: "#06b6d4", text: "#a5f3fc" },
  livraison: { bg: "rgba(14, 165, 233, 0.14)", border: "#0ea5e9", text: "#bae6fd" }
};

const TAG_PRESETS: Record<string, { display_icon: string; display_color: string }> = {
  nouveau: { display_icon: "event", display_color: "#38bdf8" },
  confirme: { display_icon: "check_circle", display_color: "#22c55e" },
  en_attente: { display_icon: "schedule", display_color: "#f59e0b" },
  passe: { display_icon: "history", display_color: "#94a3b8" },
  annule: { display_icon: "cancel", display_color: "#ef4444" },
  urgent: { display_icon: "priority_high", display_color: "#f43f5e" },
  devis: { display_icon: "description", display_color: "#6366f1" },
  support: { display_icon: "support_agent", display_color: "#06b6d4" },
  livraison: { display_icon: "inventory_2", display_color: "#0ea5e9" }
};

interface AgendaEventDialogProps {
  open: boolean;
  busy: boolean;
  editingId: number | null;
  form: AppointmentPayload;
  setForm: React.Dispatch<React.SetStateAction<AppointmentPayload>>;
  entrepriseQuery: string;
  setEntrepriseQuery: React.Dispatch<React.SetStateAction<string>>;
  entrepriseOptions: Entreprise[];
  allDayBlocked: boolean;
  setAllDayBlocked: React.Dispatch<React.SetStateAction<boolean>>;
  settings: AppointmentSettings | null;
  error: string | null;
  onClose: () => void;
  onSave: () => Promise<void>;
  onDelete: () => Promise<void>;
}

export function AgendaEventDialog(props: AgendaEventDialogProps) {
  const {
    open,
    busy,
    editingId,
    form,
    setForm,
    entrepriseQuery,
    setEntrepriseQuery,
    entrepriseOptions,
    allDayBlocked,
    setAllDayBlocked,
    settings,
    error,
    onClose,
    onSave,
    onDelete
  } = props;
  const [notesOpen, setNotesOpen] = React.useState(false);
  const tagOptions = [
    { value: "nouveau", label: "nouveau" },
    { value: "confirme", label: "confirmé" },
    { value: "en_attente", label: "en attente" },
    { value: "passe", label: "passé" },
    { value: "annule", label: "annulé" },
    { value: "urgent", label: "urgent" },
    { value: "devis", label: "devis" },
    { value: "support", label: "support" },
    { value: "livraison", label: "livraison" }
  ];
  const toLocalInput = React.useCallback((date: Date): string => {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, "0");
    const d = String(date.getDate()).padStart(2, "0");
    const hh = String(date.getHours()).padStart(2, "0");
    const mm = String(date.getMinutes()).padStart(2, "0");
    return `${y}-${m}-${d}T${hh}:${mm}`;
  }, []);
  const [workStartMinutes, workEndMinutes] = React.useMemo(() => {
    if (!settings) return [8 * 60 + 30, 18 * 60];
    const [sh, sm] = settings.work_day_start.split(":").map((v) => Number(v));
    const [eh, em] = settings.work_day_end.split(":").map((v) => Number(v));
    return [sh * 60 + (sm || 0), eh * 60 + (em || 0)];
  }, [settings]);
  const slotMinutes = settings?.slot_minutes ?? 15;
  const isEnabledWeekday = React.useCallback((day: number): boolean => {
    if (!settings) return day >= 1 && day <= 5;
    const enabled = [
      settings.sunday_enabled,
      settings.monday_enabled,
      settings.tuesday_enabled,
      settings.wednesday_enabled,
      settings.thursday_enabled,
      settings.friday_enabled,
      settings.saturday_enabled
    ];
    return enabled[day];
  }, [settings]);
  const normalizeDateTime = React.useCallback((raw: string, boundary: "start" | "end"): string => {
    const currentStart = form.start_time ? new Date(form.start_time) : new Date();
    const value = new Date(raw);
    if (Number.isNaN(value.getTime())) {
      return boundary === "start" ? form.start_time : form.end_time;
    }
    while (!isEnabledWeekday(value.getDay())) {
      value.setDate(value.getDate() + 1);
      value.setHours(Math.floor(workStartMinutes / 60), workStartMinutes % 60, 0, 0);
    }
    const minutes = value.getHours() * 60 + value.getMinutes();
    if (minutes < workStartMinutes) {
      value.setHours(Math.floor(workStartMinutes / 60), workStartMinutes % 60, 0, 0);
    }
    if (minutes > workEndMinutes) {
      value.setHours(Math.floor(workEndMinutes / 60), workEndMinutes % 60, 0, 0);
    }
    const rounded = Math.round((value.getMinutes() || 0) / slotMinutes) * slotMinutes;
    value.setMinutes(rounded, 0, 0);

    if (boundary === "end" && value <= currentStart) {
      const next = new Date(currentStart.getTime() + Math.max(15, slotMinutes) * 60000);
      return normalizeDateTime(toLocalInput(next), "end");
    }
    return toLocalInput(value);
  }, [form.end_time, form.start_time, isEnabledWeekday, slotMinutes, toLocalInput, workEndMinutes, workStartMinutes]);

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth="sm"
    >
      <DialogTitle sx={{ pr: 6 }}>
        {editingId ? "Modifier un événement agenda" : "Ajouter un événement agenda"}
        <IconButton onClick={onClose} size="small" sx={{ position: "absolute", right: 8, top: 8 }}>
          <CloseIcon fontSize="small" />
        </IconButton>
      </DialogTitle>
      <DialogContent>
        <Fade in={open} timeout={220}>
          <div>
            <Slide in={open} direction="up" timeout={260}>
              <Stack spacing={1.2} sx={{ mt: 0.5 }}>
            <Autocomplete
              options={entrepriseOptions}
              freeSolo
              getOptionLabel={(option) => (typeof option === "string" ? option : option.name ?? "")}
              inputValue={entrepriseQuery}
              onInputChange={(_e, value) => {
                setEntrepriseQuery(value);
                setForm((prev) => ({ ...prev, title: value }));
              }}
              onChange={(_e, value) => {
                if (!value) {
                  setForm((prev) => ({ ...prev, entreprise_id: null, title: "" }));
                  return;
                }
                if (typeof value === "string") {
                  setForm((prev) => ({ ...prev, entreprise_id: null, title: value }));
                  return;
                }
                const computedLocation = [value.address_1, value.city].filter(Boolean).join(", ");
                setForm((prev) => ({
                  ...prev,
                  entreprise_id: value.id,
                  title: value.name,
                  phone_number: value.phone_number ?? prev.phone_number,
                  location: computedLocation || prev.location
                }));
              }}
              renderInput={(params) => <TextField {...params} label="Entreprise (autocomplete)" fullWidth autoFocus />}
            />
            <Box sx={{ display: "grid", gap: 1, gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" } }}>
              <Box>
                <TextField
                  label="Début"
                  type="datetime-local"
                  value={form.start_time}
                  onChange={(e) => {
                    const nextStart = normalizeDateTime(e.target.value, "start");
                    const maybeEnd = form.end_time ? new Date(form.end_time) : null;
                    const nextStartDate = new Date(nextStart);
                    let nextEnd = form.end_time ?? "";
                    if (!maybeEnd || maybeEnd <= nextStartDate) {
                      const endDate = new Date(nextStartDate.getTime() + Math.max(15, slotMinutes) * 60000);
                      nextEnd = normalizeDateTime(toLocalInput(endDate), "end");
                    }
                    setForm((prev) => ({ ...prev, start_time: nextStart, end_time: nextEnd }));
                  }}
                  slotProps={{ htmlInput: { max: form.end_time || undefined } }}
                  required
                  fullWidth
                />
              </Box>
              <Box>
                <TextField
                  label="Fin"
                  type="datetime-local"
                  value={form.end_time}
                  onChange={(e) => setForm((prev) => ({ ...prev, end_time: normalizeDateTime(e.target.value, "end") }))}
                  slotProps={{ htmlInput: { min: form.start_time || undefined } }}
                  required
                  fullWidth
                />
              </Box>
            </Box>
            <Alert severity="info" sx={{ py: 0 }}>
              Créneaux limités aux jours et heures ouvrables configurés (France).
            </Alert>
            <FormControlLabel
              control={<Checkbox checked={allDayBlocked} onChange={(e) => setAllDayBlocked(e.target.checked)} />}
              label="Bloquer toute la journée"
            />
            <Box sx={{ display: "grid", gap: 1, gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" } }}>
              <Box>
                <TextField
                  label="Téléphone"
                  value={form.phone_number ?? ""}
                  onChange={(e) => setForm((prev) => ({ ...prev, phone_number: e.target.value }))}
                  fullWidth
                />
              </Box>
              <Box>
                <TextField
                  label="Lieu"
                  value={form.location ?? ""}
                  onChange={(e) => setForm((prev) => ({ ...prev, location: e.target.value }))}
                  fullWidth
                />
              </Box>
            </Box>
            <Box sx={{ display: "grid", gap: 1, gridTemplateColumns: { xs: "1fr", md: "2fr 1fr" } }}>
              <TextField
                select
                label="Couleur"
                value={form.display_color ?? "#38bdf8"}
                onChange={(e) => setForm((prev) => ({ ...prev, display_color: e.target.value || "#38bdf8" }))}
                fullWidth
              >
                {COLOR_OPTIONS.map((item) => (
                  <MenuItem key={item.value} value={item.value}>
                    <Box sx={{ display: "inline-flex", alignItems: "center", gap: 1 }}>
                      <span style={{ width: 12, height: 12, borderRadius: "50%", backgroundColor: item.value, display: "inline-block" }} />
                      {item.label}
                    </Box>
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                select
                label="Icône"
                value={form.display_icon ?? ""}
                onChange={(e) => setForm((prev) => ({ ...prev, display_icon: e.target.value || null }))}
                fullWidth
              >
                {ICON_OPTIONS.map((item) => (
                  <MenuItem key={item.value || "none"} value={item.value}>
                    <Box sx={{ display: "inline-flex", alignItems: "center", gap: 1 }}>
                      {item.value ? <span className="material-icons" style={{ color: item.color, fontSize: 18 }}>{item.value}</span> : <span style={{ width: 18 }} />}
                      {item.label}
                    </Box>
                  </MenuItem>
                ))}
              </TextField>
            </Box>
            <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap" }}>
              {tagOptions.map((tag) => {
                const selected = form.agenda_tag === tag.value;
                const style = TAG_STYLES[tag.value];
                return (
                  <Chip
                    key={tag.value}
                    label={tag.label}
                    variant={selected ? "outlined" : "filled"}
                    onClick={() => setForm((prev) => {
                      const toggledOff = prev.agenda_tag === tag.value;
                      if (toggledOff) {
                        return { ...prev, agenda_tag: null };
                      }
                      const preset = TAG_PRESETS[tag.value];
                      return {
                        ...prev,
                        agenda_tag: tag.value,
                        display_icon: preset?.display_icon ?? prev.display_icon,
                        display_color: preset?.display_color ?? prev.display_color
                      };
                    })}
                    sx={selected
                      ? {
                        background: `${style.bg} !important`,
                        border: `1px solid ${style.border} !important`,
                        color: `${style.text} !important`,
                        boxShadow: `0 0 0 1px ${style.border}33 inset`,
                        fontWeight: 700
                      }
                      : (theme) => ({
                        background: theme.palette.mode === "dark" ? "rgba(15,23,42,.45) !important" : "rgba(148,163,184,.2) !important",
                        border: theme.palette.mode === "dark" ? "1px solid rgba(148,163,184,.35) !important" : "1px solid rgba(100,116,139,.35) !important",
                        color: theme.palette.mode === "dark" ? "#cbd5e1 !important" : "#334155 !important",
                        fontWeight: 600
                      })}
                  />
                );
              })}
            </Stack>
            <Button size="small" onClick={() => setNotesOpen((v) => !v)} sx={{ alignSelf: "flex-start" }}>
              {notesOpen ? "Masquer note optionnelle" : "Ajouter une note optionnelle"}
            </Button>
            <Collapse in={notesOpen}>
              <TextField
                label="Note (optionnelle)"
                value={form.notes ?? ""}
                onChange={(e) => setForm((prev) => ({ ...prev, notes: e.target.value }))}
                multiline
                minRows={3}
                fullWidth
              />
            </Collapse>
                {error ? <Alert severity="error">{error}</Alert> : null}
              </Stack>
            </Slide>
          </div>
        </Fade>
      </DialogContent>
      <DialogActions sx={{ px: 2, pb: 2 }}>
        {editingId ? <Button color="error" onClick={() => { void onDelete(); }}>Supprimer</Button> : null}
        <Button onClick={onClose}>Annuler</Button>
        <Button variant="contained" disabled={busy || !form.title || !form.start_time || !form.end_time} onClick={() => { void onSave(); }}>
          {editingId ? "Enregistrer" : "Créer"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
