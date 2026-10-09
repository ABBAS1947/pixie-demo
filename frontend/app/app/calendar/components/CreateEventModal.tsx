"use client";

import { useState } from "react";
import { X } from "lucide-react";
import type { DeadlineKind } from "@/lib/types";

export interface CreateEventData {
  title: string;
  due_at: string;
  kind: DeadlineKind;
  pace_plan?: string;
}

interface Props {
  initialDate?: Date;
  onClose: () => void;
  onSubmit: (data: CreateEventData) => Promise<void>;
}

function toLocalInput(d: Date): string {
  const off = d.getTimezoneOffset();
  return new Date(d.getTime() - off * 60000).toISOString().slice(0, 16);
}

// Guide §4.5: centered modal, title/due/type/pace-plan form.
export default function CreateEventModal({ initialDate, onClose, onSubmit }: Props) {
  const [title, setTitle] = useState("");
  const [due, setDue] = useState(initialDate ? toLocalInput(initialDate) : "");
  const [kind, setKind] = useState<DeadlineKind>("assignment");
  const [pace, setPace] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim() || !due) {
      setError("Title and due date are required.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onSubmit({
        title: title.trim(),
        due_at: new Date(due).toISOString(),
        kind,
        pace_plan: pace.trim() || undefined,
      });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create deadline");
      setBusy(false);
    }
  }

  const inputCls =
    "w-full rounded-[8px] border border-[var(--border)] bg-[var(--bg)] px-3 py-2 text-[14px] text-[var(--fg)] focus:border-[var(--accent)] focus:outline-none";
  const labelCls = "mb-1 block text-[13px] text-[var(--meta)]";

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
        <h2
          className="mb-4 text-[20px] text-[var(--fg)]"
          style={{ fontFamily: "var(--font-dm-sans)", fontWeight: 500 }}
        >
          Add deadline
        </h2>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className={labelCls} style={{ fontFamily: "var(--font-dm-sans)" }}>
              Title
            </label>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className={inputCls}
              style={{ fontFamily: "var(--font-dm-sans)" }}
              placeholder="Chemistry — Unit 3 exam"
              autoFocus
            />
          </div>
          <div>
            <label className={labelCls} style={{ fontFamily: "var(--font-dm-sans)" }}>
              Due date
            </label>
            <input
              type="datetime-local"
              value={due}
              onChange={(e) => setDue(e.target.value)}
              className={inputCls}
              style={{ fontFamily: "var(--font-dm-sans)" }}
            />
          </div>
          <div>
            <label className={labelCls} style={{ fontFamily: "var(--font-dm-sans)" }}>
              Type
            </label>
            <select
              value={kind}
              onChange={(e) => setKind(e.target.value as DeadlineKind)}
              className={inputCls}
              style={{ fontFamily: "var(--font-dm-sans)" }}
            >
              <option value="assignment">Assignment</option>
              <option value="exam">Exam</option>
              <option value="project">Project</option>
            </select>
          </div>
          <div>
            <label className={labelCls} style={{ fontFamily: "var(--font-dm-sans)" }}>
              Pace plan (optional)
            </label>
            <textarea
              value={pace}
              onChange={(e) => setPace(e.target.value)}
              rows={3}
              className={inputCls}
              style={{ fontFamily: "var(--font-body)" }}
              placeholder="Review ionic vs covalent bonds (Mon), practice stoichiometry (Wed)…"
            />
          </div>
          {error ? (
            <p className="text-[13px] text-[var(--danger)]" style={{ fontFamily: "var(--font-dm-sans)" }}>
              {error}
            </p>
          ) : null}
          <div className="flex gap-2 pt-1">
            <button
              type="submit"
              disabled={busy}
              className="btn-3d w-full disabled:opacity-60"
            >
              <span className="bs" />
              <span className="be" />
              <span className="bf">{busy ? "Creating…" : "Create"}</span>
            </button>
            <button
              type="button"
              onClick={onClose}
              className="w-full rounded-[8px] border border-[var(--border)] px-4 py-2.5 text-sm text-[var(--meta)] transition-colors hover:text-[var(--fg)]"
              style={{ fontFamily: "var(--font-dm-sans)" }}
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
