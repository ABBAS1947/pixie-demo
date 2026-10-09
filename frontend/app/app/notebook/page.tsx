"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import Dialog from "@/components/Dialog";
import NoteEditorPane, { type SaveStatus } from "@/components/notebook/NoteEditorPane";
import { deleteNote, getNote, updateNote } from "@/lib/api";
import type { Note } from "@/lib/types";

export default function NotebookPage() {
  const router = useRouter();
  const [note, setNote] = useState<Note | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const noteRef = useRef<Note | null>(null);
  const dirtyRef = useRef(false);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const saveTaskRef = useRef<Promise<boolean> | null>(null);

  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("noteId");
    if (!id) { router.replace("/app/library"); return; }
    let current = true;
    void getNote(id).then((loaded) => {
      if (!current) return;
      noteRef.current = loaded;
      setNote(loaded);
    }).catch((cause) => {
      if (current) setError(cause instanceof Error ? cause.message : "This note could not be opened.");
    }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [router]);

  const persist = useCallback(async () => {
    if (saveTaskRef.current) await saveTaskRef.current;
    if (!dirtyRef.current || !noteRef.current) return true;
    const snapshot = noteRef.current;
    dirtyRef.current = false;
    const task = updateNote(snapshot.id, {
      title: snapshot.title,
      content: snapshot.content,
      tags: snapshot.tags.join(","),
      folder_id: snapshot.folderId ?? null,
    }).then((saved) => {
      if (noteRef.current === snapshot) {
        noteRef.current = saved;
        setNote(saved);
        setSaveStatus("saved");
      }
      return true;
    }).catch((cause) => {
      dirtyRef.current = true;
      setSaveStatus("idle");
      setError(cause instanceof Error ? cause.message : "Your changes could not be saved.");
      return false;
    });
    saveTaskRef.current = task;
    const saved = await task;
    if (saveTaskRef.current === task) saveTaskRef.current = null;
    return saved;
  }, []);

  const flushPendingSave = useCallback(async () => {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = null;
    while (dirtyRef.current || saveTaskRef.current) {
      if (!(await persist())) return false;
    }
    return true;
  }, [persist]);

  useEffect(() => () => { void flushPendingSave(); }, [flushPendingSave]);

  function changeNote(patch: Partial<{ title: string; content: string; tags: string }>) {
    const current = noteRef.current;
    if (!current) return;
    const next: Note = {
      ...current,
      ...patch,
      tags: patch.tags === undefined ? current.tags : patch.tags.split(",").map((tag) => tag.trim()).filter(Boolean),
    };
    noteRef.current = next;
    setNote(next);
    dirtyRef.current = true;
    setSaveStatus("saving");
    setError(null);
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => { void persist(); }, 700);
  }

  async function leaveEditor() {
    if (await flushPendingSave()) router.replace("/app/library");
  }

  async function removeNote() {
    if (!noteRef.current) return;
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = null;
    if (saveTaskRef.current) await saveTaskRef.current;
    try {
      await deleteNote(noteRef.current.id);
      dirtyRef.current = false;
      setConfirmDelete(false);
      router.replace("/app/library");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "This note could not be deleted.");
      setConfirmDelete(false);
    }
  }

  if (!note) return <main className="notes-editor-page"><div className="notes-frame notes-editor-frame"><p role={error ? "alert" : "status"}>{error || (loading ? "Opening your note…" : "Opening Library…")}</p>{error && <Link href="/app/library">Back to Library</Link>}</div></main>;

  return <>
    <main className="notes-editor-page"><div className="notes-frame notes-editor-frame">
      {error && <div className="notes-error" role="alert">{error}</div>}
      <NoteEditorPane key={note.id} note={note} saveStatus={saveStatus} onBack={() => void leaveEditor()} onChange={changeNote} onDelete={() => setConfirmDelete(true)} />
    </div></main>
    {confirmDelete && <Dialog open role="alertdialog" title="Delete this note?" message="This note and its edits will be removed permanently. This cannot be undone." confirmLabel="Delete note" cancelLabel="Cancel" destructive onConfirm={() => void removeNote()} onCancel={() => setConfirmDelete(false)} />}
  </>;
}
