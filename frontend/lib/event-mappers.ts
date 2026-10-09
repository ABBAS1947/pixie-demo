// Deadline -> FullCalendar event mapping (guide §6.2 lib/event-mappers).
import type { Deadline, DeadlineKind } from "@/lib/types";

export interface CalendarEvent {
  id: string;
  title: string;
  start: string;
  allDay?: boolean;
  extendedProps: {
    kind: DeadlineKind;
    courseName?: string;
    confirmed: boolean;
    pacePlan?: string;
    source: string;
    syncedToGoogle: boolean;
  };
}

export function toCalendarEvent(d: Deadline): CalendarEvent {
  return {
    id: d.id,
    title: d.title,
    start: d.due_at,
    extendedProps: {
      kind: d.kind,
      courseName: d.course?.name,
      confirmed: d.confirmed,
      pacePlan: d.pace_plan ?? undefined,
      source: d.source,
      syncedToGoogle: d.synced_to_google,
    },
  };
}

// Guide §2.1 event color mapping: exam ink-blue, assignment sage,
// project warm, unconfirmed muted. Never Google's default colors.
export function eventColor(kind: DeadlineKind, confirmed: boolean): string {
  if (!confirmed) return "#6b6a64";
  switch (kind) {
    case "exam":
      return "#1b365d";
    case "assignment":
      return "#4a6b3a";
    case "project":
      return "#8a6b1f";
    default:
      return "#6b6a64";
  }
}

export function kindLabel(kind: DeadlineKind): string {
  switch (kind) {
    case "exam":
      return "Exam";
    case "assignment":
      return "Assignment";
    case "project":
      return "Project";
  }
}
