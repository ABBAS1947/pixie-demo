"use client";

import { ChevronLeft, ChevronRight, RefreshCw } from "lucide-react";
import { viewTitle } from "@/lib/calendar-utils";
import type { CalendarView } from "@/lib/types";

const VIEWS: { key: CalendarView; label: string }[] = [
  { key: "month", label: "Month" },
  { key: "week", label: "Week" },
  { key: "day", label: "Day" },
  { key: "list", label: "List" },
];

interface Props {
  currentDate: Date;
  view: CalendarView;
  isSyncing: boolean;
  onPrev: () => void;
  onNext: () => void;
  onToday: () => void;
  onViewChange: (v: CalendarView) => void;
  onSync: () => void;
}

// Guide §4.2: title, navigation group, view toggle, sync button.
export default function CalendarHeader(props: Props) {
  const navBtn =
    "flex h-8 w-8 items-center justify-center rounded-[8px] text-[var(--fg-2)] transition-colors hover:bg-[var(--surface-warm)]";
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--border)] bg-[var(--surface)] px-6 py-4 calendar-header">
      <h1
        className="text-[24px] text-[var(--fg)]"
        style={{ fontFamily: "var(--font-dm-sans)", fontWeight: 500 }}
      >
        {viewTitle(props.currentDate, props.view)}
      </h1>

      <div className="flex items-center gap-2">
        <button onClick={props.onPrev} className={navBtn} aria-label="Previous">
          <ChevronLeft size={16} />
        </button>
        <button
          onClick={props.onToday}
          className="rounded-[8px] border border-[var(--border)] px-3 py-1.5 text-sm text-[var(--fg-2)] transition-colors hover:text-[var(--fg)]"
          style={{ fontFamily: "var(--font-dm-sans)" }}
        >
          Today
        </button>
        <button onClick={props.onNext} className={navBtn} aria-label="Next">
          <ChevronRight size={16} />
        </button>
      </div>

      <div className="flex overflow-hidden rounded-[8px] shadow-ring">
        {VIEWS.map((v) => (
          <button
            key={v.key}
            onClick={() => props.onViewChange(v.key)}
            className={`px-4 py-1.5 text-sm transition-colors ${
              props.view === v.key
                ? "bg-[var(--accent)] text-[var(--accent-on)]"
                : "bg-[var(--surface)] text-[var(--meta)] hover:text-[var(--fg)]"
            }`}
            style={{ fontFamily: "var(--font-dm-sans)" }}
          >
            {v.label}
          </button>
        ))}
      </div>

      <button
        onClick={props.onSync}
        disabled={props.isSyncing}
        className="flex items-center gap-1 rounded-[8px] border border-[var(--border)] px-3 py-1.5 text-sm text-[var(--meta)] transition-colors hover:text-[var(--fg)] disabled:opacity-50"
        style={{ fontFamily: "var(--font-dm-sans)" }}
      >
        <RefreshCw size={14} className={props.isSyncing ? "animate-spin" : ""} />
        {props.isSyncing ? "Syncing" : "Sync"}
      </button>
    </div>
  );
}
