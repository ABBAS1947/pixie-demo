"use client";

import {
  addDays,
  format,
  isSameDay,
  isSameMonth,
  isToday,
  startOfMonth,
  startOfWeek,
} from "date-fns";

interface Props {
  date: Date;
  onSelect: (d: Date) => void;
}

// Guide §3.1/4.1: sidebar mini calendar. Custom grid instead of
// react-datepicker — kami-styled, no foreign component styles.
export default function MiniCalendar({ date, onSelect }: Props) {
  const start = startOfWeek(startOfMonth(date), { weekStartsOn: 1 });
  const days: Date[] = [];
  for (let i = 0; i < 42; i++) days.push(addDays(start, i));

  return (
    <div className="rounded-[8px] bg-[var(--bg)] p-3 shadow-ring">
      <p
        className="mb-2 text-center text-[13px] font-medium text-[var(--fg-2)]"
        style={{ fontFamily: "var(--font-dm-sans)" }}
      >
        {format(date, "MMMM yyyy")}
      </p>
      <div className="grid grid-cols-7 gap-1 text-center">
        {["M", "T", "W", "T", "F", "S", "S"].map((d, i) => (
          <span
            key={i}
            className="text-[10px] uppercase text-[var(--meta)]"
            style={{ fontFamily: "var(--font-dm-sans)" }}
          >
            {d}
          </span>
        ))}
        {days.map((d) => {
          const inMonth = isSameMonth(d, date);
          const today = isToday(d);
          const selected = isSameDay(d, date);
          return (
            <button
              key={d.toISOString()}
              onClick={() => onSelect(d)}
              className={`h-7 rounded-[4px] text-[12px] transition-colors ${
                today
                  ? "bg-[var(--accent)] text-[var(--accent-on)]"
                  : selected
                    ? "bg-[var(--accent-light)] text-white"
                    : inMonth
                      ? "text-[var(--fg-2)] hover:bg-[var(--surface-warm)]"
                      : "text-[var(--border-soft)] hover:bg-[var(--surface-warm)]"
              }`}
              style={{ fontFamily: "var(--font-dm-sans)" }}
            >
              {format(d, "d")}
            </button>
          );
        })}
      </div>
    </div>
  );
}
