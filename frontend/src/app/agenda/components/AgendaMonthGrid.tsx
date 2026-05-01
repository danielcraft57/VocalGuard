import React, { useMemo } from "react";
import type { Appointment } from "../../../services/appointmentsApi";

const WEEKDAY_LABELS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];

interface AgendaMonthGridProps {
  cursorDate: Date;
  monthCells: Date[];
  events: Appointment[];
  onCreateAt: (date: Date) => void;
  onEdit: (item: Appointment) => void;
}

function AgendaMonthGridComponent(props: AgendaMonthGridProps) {
  const { cursorDate, monthCells, events, onCreateAt, onEdit } = props;

  const eventsByDay = useMemo(() => {
    const grouped = new Map<string, Appointment[]>();
    for (const item of events) {
      const d = new Date(item.start_time);
      const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
      const list = grouped.get(key) ?? [];
      list.push(item);
      grouped.set(key, list);
    }
    return grouped;
  }, [events]);

  const dayKey = (day: Date): string => `${day.getFullYear()}-${day.getMonth()}-${day.getDate()}`;

  return (
    <div className="vg-agenda-month">
      {WEEKDAY_LABELS.map((label) => <div key={label} className="vg-agenda-weekday">{label}</div>)}
      {monthCells.map((day) => (
        (() => {
          const dayEvents = eventsByDay.get(dayKey(day)) ?? [];
          const occupied = dayEvents.length > 0;
          const isPastDay = new Date(day.getFullYear(), day.getMonth(), day.getDate(), 23, 59, 59) < new Date();
          return (
        <button
          key={day.toISOString()}
          type="button"
          className={`vg-agenda-day-cell ${day.getMonth() !== cursorDate.getMonth() ? "vg-agenda-day-cell--muted" : ""} ${occupied ? "vg-agenda-day-cell--occupied" : ""} ${isPastDay ? "vg-agenda-day-cell--disabled" : ""}`}
          onClick={() => onCreateAt(new Date(day.getFullYear(), day.getMonth(), day.getDate(), 9, 0, 0))}
          disabled={isPastDay}
        >
          <div className="vg-agenda-day-number">{day.getDate()}</div>
          <div className="vg-agenda-events-mini">
            {dayEvents.slice(0, 3).map((item) => (
              <div key={item.id} className="vg-agenda-pill" onClick={(e) => { e.stopPropagation(); onEdit(item); }}>
                {item.display_icon ? <span className="material-icons" style={{ fontSize: 12, marginRight: 4 }}>{item.display_icon}</span> : null}
                {new Date(item.start_time).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })} - {item.title}
                {item.agenda_tag ? ` [${item.agenda_tag}]` : ""}
              </div>
            ))}
          </div>
        </button>
          );
        })()
      ))}
    </div>
  );
}

export const AgendaMonthGrid = React.memo(AgendaMonthGridComponent);
