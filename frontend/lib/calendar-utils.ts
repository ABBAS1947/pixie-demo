// Date helpers for the calendar (guide §6.2 lib/calendar-utils).
import {
  addDays,
  addMonths,
  addWeeks,
  endOfDay,
  endOfMonth,
  endOfWeek,
  format,
  startOfDay,
  startOfMonth,
  startOfWeek,
} from "date-fns";
import type { CalendarView } from "./types";

export function viewTitle(date: Date, view: CalendarView): string {
  if (view === "month") return format(date, "MMMM yyyy");
  if (view === "week") return format(date, "MMMM yyyy");
  if (view === "day") return format(date, "EEEE, MMMM d");
  return format(date, "MMMM yyyy");
}

export function viewRange(date: Date, view: CalendarView): { start: Date; end: Date } {
  if (view === "month") {
    return { start: startOfMonth(date), end: endOfMonth(date) };
  }
  if (view === "week") {
    return {
      start: startOfWeek(date, { weekStartsOn: 1 }),
      end: endOfWeek(date, { weekStartsOn: 1 }),
    };
  }
  if (view === "day") {
    return { start: startOfDay(date), end: endOfDay(date) };
  }
  // list: rolling 60 days from today
  return { start: startOfDay(new Date()), end: addDays(new Date(), 60) };
}

export function navigateDate(date: Date, view: CalendarView, delta: number): Date {
  if (view === "week") return addWeeks(date, delta);
  if (view === "day") return addDays(date, delta);
  return addMonths(date, delta);
}

export function formatEventTime(iso: string): string {
  return format(new Date(iso), "MMM d · h:mm a");
}

// Guide §2.3: only the 4px→64px scale, nothing off-scale.
export const SPACE = [4, 8, 12, 16, 24, 32, 48, 64] as const;
