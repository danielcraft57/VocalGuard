import { useEffect, useMemo, useState } from "react";
import type { Appointment, AppointmentPayload } from "../../../services/appointmentsApi";
import {
  createAppointment,
  deleteAppointment,
  fetchAppointmentSettings,
  fetchAppointments,
  type AppointmentSettings,
  updateAppointment
} from "../../../services/appointmentsApi";
import { fetchEntreprises, type Entreprise } from "../../../services/entreprisesApi";
import type { AgendaView } from "../types";

function toLocalInput(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  const hh = String(date.getHours()).padStart(2, "0");
  const mm = String(date.getMinutes()).padStart(2, "0");
  return `${y}-${m}-${d}T${hh}:${mm}`;
}

function parseDate(value: string): Date {
  return new Date(value);
}

function sameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

function normalizeApiError(raw: string): string {
  const lowered = raw.toLowerCase();
  if (lowered.includes("conflit detecte")) {
    return "Ce créneau est déjà pris. Choisis un autre horaire.";
  }
  if (lowered.includes("hors plage horaire")) {
    return "Créneau hors horaires de travail.";
  }
  if (lowered.includes("jour indisponible")) {
    return "Ce jour est marqué indisponible.";
  }
  if (lowered.includes("jours de travail")) {
    return "Ce jour n'est pas activé dans les jours de travail.";
  }
  if (lowered.includes("heure de fin")) {
    return "L'heure de fin doit être après l'heure de début.";
  }
  return raw;
}

function startOfWeek(base: Date): Date {
  const d = new Date(base);
  d.setHours(0, 0, 0, 0);
  const weekdayOffset = (d.getDay() + 6) % 7; // Lundi=0 ... Dimanche=6
  d.setDate(d.getDate() - weekdayOffset);
  return d;
}

function defaultFormFromDate(start: Date): AppointmentPayload {
  const end = new Date(start.getTime() + 60 * 60 * 1000);
  return {
    title: "",
    start_time: toLocalInput(start),
    end_time: toLocalInput(end),
    status: "scheduled",
    location: "",
    phone_number: "",
    service_type: "",
    display_color: "#38bdf8",
    notes: ""
  };
}

