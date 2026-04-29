"use client";

import React from "react";
import { Alert, Card, CardContent, Stack, Typography } from "@mui/material";
import { AppLayout } from "../../components/AppLayout";
import { AgendaEventDialog } from "./components/AgendaEventDialog";
import { AgendaMonthGrid } from "./components/AgendaMonthGrid";
import { AgendaTimeGrid } from "./components/AgendaTimeGrid";
import { AgendaToolbar } from "./components/AgendaToolbar";
import { useAgendaCalendar } from "./hooks/useAgendaCalendar";

export default function AgendaPage() {
  const agenda = useAgendaCalendar();

  return (
    <AppLayout title="Agenda" hidePageHeader>
      <Stack spacing={1}>
        <AgendaToolbar
          view={agenda.view}
          onViewChange={agenda.setView}
          periodLabel={agenda.periodLabel}
          onToday={agenda.goToday}
          onPrev={agenda.goPrev}
          onNext={agenda.goNext}
        />

        {agenda.error ? <Alert severity="error">{agenda.error}</Alert> : null}

        <Card sx={{ borderRadius: 3, border: "1px solid var(--vg-color-border-subtle)", transition: "all .2s ease", "&:hover": { boxShadow: 6 } }}>
          <CardContent sx={{ p: 1 }}>
            {agenda.view === "month" ? (
              <AgendaMonthGrid
                cursorDate={agenda.cursorDate}
                monthCells={agenda.monthCells}
                events={agenda.events}
                onCreateAt={agenda.openCreateAt}
                onEdit={agenda.openEdit}
              />
            ) : (
              <AgendaTimeGrid
                view={agenda.view}
                cursorDate={agenda.cursorDate}
                weekDays={agenda.weekDays}
                events={agenda.events}
                onCreateAt={agenda.openCreateAt}
                onEdit={agenda.openEdit}
                onMoveEvent={agenda.onMoveEvent}
                onResizeEvent={agenda.onResizeEvent}
                focusSlot={agenda.focusSlot}
                focusNonce={agenda.focusNonce}
              />
            )}
          </CardContent>
        </Card>

        {agenda.loading ? <Typography className="vg-agenda-loading">Chargement des événements...</Typography> : null}
      </Stack>

      <AgendaEventDialog
        open={agenda.editorOpen}
        busy={agenda.busy}
        editingId={agenda.editingId}
        form={agenda.form}
        setForm={agenda.setForm}
        entrepriseQuery={agenda.entrepriseQuery}
        setEntrepriseQuery={agenda.setEntrepriseQuery}
        entrepriseOptions={agenda.entrepriseOptions}
        allDayBlocked={agenda.allDayBlocked}
        setAllDayBlocked={agenda.setAllDayBlocked}
        settings={agenda.settings}
        error={agenda.error}
        onClose={() => agenda.setEditorOpen(false)}
        onSave={agenda.saveEvent}
        onDelete={agenda.removeEvent}
      />
    </AppLayout>
  );
}
