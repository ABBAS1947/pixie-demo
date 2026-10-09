"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { ListChecks, Trash2, X } from "lucide-react";
import Dialog from "@/components/Dialog";
import { getQuickNote, saveQuickNote, type QuickNoteLine } from "@/lib/api";
import styles from "./QuickCapturePanel.module.css";

const CHECKLIST_LIMIT = 12;
const SAVE_DELAY_MS = 650;

type Draft = { body: string; checklist: QuickNoteLine[] };
const emptyDraft = (): Draft => ({ body: "", checklist: [] });
const snapshot = (draft: Draft) => JSON.stringify(draft);

export default function QuickCapturePanel({ ownerId }: { ownerId: string }) {
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [saveState, setSaveState] = useState<"saved" | "unsaved" | "saving" | "error" | "conflict">("saved");
  const [saveError, setSaveError] = useState("");
  const [confirmClear, setConfirmClear] = useState(false);
  const draftRef = useRef<Draft>(emptyDraft());
  const savedRef = useRef(snapshot(draftRef.current));
  const revisionRef = useRef(0);
  const bodyLimitRef = useRef(2000);
  const savingRef = useRef<Promise<void> | null>(null);
  const activeRef = useRef(true);
  const blockedRef = useRef(false);
  const bodyRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    activeRef.current = true;
    let active = true;
    void getQuickNote().then((note) => {
      if (!active) return;
      const next = { body: note.body, checklist: note.checklist };
      draftRef.current = next;
      savedRef.current = snapshot(next);
      revisionRef.current = note.revision;
      bodyLimitRef.current = Math.max(2000, note.body.length);
      blockedRef.current = false;
      setDraft(next);
      setLoadError(false);
      setSaveState("saved");
      setSaveError("");
    }).catch(() => {
      if (active) setLoadError(true);
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; activeRef.current = false; };
  }, [ownerId, loadAttempt]);

  const changeDraft = (next: Draft) => {
    draftRef.current = next;
    setDraft(next);
    if (!blockedRef.current) setSaveState("unsaved");
  };

  const flush = useCallback((): Promise<void> => {
    if (savingRef.current || blockedRef.current || !activeRef.current) return savingRef.current ?? Promise.resolve();
    const run = async () => {
      while (activeRef.current && !blockedRef.current && snapshot(draftRef.current) !== savedRef.current) {
        const current = draftRef.current;
        const sent = snapshot(current);
        setSaveState("saving");
        setSaveError("");
        try {
          const saved = await saveQuickNote({ ...current, revision: revisionRef.current });
          revisionRef.current = saved.revision;
          savedRef.current = sent;
          if (activeRef.current && snapshot(draftRef.current) === sent) setSaveState("saved");
        } catch (cause) {
          if (!activeRef.current) return;
          const message = cause instanceof Error ? cause.message : "Could not save this note.";
          const conflict = message.includes("changed elsewhere");
          blockedRef.current = conflict;
          setSaveState(conflict ? "conflict" : "error");
          setSaveError(message);
          return;
        }
      }
    };
    const pending = run().finally(() => { savingRef.current = null; });
    savingRef.current = pending;
    return pending;
  }, []);

  useEffect(() => {
    if (loading || loadError || blockedRef.current || snapshot(draft) === savedRef.current) return;
    const timer = window.setTimeout(() => { void flush(); }, SAVE_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [draft, loading, loadError, flush]);

  useLayoutEffect(() => {
    const input = bodyRef.current;
    if (!input) return;
    const fitText = () => {
      input.style.height = "auto";
      input.style.height = `${Math.max(156, input.scrollHeight)}px`;
    };
    fitText();
    window.addEventListener("resize", fitText);
    return () => window.removeEventListener("resize", fitText);
  }, [draft.body, loading]);

  useEffect(() => {
    const saveWhenHidden = () => { if (document.visibilityState === "hidden") void flush(); };
    document.addEventListener("visibilitychange", saveWhenHidden);
    return () => document.removeEventListener("visibilitychange", saveWhenHidden);
  }, [flush]);

  const editLine = (id: string, update: Partial<QuickNoteLine>) => {
    changeDraft({ ...draftRef.current, checklist: draftRef.current.checklist.map((line) => line.id === id ? { ...line, ...update } : line) });
  };

  const addLine = () => {
    if (draftRef.current.checklist.length >= CHECKLIST_LIMIT) return;
    const id = crypto.randomUUID();
    changeDraft({ ...draftRef.current, checklist: [...draftRef.current.checklist, { id, text: "", checked: false }] });
    window.requestAnimationFrame(() => document.getElementById(`quick-check-${id}`)?.focus());
    window.setTimeout(() => void flush(), 0);
  };

  const removeLine = (id: string) => {
    changeDraft({ ...draftRef.current, checklist: draftRef.current.checklist.filter((item) => item.id !== id) });
    window.setTimeout(() => void flush(), 0);
  };

  const clearNote = () => {
    setConfirmClear(false);
    changeDraft(emptyDraft());
    void flush();
  };

  return <section className={styles.panel} aria-labelledby="quick-note-title">
    <div className={styles.heading}>
      <h2 id="quick-note-title">Quick note</h2>
      {!loading && !loadError && <div className={styles.headingActions}>
        {(draft.body || draft.checklist.length > 0) && <button type="button" className={styles.iconButton} onClick={() => setConfirmClear(true)} aria-label="Clear quick note" title="Clear quick note"><Trash2 size={16} aria-hidden="true" /></button>}
        <button type="button" className={styles.iconButton} onClick={addLine} disabled={draft.checklist.length >= CHECKLIST_LIMIT} aria-label="Add checklist item" title="Add checklist item"><ListChecks size={18} aria-hidden="true" /></button>
      </div>}
    </div>

    {loading ? <p className={styles.message} role="status">Loading your note…</p>
      : loadError ? <div className={styles.message} role="alert">Your note could not be loaded. <button type="button" onClick={() => { setLoading(true); setLoadError(false); setLoadAttempt((value) => value + 1); }}>Try again</button></div>
        : <>
          <div className={styles.paper}>
            <label className={styles.srOnly} htmlFor="quick-note-body">Quick note text</label>
            <textarea ref={bodyRef} id="quick-note-body" className={styles.body} value={draft.body} maxLength={bodyLimitRef.current} onChange={(event) => changeDraft({ ...draftRef.current, body: event.target.value })} onBlur={() => void flush()} placeholder="Take a note…" />
            {draft.checklist.length > 0 && <ul className={styles.checklist}>
              {draft.checklist.map((line) => <li key={line.id}>
                <label className={styles.checkboxTap}><input type="checkbox" checked={line.checked} aria-label={`Mark checklist item ${line.text || "blank"} complete`} onChange={(event) => { editLine(line.id, { checked: event.target.checked }); window.setTimeout(() => void flush(), 0); }} /></label>
                <input id={`quick-check-${line.id}`} type="text" value={line.text} maxLength={500} aria-label="Checklist item text" placeholder="List item" onChange={(event) => editLine(line.id, { text: event.target.value })} onBlur={() => void flush()} />
                <button type="button" className={styles.removeLine} onClick={() => removeLine(line.id)} aria-label={`Remove checklist item ${line.text || "blank"}`}><X size={16} aria-hidden="true" /></button>
              </li>)}
            </ul>}
          </div>
          {(saveState === "error" || saveState === "conflict") && <div className={styles.error} role="alert"><span>{saveError}</span>{saveState === "error" && <button type="button" onClick={() => void flush()}>Retry</button>}</div>}
        </>}

    {confirmClear && <Dialog open role="alertdialog" title="Clear this note?" message="This removes the text and every checklist item." confirmLabel="Clear note" cancelLabel="Keep note" destructive onConfirm={clearNote} onCancel={() => setConfirmClear(false)} />}
  </section>;
}
