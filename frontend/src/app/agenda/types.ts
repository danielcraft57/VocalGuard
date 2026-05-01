import type { Appointment, AppointmentPayload } from "../../services/appointmentsApi";

export type AgendaView = "day" | "week" | "month";

export interface AgendaEditorState {
  open: boolean;
  editingId: number | null;
  busy: boolean;
  form: AppointmentPayload;
}

export interface AgendaState {
  events: Appointment[];
  loading: boolean;
  error: string | null;
  view: AgendaView;
  cursorDate: Date;
  editor: AgendaEditorState;
}
