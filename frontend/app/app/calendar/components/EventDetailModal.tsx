"use client";

import { useState } from "react";
import { X } from "lucide-react";
import { formatEventTime } from "@/lib/calendar-utils";
import { kindLabel } from "@/lib/event-mappers";
import type { Deadline, DeadlineKind } from "@/lib/types";

interface Props {
  deadline: Deadline;
  isGoogleConnected: boolean;
  onClose: () => void;
  onUpdate: (
    id: string,
    patch: Partial<{
      title: string;
      due_at: string;
      kind: DeadlineKind;
      pace_plan: string | null;
      confirmed: boolean;
      status: string;
    }>,
  ) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
}

function toLocalInput(iso: string): string {
  const d = new Date(iso);
  const off = d.getTimezoneOffset();
  return new Date(d.getTime() - off * 60000).toISOString().slice(0, 16);
}

// Guide §5.3/5.4: detail modal with confirm/dismiss workflow + edit/delete.
export default function EventDetailModal({
  deadline,
  isGoogleConnected,
  onClose,
  onUpdate,
  onDelete,
}: Props) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(deadline.title);
  const [due, setDue] = useState(toLocalInput(deadline.due_at));
  const [kind, setKind] = useState<DeadlineKind>(deadline.kind);
  const [pace, setPace] = useState(deadline.pace_plan ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await onUpdate(deadline.id, {
        title: title.trim(),
        due_at: new Date(due).toISOString(),
        kind,
        pace_plan: pace.trim() || null,
      });
      setEditing(false);
      setBusy(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update");
      setBusy(false);
    }
  }

  async function confirm() {
    setBusy(true);
    try {
      await onUpdate(deadline.id, { confirmed: true });
      setBusy(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to confirm");
      setBusy(false);
    }
  }

  const inputCls =
    "w-full rounded-[8px] border border-[var(--border)] bg-[var(--bg)] px-3 py-2 text-[14px] text-[var(--fg)] focus:border-[var(--accent)] focus:outline-none";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/20 p-4">
      <div className="relative w-full max-w-md rounded-[12px] bg-[var(--surface)] p-6 shadow-[0_8px_48px_rgba(0,0,0,0.12)]">
        <button
          onClick={onClose}
          className="absolute right-4 top-4 text-[var(--meta)] transition-colors hover:text-[var(--fg)]"
          aria-label="Close"
        >
          <X size={16} />
        </button>

        {editing ? (
          <>
            <h2 className="mb-4 text-[20px]" style={{ fontFamily: "var(--font-dm-sans)", fontWeight: 500 }}>
              Edit deadline
            </h2>
            <div className="space-y-4">
              <div>
                <label className="mb-1 block text-[13px] text-[var(--meta)]" style={{ fontFamily: "var(--font-dm-sans)" }}>
                  Title
                </label>
                <input value={title} onChange={(e) => setTitle(e.target.value)} className={inputCls} style={{ fontFamily: "var(--font-dm-sans)" }} />
              </div>
              <div>
                <label className="mb-1 block text-[13px] text-[var(--meta)]" style={{ fontFamily: "var(--font-dm-sans)" }}>
                  Due date
                </label>
                <input type="datetime-local" value={due} onChange={(e) => setDue(e.target.value)} className={inputCls} style={{ fontFamily: "var(--font-dm-sans)" }} />
              </div>
              <div>
                <label className="mb-1 block text-[13px] text-[var(--meta)]" style={{ fontFamily: "var(--font-dm-sans)" }}>
                  Type
                </label>
                <select value={kind} onChange={(e) => setKind(e.target.value as DeadlineKind)} className={inputCls} style={{ fontFamily: "var(--font-dm-sans)" }}>
                  <option value="assignment">Assignment</option>
                  <option value="exam">Exam</option>
                  <option value="project">Project</option>
                </select>
              </div>
              <div>
                <label className="mb-1 block text-[13px] text-[var(--meta)]" style={{ fontFamily: "var(--font-dm-sans)" }}>
                  Pace plan
                </label>
                <textarea value={pace} onChange={(e) => setPace(e.target.value)} rows={3} className={inputCls} style={{ fontFamily: "var(--font-body)" }} />
              </div>
              {error ? <p className="text-[13px] text-[var(--danger)]">{error}</p> : null}
              <div className="flex gap-2">
                <button onClick={save} disabled={busy} className="btn-3d w-full disabled:opacity-60">
                  <span className="bs" />
                  <span className="be" />
                  <span className="bf">Save</span>
                </button>
                <button onClick={() => setEditing(false)} className="w-full rounded-[8px] border border-[var(--border)] px-4 py-2 text-sm text-[var(--meta)]" style={{ fontFamily: "var(--font-dm-sans)" }}>
                  Cancel
                </button>
              </div>
            </div>
          </>
        ) : (
          <>
            <h2 className="mb-2 text-[20px]" style={{ fontFamily: "var(--font-dm-sans)", fontWeight: 500 }}>
              {deadline.title}
            </h2>
            <div className="flex flex-wrap items-center gap-2 text-[13px] text-[var(--meta)]" style={{ fontFamily: "var(--font-dm-sans)" }}>
              <span
                className="rounded-[4px] px-2 py-0.5 text-[12px] font-medium text-[var(--fg-2)]"
                style={{ fontFamily: "var(--font-dm-sans)", background: "var(--surface-warm)" }}
              >
                {kindLabel(deadline.kind)}
              </span>
              {deadline.course?.name ? (
                <span className="rounded-[4px] px-2 py-0.5 text-[12px]" style={{ fontFamily: "var(--font-dm-sans)", background: "var(--surface-warm)" }}>
                  {deadline.course.name}
                </span>
              ) : null}
              <span>{formatEventTime(deadline.due_at)}</span>
              {deadline.synced_to_google ? (
                <span className="text-[11px] text-[var(--success)]">· Synced to Google</span>
              ) : null}
              {!deadline.confirmed ? (
                <span className="rounded-[4px] border border-dashed border-[var(--meta)] px-2 py-0.5 text-[11px] text-[var(--meta)]">
                  Unconfirmed
                </span>
              ) : null}
            </div>

            {deadline.pace_plan ? (
              <div className="mt-4 rounded-[6px] bg-[var(--bg)] p-3 text-sm text-[var(--fg-2)]" style={{ fontFamily: "var(--font-body)" }}>
                {deadline.pace_plan}
              </div>
            ) : null}

            <div className="mt-5 flex flex-wrap items-center gap-2">
              {!deadline.confirmed ? (
                <>
                  <button
                    onClick={confirm}
                    disabled={busy}
                    className="rounded-[6px] bg-[var(--success)] px-3 py-1.5 text-sm font-medium text-white disabled:opacity-60"
                    style={{ fontFamily: "var(--font-dm-sans)" }}
                  >
                    Confirm
                  </button>
                  <button
                    onClick={() => onDelete(deadline.id)}
                    disabled={busy}
                    className="rounded-[6px] bg-[var(--surface-warm)] px-3 py-1.5 text-sm text-[var(--fg-2)] disabled:opacity-60"
                    style={{ fontFamily: "var(--font-dm-sans)" }}
                  >
                    Dismiss
                  </button>
                </>
              ) : null}
              <button
                onClick={() => setEditing(true)}
                className="rounded-[6px] px-3 py-1.5 text-sm text-[var(--meta)] transition-colors hover:text-[var(--fg)]"
                style={{ fontFamily: "var(--font-dm-sans)" }}
              >
                Edit
              </button>
              <button
                onClick={() => onDelete(deadline.id)}
                className="ml-auto rounded-[6px] px-3 py-1.5 text-sm text-[var(--danger)] transition-colors hover:bg-[var(--danger)]/10"
                style={{ fontFamily: "var(--font-dm-sans)" }}
              >
                Delete
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
