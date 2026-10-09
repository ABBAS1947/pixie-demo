"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import FullCalendar from "@fullcalendar/react";
import dayGridPlugin from "@fullcalendar/daygrid";
import timeGridPlugin from "@fullcalendar/timegrid";
import interactionPlugin from "@fullcalendar/interaction";

import {
  createDeadline,
  deleteDeadline,
  googleAuthorizeUrl,
  googleDisconnect,
  googleStatus,
  listDeadlines,
  syncCalendar,
  updateDeadline,
} from "@/lib/api";
import { eventColor, toCalendarEvent } from "@/lib/event-mappers";
import { navigateDate } from "@/lib/calendar-utils";
import type { CalendarView, Deadline, GoogleConnectionDetails } from "@/lib/types";
import CalendarSidebar from "./components/CalendarSidebar";
import CalendarHeader from "./components/CalendarHeader";
import CreateEventModal, { type CreateEventData } from "./components/CreateEventModal";
import EventDetailModal from "./components/EventDetailModal";
import DeadlineItem from "./components/DeadlineItem";

const VIEW_TO_FC: Record<"month" | "week" | "day", string> = {
  month: "dayGridMonth",
  week: "timeGridWeek",
  day: "timeGridDay",
};

export default function Calendar() {
  const [currentDate, setCurrentDate] = useState(() => new Date());
  const [view, setView] = useState<CalendarView>("month");
  const [deadlines, setDeadlines] = useState<Deadline[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [createInitial, setCreateInitial] = useState<Date | undefined>(undefined);
  const [detail, setDetail] = useState<Deadline | null>(null);
  const [googleConnected, setGoogleConnected] = useState(false);
  const [googleDetails, setGoogleDetails] = useState<GoogleConnectionDetails | null>(null);
  const [isSyncing, setIsSyncing] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const calRef = useRef<React.ComponentRef<typeof FullCalendar> | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 3000);
  }, []);

  const load = useCallback(async () => {
    try {
      const list = await listDeadlines();
      setDeadlines(list);
    } catch {
      setDeadlines([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadGoogle = useCallback(async () => {
    try {
      const st = await googleStatus();
      setGoogleConnected(st.connected);
      setGoogleDetails(st.details);
    } catch {
      setGoogleConnected(false);
      setGoogleDetails(null);
    }
  }, []);

  useEffect(() => {
    void load();
    void loadGoogle();
  }, [load, loadGoogle]);

  // Drive FullCalendar from our state (single source of truth).
  useEffect(() => {
    const api = calRef.current?.getApi();
    if (!api || view === "list") return;
    api.changeView(VIEW_TO_FC[view]);
    api.gotoDate(currentDate);
  }, [view, currentDate]);

  function goPrev() {
    setCurrentDate((d) => navigateDate(d, view, -1));
  }
  function goNext() {
    setCurrentDate((d) => navigateDate(d, view, 1));
  }
  function goToday() {
    setCurrentDate(new Date());
  }

  async function handleCreate(data: CreateEventData) {
    const created = await createDeadline({
      title: data.title,
      due_at: data.due_at,
      kind: data.kind,
      pace_plan: data.pace_plan,
      confirmed: true,
    });
    setDeadlines((prev) => [...prev, created]);
    showToast("Deadline created");
  }

  async function handleUpdate(
    id: string,
    patch: Parameters<typeof updateDeadline>[1],
  ) {
    const updated = await updateDeadline(id, patch);
    setDeadlines((prev) => prev.map((d) => (d.id === id ? updated : d)));
    if (detail?.id === id) setDetail(updated);
    showToast("Saved");
  }

  async function handleDelete(id: string) {
    await deleteDeadline(id);
    setDeadlines((prev) => prev.filter((d) => d.id !== id));
    setDetail(null);
    showToast("Deleted");
  }

  async function handleConnectGoogle() {
    try {
      const { url } = await googleAuthorizeUrl();
      window.location.href = url;
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Google is not configured yet");
    }
  }

  async function handleSync() {
    setIsSyncing(true);
    try {
      const res = await syncCalendar(true);
      showToast(
        res.imported !== undefined
          ? `Synced: pushed ${res.pushed ?? 0}, imported ${res.imported}`
          : "Synced",
      );
      await load();
      await loadGoogle();
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Sync failed");
    } finally {
      setIsSyncing(false);
    }
  }

  async function handleDisconnect() {
    await googleDisconnect();
    setGoogleConnected(false);
    setGoogleDetails(null);
    showToast("Google disconnected");
  }

  const events = useMemo(() => deadlines.map(toCalendarEvent), [deadlines]);

  const sortedUpcoming = useMemo(
    () =>
      [...deadlines]
        .filter((d) => d.status !== "completed")
        .sort((a, b) => new Date(a.due_at).getTime() - new Date(b.due_at).getTime()),
    [deadlines],
  );

  return (
    <div className="flex h-full min-h-0 calendar-page">
      <CalendarSidebar
        currentDate={currentDate}
        onDateChange={setCurrentDate}
        isGoogleConnected={googleConnected}
        googleEmail={googleDetails?.email}
        lastSyncAt={googleDetails?.last_sync_at}
        isSyncing={isSyncing}
        onConnectGoogle={handleConnectGoogle}
        onDisconnectGoogle={handleDisconnect}
        onSync={handleSync}
        onCreateEvent={() => {
          setCreateInitial(undefined);
          setCreateOpen(true);
        }}
      />

      <div className="flex min-w-0 flex-1 flex-col bg-[var(--bg)] calendar-main">
        <CalendarHeader
          currentDate={currentDate}
          view={view}
          isSyncing={isSyncing}
          onPrev={goPrev}
          onNext={goNext}
          onToday={goToday}
          onViewChange={setView}
          onSync={handleSync}
        />

        <div className="min-h-0 flex-1 overflow-y-auto p-4 calendar-content">
          {loading ? (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-14 animate-pulse rounded-[10px] bg-[var(--surface-warm)]" />
              ))}
            </div>
          ) : view === "list" ? (
            sortedUpcoming.length === 0 ? (
              <div className="py-16 text-center">
                <p className="text-sm text-[var(--fg-2)]" style={{ fontFamily: "var(--font-dm-sans)" }}>
                  No deadlines yet. Upload a syllabus or add one manually.
                </p>
              </div>
            ) : (
              <div className="mx-auto max-w-2xl space-y-2">
                {sortedUpcoming.map((d) => (
                  <DeadlineItem key={d.id} deadline={d} onOpen={setDetail} />
                ))}
              </div>
            )
          ) : (
            <div className="rounded-[10px] bg-[var(--surface)] p-3 shadow-ring calendar-board">
              <FullCalendar
                ref={calRef}
                plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
                initialView="dayGridMonth"
                headerToolbar={false}
                height="auto"
                events={events}
                selectable
                selectMirror
                dayMaxEvents
                weekends
                eventClick={(info) => {
                  const d = deadlines.find((x) => x.id === info.event.id);
                  if (d) setDetail(d);
                }}
                eventDrop={async (info) => {
                  const d = deadlines.find((x) => x.id === info.event.id);
                  if (!d) return;
                  const start = info.event.start;
                  if (!start) return;
                  try {
                    await handleUpdate(d.id, { due_at: start.toISOString() });
                  } catch {
                    info.revert();
                  }
                }}
                select={(info) => {
                  setCreateInitial(info.start);
                  setCreateOpen(true);
                }}
                eventContent={(info) => {
                  const { kind, confirmed, courseName } = info.event.extendedProps;
                  return (
                    <div
                      className={`truncate rounded-[4px] px-2 py-0.5 text-[11px] text-white ${
                        confirmed ? "" : "border border-dashed opacity-60"
                      }`}
                      style={{ fontFamily: "var(--font-dm-sans)", background: eventColor(kind, confirmed) }}
                    >
                      {info.event.title}
                      {courseName ? ` · ${courseName}` : ""}
                    </div>
                  );
                }}
              />
            </div>
          )}
        </div>
      </div>


      {createOpen ? (
        <CreateEventModal
          initialDate={createInitial}
          onClose={() => setCreateOpen(false)}
          onSubmit={handleCreate}
        />
      ) : null}

      {detail ? (
        <EventDetailModal
          deadline={detail}
          isGoogleConnected={googleConnected}
          onClose={() => setDetail(null)}
          onUpdate={handleUpdate}
          onDelete={handleDelete}
        />
      ) : null}

      {toast ? (
        <div className="fixed left-1/2 top-4 z-50 -translate-x-1/2 rounded-[8px] border border-[var(--border)] bg-[var(--surface)] px-4 py-2 text-sm text-[var(--fg-2)] shadow-raised">
          {toast}
        </div>
      ) : null}
    </div>
  );
}
