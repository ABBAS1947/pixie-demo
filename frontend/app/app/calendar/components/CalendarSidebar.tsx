"use client";

import { Plus } from "lucide-react";
import MiniCalendar from "./MiniCalendar";
import GoogleConnection from "./GoogleConnection";

interface Props {
  currentDate: Date;
  onDateChange: (d: Date) => void;
  isGoogleConnected: boolean;
  googleEmail?: string | null;
  lastSyncAt?: string | null;
  isSyncing: boolean;
  onConnectGoogle: () => void;
  onDisconnectGoogle: () => void;
  onSync: () => void;
  onCreateEvent: () => void;
}

// Guide §3.1/4.1: desktop-only sidebar — create button, mini calendar,
// calendar list, Google connection.
export default function CalendarSidebar(props: Props) {
  return (
    <aside className="hidden w-[260px] shrink-0 flex-col border-r border-[var(--border)] bg-[var(--surface)] p-4 lg:flex calendar-sidebar">
      <button
        onClick={props.onCreateEvent}
        className="btn-3d mb-4"
      >
        <span className="bs" />
        <span className="be" />
        <span className="bf">
          <Plus size={15} /> New event
        </span>
      </button>

      <MiniCalendar date={props.currentDate} onSelect={props.onDateChange} />

      <div className="mt-4">
        <p
          className="px-2 text-[11px] font-medium uppercase tracking-[0.4px] text-[var(--meta)]"
          style={{ fontFamily: "var(--font-dm-sans)" }}
        >
          My Calendars
        </p>
        <div className="mt-1.5 space-y-1">
          <div
            className="flex items-center gap-2 rounded-[4px] px-2 py-1 text-[13px] text-[var(--fg-2)]"
            style={{ fontFamily: "var(--font-dm-sans)" }}
          >
            <span className="h-3 w-3 rounded-full bg-[var(--accent)]" />
            Deadlines
          </div>
        </div>
      </div>

      <GoogleConnection
        connected={props.isGoogleConnected}
        email={props.googleEmail}
        lastSyncAt={props.lastSyncAt}
        isSyncing={props.isSyncing}
        onConnect={props.onConnectGoogle}
        onSync={props.onSync}
        onDisconnect={props.onDisconnectGoogle}
      />
    </aside>
  );
}
