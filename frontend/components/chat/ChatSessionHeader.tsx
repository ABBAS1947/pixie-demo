"use client";

import { ChevronDown, Pencil, Trash2 } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";

interface Props {
  title: string;
  onRename: (title: string) => Promise<void>;
  onDelete: () => Promise<void>;
}

export default function ChatSessionHeader({ title, onRename, onDelete }: Props) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(title);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const menuRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const editRef = useRef<HTMLInputElement>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const returnFocusRef = useRef(false);

  useEffect(() => {
    if (!menuOpen) return;
    const closeOnOutside = (event: PointerEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setMenuOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener("pointerdown", closeOnOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOnOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [menuOpen]);

  useEffect(() => {
    if (editing) editRef.current?.focus();
    if (!editing && returnFocusRef.current) {
      triggerRef.current?.focus();
      returnFocusRef.current = false;
    }
  }, [editing]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (confirmOpen && dialog && !dialog.open) dialog.showModal();
    if (!confirmOpen && dialog?.open) dialog.close();
  }, [confirmOpen]);

  async function saveTitle(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const next = draft.trim().replace(/\s+/g, " ");
    if (!next) {
      setError("Enter a chat title.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await onRename(next);
      returnFocusRef.current = true;
      setEditing(false);
    } catch {
      setError("Couldn’t rename this chat. Try again.");
    } finally {
      setBusy(false);
    }
  }

  async function confirmDelete() {
    setBusy(true);
    setError("");
    try {
      await onDelete();
      setConfirmOpen(false);
    } catch {
      setError("Couldn’t delete this chat. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return <header className="chat-session-header">
    <div className="chat-session-header-inner">
      {editing ? <form className="chat-session-rename" onSubmit={saveTitle}>
        <input ref={editRef} value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Escape") { returnFocusRef.current = true; setEditing(false); setError(""); } }} maxLength={200} aria-label="Chat title" />
        <button type="submit" disabled={busy}>Save</button>
        <button type="button" onClick={() => { returnFocusRef.current = true; setEditing(false); setError(""); }} disabled={busy}>Cancel</button>
      </form> : <div ref={menuRef} className="chat-session-title-wrap">
        <button ref={triggerRef} type="button" className="chat-session-title-button" aria-expanded={menuOpen} aria-controls="chat-session-actions" onClick={() => setMenuOpen((open) => !open)}>
          <span>{title.replace(/^\*\*\s*/, "").replace(/\s*\*\*$/, "")}</span>
          <ChevronDown size={17} aria-hidden="true" />
        </button>
        {menuOpen && <div id="chat-session-actions" className="chat-session-actions">
          <button type="button" onClick={() => { setDraft(title); setError(""); setMenuOpen(false); setEditing(true); }}><Pencil size={17} aria-hidden="true" /> Rename</button>
          <button type="button" className="chat-session-delete-action" onClick={() => { setError(""); setMenuOpen(false); setConfirmOpen(true); }}><Trash2 size={17} aria-hidden="true" /> Delete</button>
        </div>}
      </div>}
      {error && !confirmOpen && <p className="chat-session-error" role="alert">{error}</p>}
    </div>
    <dialog ref={dialogRef} className="chat-session-confirm" aria-labelledby="chat-delete-title" aria-describedby="chat-delete-description" onCancel={(event) => { if (busy) event.preventDefault(); }} onClose={() => setConfirmOpen(false)}>
      <h2 id="chat-delete-title">Delete this chat?</h2>
      <p id="chat-delete-description">This conversation will be permanently deleted.</p>
      {error && <p className="chat-session-error" role="alert">{error}</p>}
      <div>
        <button type="button" autoFocus onClick={() => setConfirmOpen(false)} disabled={busy}>Cancel</button>
        <button type="button" className="chat-session-confirm-delete" onClick={confirmDelete} disabled={busy}>{busy ? "Deleting…" : "Delete chat"}</button>
      </div>
    </dialog>
  </header>;
}
