"use client";

import { formatEventTime } from "@/lib/calendar-utils";
import { kindLabel } from "@/lib/event-mappers";
import type { Deadline } from "@/lib/types";

interface Props {
  deadline: Deadline;
  onOpen: (d: Deadline) => void;
}

// Guide §4.4: list-view card — kind-colored left border, title, meta row.
export default function DeadlineItem({ deadline, onOpen }: Props) {
  const borderColor = !deadline.confirmed
    ? "var(--meta)"
    : deadline.kind === "exam"
      ? "var(--accent)"
      : deadline.kind === "assignment"
        ? "var(--success)"
        : "var(--warn)";

  return (
    <button
      onClick={() => onOpen(deadline)}
      className={`w-full rounded-[10px] border border-[var(--border)] bg-[var(--surface)] p-4 text-left shadow-ring transition-shadow hover:shadow-raised ${
        !deadline.confirmed ? "border-dashed" : ""
      }`}
      style={{ borderLeft: `4px solid ${borderColor}` }}
    >
      <p
        className="text-[15px] font-semibold text-[var(--fg)]"
        style={{ fontFamily: "var(--font-dm-sans)" }}
      >
        {deadline.title}
      </p>
      <div className="mt-1 flex flex-wrap items-center gap-3 text-[13px] text-[var(--meta)]" style={{ fontFamily: "var(--font-dm-sans)" }}>
        <span>{formatEventTime(deadline.due_at)}</span>
        {deadline.course?.name ? (
          <span className="rounded-[4px] bg-[var(--surface-warm)] px-2 py-0.5 text-[12px] text-[var(--fg-2)]">
            {deadline.course.name}
          </span>
        ) : null}
        <span className="text-[12px]">{kindLabel(deadline.kind)}</span>
        {!deadline.confirmed ? (
          <span className="text-[11px] text-[var(--meta)]">Unconfirmed</span>
        ) : null}
        {deadline.synced_to_google ? (
          <span className="text-[11px] text-[var(--success)]">Synced</span>
        ) : null}
      </div>
    </button>
  );
}