export function useAgendaCalendar() {
  const [events, setEvents] = useState<Appointment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<AgendaView>("week");
  const [cursorDate, setCursorDate] = useState(new Date());
  const [editorOpen, setEditorOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState<AppointmentPayload>(defaultFormFromDate(new Date()));
  const [allDayBlocked, setAllDayBlocked] = useState(false);
  const [entrepriseQuery, setEntrepriseQuery] = useState("");
  const [entrepriseOptions, setEntrepriseOptions] = useState<Entreprise[]>([]);
  const [entrepriseCache, setEntrepriseCache] = useState<Entreprise[]>([]);
  const [focusSlot, setFocusSlot] = useState<Date | null>(null);
  const [focusNonce, setFocusNonce] = useState(0);
  const [settings, setSettings] = useState<AppointmentSettings | null>(null);

  useEffect(() => {
    const start = form.start_time ? parseDate(form.start_time) : null;
    if (!start || Number.isNaN(start.getTime())) {
      return;
    }
    const currentEnd = form.end_time ? parseDate(form.end_time) : null;
    if (!currentEnd || Number.isNaN(currentEnd.getTime()) || currentEnd <= start) {
      const nextEnd = new Date(start.getTime() + 60 * 60 * 1000);
      setForm((prev) => ({ ...prev, end_time: toLocalInput(nextEnd) }));
    }
  }, [form.start_time]);

  useEffect(() => {
    fetchAppointmentSettings()
      .then((res) => setSettings(res))
      .catch(() => setSettings(null));
  }, []);

  useEffect(() => {
    fetchEntreprises({ limit: 120 })
      .then((res) => {
        setEntrepriseCache(res.items);
        setEntrepriseOptions(res.items.slice(0, 20));
      })
      .catch(() => {
        setEntrepriseCache([]);
      });
  }, []);

  useEffect(() => {
    const query = entrepriseQuery.trim();
    if (query.length < 2) {
      setEntrepriseOptions(entrepriseCache.slice(0, 20));
      return;
    }
    const timer = window.setTimeout(() => {
      const local = entrepriseCache.filter((item) => item.name.toLowerCase().includes(query.toLowerCase())).slice(0, 20);
      if (local.length > 0) {
        setEntrepriseOptions(local);
        return;
      }
      fetchEntreprises({ q: query, limit: 20 })
        .then((res) => setEntrepriseOptions(res.items))
        .catch(() => setEntrepriseOptions(local));
    }, 220);
    return () => window.clearTimeout(timer);
  }, [entrepriseQuery, entrepriseCache]);

  useEffect(() => {
    let cancelled = false;
    async function loadEvents(): Promise<void> {
      try {
        const data = await fetchAppointments();
        if (!cancelled) {
          setEvents(data);
          setError(null);
        }
      } catch {
        if (!cancelled) {
          setError("Impossible de charger l'agenda.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    loadEvents();
    return () => {
      cancelled = true;
    };
  }, []);

  const weekDays = useMemo(() => {
    const start = startOfWeek(cursorDate);
    return Array.from({ length: 7 }, (_, index) => {
      const day = new Date(start);
      day.setDate(start.getDate() + index);
      return day;
    });
  }, [cursorDate]);

  const monthCells = useMemo(() => {
    const firstDay = new Date(cursorDate.getFullYear(), cursorDate.getMonth(), 1);
    const gridStart = startOfWeek(firstDay);
    return Array.from({ length: 42 }, (_, index) => {
      const day = new Date(gridStart);
      day.setDate(gridStart.getDate() + index);
      return day;
    });
  }, [cursorDate]);

  const goToday = (): void => {
    const now = new Date();
    setCursorDate(now);
    const next = findNextFreeSlot(now, events);
    setFocusSlot(next);
    setFocusNonce((v) => v + 1);
  };
  const goNext = (): void => {
    const next = new Date(cursorDate);
    if (view === "month") next.setMonth(next.getMonth() + 1);
    if (view === "week") next.setDate(next.getDate() + 7);
    if (view === "day") next.setDate(next.getDate() + 1);
    setCursorDate(next);
  };
  const goPrev = (): void => {
    const next = new Date(cursorDate);
    if (view === "month") next.setMonth(next.getMonth() - 1);
    if (view === "week") next.setDate(next.getDate() - 7);
    if (view === "day") next.setDate(next.getDate() - 1);
    setCursorDate(next);
  };

  const periodLabel = useMemo(() => {
    if (view === "day") {
      return cursorDate.toLocaleDateString("fr-FR", { weekday: "long", day: "2-digit", month: "long", year: "numeric" });
    }
    if (view === "week") {
      const start = weekDays[0];
      const end = weekDays[6];
      return `${start.toLocaleDateString("fr-FR", { day: "2-digit", month: "long" })} - ${end.toLocaleDateString("fr-FR", { day: "2-digit", month: "long", year: "numeric" })}`;
    }
    return cursorDate.toLocaleDateString("fr-FR", { month: "long", year: "numeric" });
  }, [view, cursorDate, weekDays]);

  const openCreateAt = (start: Date): void => {
    const now = new Date();
    if (start < now) {
      setError("Impossible de créer un rendez-vous dans le passé.");
      return;
    }
    const end = new Date(start.getTime() + 60 * 60 * 1000);
    if (!isAllowedBySettings(start, end, settings)) {
      setError("Créneau hors horaires/jours ouvrables (France).");
      return;
    }
    const alreadyBookedAllDay = events.some((item) => {
      const itemStart = parseDate(item.start_time);
      return sameDay(itemStart, start) && Boolean(item.is_all_day);
    });
    if (alreadyBookedAllDay) {
      setError("Cette journée est déjà bloquée en 'toute la journée'.");
      return;
    }
    setEditingId(null);
    setForm(defaultFormFromDate(start));
    setAllDayBlocked(false);
    setEntrepriseQuery("");
    setEditorOpen(true);
  };

  const openEdit = (item: Appointment): void => {
    setEditingId(item.id);
    setForm({
      title: item.title,
      start_time: toLocalInput(parseDate(item.start_time)),
      end_time: toLocalInput(parseDate(item.end_time)),
      status: item.status ?? "scheduled",
      location: item.location ?? "",
      phone_number: item.phone_number ?? "",
      service_type: item.service_type ?? "",
      agenda_tag: item.agenda_tag ?? null,
      display_icon: item.display_icon ?? null,
      display_color: item.display_color ?? "#38bdf8",
      notes: item.notes ?? ""
    });
    setAllDayBlocked(false);
    setEntrepriseQuery(item.title ?? "");
    setEditorOpen(true);
  };

  const refreshEvents = async (): Promise<void> => {
    setEvents(await fetchAppointments());
  };

  const saveEvent = async (): Promise<void> => {
    setBusy(true);
    setError(null);
    try {
      const startForCheck = parseDate(form.start_time);
      const endForCheck = parseDate(form.end_time);
      if (!isAllowedBySettings(startForCheck, endForCheck, settings)) {
        setError("Créneau hors horaires/jours de travail configurés.");
        return;
      }
      if (allDayBlocked) {
        const start = parseDate(form.start_time);
        const dayStart = new Date(start.getFullYear(), start.getMonth(), start.getDate(), 0, 0, 0);
        const dayEnd = new Date(start.getFullYear(), start.getMonth(), start.getDate(), 23, 59, 0);
        const payload = {
          ...form,
          start_time: toLocalInput(dayStart),
          end_time: toLocalInput(dayEnd)
        };
        if (editingId) await updateAppointment(editingId, payload);
        else await createAppointment(payload);
      } else if (editingId) {
        await updateAppointment(editingId, form);
      } else {
        await createAppointment(form);
      }
      await refreshEvents();
      setEditorOpen(false);
    } catch (err) {
      const raw = err instanceof Error ? err.message : "Erreur de sauvegarde agenda.";
      setError(normalizeApiError(raw));
    } finally {
      setBusy(false);
    }
  };

  const removeEvent = async (): Promise<void> => {
    if (!editingId) return;
    setBusy(true);
    try {
      await deleteAppointment(editingId);
      await refreshEvents();
      setEditorOpen(false);
    } finally {
      setBusy(false);
    }
  };

  const onMoveEvent = async (item: Appointment, newStart: Date): Promise<void> => {
    if (newStart < new Date()) {
      setError("Impossible de déplacer un rendez-vous dans le passé.");
      return;
    }
    const oldStart = parseDate(item.start_time);
    const oldEnd = parseDate(item.end_time);
    const duration = Math.max(30, Math.round((oldEnd.getTime() - oldStart.getTime()) / 60000));
    const newEnd = new Date(newStart.getTime() + duration * 60000);
    if (!isAllowedBySettings(newStart, newEnd, settings)) {
      setError("Créneau hors horaires/jours de travail configurés.");
      return;
    }
    try {
      await updateAppointment(item.id, {
        start_time: toLocalInput(newStart),
        end_time: toLocalInput(newEnd)
      });
      await refreshEvents();
      setError(null);
    } catch (err) {
      const raw = err instanceof Error ? err.message : "Impossible de déplacer cet événement.";
      setError(normalizeApiError(raw));
    }
  };

  const onResizeEvent = async (item: Appointment, newEnd: Date): Promise<void> => {
    const start = parseDate(item.start_time);
    if (newEnd <= start) {
      return;
    }
    if (!isAllowedBySettings(start, newEnd, settings)) {
      setError("Créneau hors horaires/jours de travail configurés.");
      return;
    }
    try {
      await updateAppointment(item.id, {
        end_time: toLocalInput(newEnd)
      });
      await refreshEvents();
      setError(null);
    } catch (err) {
      const raw = err instanceof Error ? err.message : "Impossible de redimensionner cet événement.";
      setError(normalizeApiError(raw));
    }
  };

  return {
    events,
    loading,
    error,
    view,
    setView,
    cursorDate,
    weekDays,
    monthCells,
    editorOpen,
    setEditorOpen,
    editingId,
    busy,
    form,
    setForm,
    entrepriseQuery,
    setEntrepriseQuery,
    entrepriseOptions,
    allDayBlocked,
    setAllDayBlocked,
    goToday,
    goNext,
    goPrev,
    periodLabel,
    openCreateAt,
    openEdit,
    saveEvent,
    removeEvent,
    onMoveEvent,
    onResizeEvent,
    setError,
    focusSlot,
    focusNonce,
    settings
  };
}

function findNextFreeSlot(base: Date, events: Appointment[]): Date {
  const start = new Date(base);
  start.setMinutes(Math.ceil(start.getMinutes() / 15) * 15, 0, 0);
  if (start.getHours() < 8) start.setHours(8, 0, 0, 0);
  if (start.getHours() > 20) {
    start.setDate(start.getDate() + 1);
    start.setHours(8, 0, 0, 0);
  }

  for (let i = 0; i < 96; i++) {
    const slot = new Date(start.getTime() + i * 15 * 60000);
    const taken = events.some((item) => {
      const s = parseDate(item.start_time).getTime();
      const e = parseDate(item.end_time).getTime();
      const t = slot.getTime();
      return t >= s && t < e;
    });
    if (!taken) {
      return slot;
    }
  }
  return start;
}

function parseHmToMinutes(value: string): number {
  const [h, m] = value.split(":").map((v) => Number(v));
  return h * 60 + m;
}

function isAllowedBySettings(start: Date, end: Date, settings: AppointmentSettings | null): boolean {
  if (!settings) return true;
  const weekdayEnabled = [
    settings.sunday_enabled,
    settings.monday_enabled,
    settings.tuesday_enabled,
    settings.wednesday_enabled,
    settings.thursday_enabled,
    settings.friday_enabled,
    settings.saturday_enabled
  ][start.getDay()];
  if (!weekdayEnabled) return false;

  const startMin = start.getHours() * 60 + start.getMinutes();
  const endMin = end.getHours() * 60 + end.getMinutes();
  const minAllowed = parseHmToMinutes(settings.work_day_start);
  const maxAllowed = parseHmToMinutes(settings.work_day_end);
  return startMin >= minAllowed && endMin <= maxAllowed;
}
