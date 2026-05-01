import React, { useEffect, useMemo, useRef } from "react";
import type { Appointment } from "../../../services/appointmentsApi";
import type { AgendaView } from "../types";

interface AgendaTimeGridProps {
  view: AgendaView;
  cursorDate: Date;
  weekDays: Date[];
  events: Appointment[];
  onCreateAt: (date: Date) => void;
  onEdit: (item: Appointment) => void;
  onMoveEvent: (item: Appointment, newStart: Date) => void;
  onResizeEvent: (item: Appointment, newEnd: Date) => void;
  focusSlot: Date | null;
  focusNonce: number;
}

function AgendaTimeGridComponent(props: AgendaTimeGridProps) {
  const { view, cursorDate, weekDays, events, onCreateAt, onEdit, onMoveEvent, onResizeEvent, focusSlot, focusNonce } = props;
  const hours = useMemo(() => Array.from({ length: 13 }, (_, index) => index + 8), []);
  const days = view === "day" ? [cursorDate] : weekDays;
  const containerRef = useRef<HTMLDivElement | null>(null);
  const SLOT_HEIGHT = 52;

  useEffect(() => {
    const target = containerRef.current;
    if (!target) return;
    const anchor = focusSlot ?? new Date();
    const hourOffset = Math.max(0, anchor.getHours() - 8 + (anchor.getMinutes() / 60));
    target.scrollTop = hourOffset * SLOT_HEIGHT;
  }, [view, cursorDate, focusSlot, focusNonce]);

  const eventsByDay = useMemo(() => {
    const grouped = new Map<string, Appointment[]>();
    for (const item of events) {
      const d = new Date(item.start_time);
      const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
      const list = grouped.get(key) ?? [];
      list.push(item);
      grouped.set(key, list);
    }
    for (const [, list] of grouped) {
      list.sort((a, b) => new Date(a.start_time).getTime() - new Date(b.start_time).getTime());
    }
    return grouped;
  }, [events]);

  const dayKey = (day: Date): string => `${day.getFullYear()}-${day.getMonth()}-${day.getDate()}`;

  return (
    <div className="vg-agenda-time-shell">
      <div className="vg-agenda-time-grid" style={{ gridTemplateColumns: `80px repeat(${days.length}, minmax(0, 1fr))` }}>
        <div className="vg-agenda-time-head">Heure</div>
        {days.map((day) => (
          <div key={day.toISOString()} className="vg-agenda-time-head">
            {day.toLocaleDateString("fr-FR", { weekday: "short", day: "2-digit", month: "2-digit" })}
          </div>
        ))}
      </div>

      <div ref={containerRef} className="vg-agenda-time-scroll">
        <div className="vg-agenda-time-grid" style={{ gridTemplateColumns: `80px repeat(${days.length}, minmax(0, 1fr))` }}>
          {hours.map((hour) => (
            <React.Fragment key={hour}>
              <div className="vg-agenda-hour-label">{String(hour).padStart(2, "0")}:00</div>
              {days.map((day) => {
                const slot = new Date(day.getFullYear(), day.getMonth(), day.getDate(), hour, 0, 0);
                const isPastSlot = slot < new Date();
                return (
                  <button
                    key={`${day.toISOString()}-${hour}`}
                    type="button"
                    className={`vg-agenda-hour-cell ${isPastSlot ? "vg-agenda-hour-cell--disabled" : ""}`}
                    onClick={() => onCreateAt(slot)}
                    disabled={isPastSlot}
                  />
                );
              })}
            </React.Fragment>
          ))}
        </div>

        <div className="vg-agenda-overlay" style={{ gridTemplateColumns: `80px repeat(${days.length}, minmax(0, 1fr))` }}>
          <div />
          {days.map((day) => (
            <div
              key={`col-${day.toISOString()}`}
              className="vg-agenda-day-overlay-col"
              onDragOver={(e) => e.preventDefault()}
              onClick={(e) => {
                const rect = (e.currentTarget as HTMLDivElement).getBoundingClientRect();
                const y = e.clientY - rect.top;
                const minutes = Math.max(0, Math.min(12 * 60, Math.round((y / SLOT_HEIGHT) * 60)));
                const hour = 8 + Math.floor(minutes / 60);
                const minute = Math.round((minutes % 60) / 15) * 15;
                const slot = new Date(day.getFullYear(), day.getMonth(), day.getDate(), hour, minute, 0);
                onCreateAt(slot);
              }}
              onDrop={(e) => {
                e.preventDefault();
                const eventId = Number(e.dataTransfer.getData("text/event-id"));
                const moved = events.find((item) => item.id === eventId);
                if (!moved) return;
                const rect = (e.currentTarget as HTMLDivElement).getBoundingClientRect();
                const y = e.clientY - rect.top;
                const minutes = Math.max(0, Math.min(12 * 60, Math.round((y / SLOT_HEIGHT) * 60)));
                const hour = 8 + Math.floor(minutes / 60);
                const minute = Math.round((minutes % 60) / 15) * 15;
                const newStart = new Date(day.getFullYear(), day.getMonth(), day.getDate(), hour, minute, 0);
                onMoveEvent(moved, newStart);
              }}
            >
              {(eventsByDay.get(dayKey(day)) ?? []).map((item) => {
                const start = new Date(item.start_time);
                const end = new Date(item.end_time);
                const top = Math.max(0, (start.getHours() - 8) * SLOT_HEIGHT + (start.getMinutes() / 60) * SLOT_HEIGHT);
                const durationMin = Math.max(30, (end.getTime() - start.getTime()) / 60000);
                const height = Math.max(30, (durationMin / 60) * SLOT_HEIGHT);
                return (
                  <div
                    key={item.id}
                    className="vg-agenda-event-block"
                    style={{
                      top: `${top}px`,
                      height: `${height}px`,
                      background: item.display_color
                        ? `linear-gradient(180deg, ${item.display_color}E6, ${item.display_color}CC)`
                        : undefined
                    }}
                    draggable
                    onDragStart={(e) => e.dataTransfer.setData("text/event-id", String(item.id))}
                    onClick={(e) => {
                      e.stopPropagation();
                      onEdit(item);
                    }}
                  >
                    <div className="vg-agenda-event-title">
                      {item.display_icon ? <span className="material-icons" style={{ fontSize: 12, marginRight: 4 }}>{item.display_icon}</span> : null}
                      {new Date(item.start_time).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })} - {item.title}
                      {item.agenda_tag ? <span style={{ marginLeft: 6, opacity: 0.9 }}>[{item.agenda_tag}]</span> : null}
                    </div>
                    <div
                      className="vg-agenda-event-resize"
                      onMouseDown={(e) => {
                        e.preventDefault();
                        const startY = e.clientY;
                        const initialHeight = height;
                        let lastY = startY;
                        let rafId: number | null = null;
                        const onMove = (moveEvent: MouseEvent) => {
                          const nextY = moveEvent.clientY;
                          if (rafId !== null) {
                            return;
                          }
                          rafId = window.requestAnimationFrame(() => {
                            lastY = nextY;
                            rafId = null;
                          });
                        };
                        const onUp = () => {
                          if (rafId !== null) {
                            window.cancelAnimationFrame(rafId);
                            rafId = null;
                          }
                          const delta = lastY - startY;
                          const nextHeight = Math.max(30, initialHeight + delta);
                          const nextMinutes = Math.round(((nextHeight / SLOT_HEIGHT) * 60) / 15) * 15;
                          const newEnd = new Date(start.getTime() + nextMinutes * 60000);
                          onResizeEvent(item, newEnd);
                          window.removeEventListener("mousemove", onMove);
                          window.removeEventListener("mouseup", onUp);
                        };
                        window.addEventListener("mousemove", onMove);
                        window.addEventListener("mouseup", onUp);
                      }}
                    />
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export const AgendaTimeGrid = React.memo(AgendaTimeGridComponent);
