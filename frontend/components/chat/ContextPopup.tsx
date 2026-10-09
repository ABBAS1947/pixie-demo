"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { listFiles, listNotes, searchNotes, type FileDoc } from "@/lib/api";
import type { Note } from "@/lib/types";

export interface ContextChip {
  kind: "note" | "file";
  id: string;
  title: string;
}

/** Context picker anchored above the composer action row. */
export default function ContextPopup({
  chips,
  onToggle,
  onClose,
  align = "right",
}: {
  chips: ContextChip[];
  onToggle: (chip: ContextChip) => void;
  onClose: () => void;
  align?: "left" | "right";
}) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [notes, setNotes] = useState<Note[]>([]);
  const [files, setFiles] = useState<FileDoc[]>([]);

  useEffect(() => {
    Promise.all([listNotes(), listFiles()])
      .then(([nextNotes, nextFiles]) => {
        setNotes(nextNotes.slice(0, 4));
        setFiles(nextFiles.slice(0, 4));
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!query.trim()) return;
    const timer = window.setTimeout(() => {
      searchNotes(query.trim()).then(setNotes).catch(() => {});
    }, 250);
    return () => window.clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const q = query.trim().toLowerCase();
  const visibleFiles = (q ? files.filter((file) => `${file.title} ${file.original_name}`.toLowerCase().includes(q)) : files).slice(0, 4);
  const attached = (kind: ContextChip["kind"], id: string) => chips.some((chip) => chip.kind === kind && chip.id === id);

  function item(kind: ContextChip["kind"], id: string, title: string, href: string) {
    const selected = attached(kind, id);
    return (
      <div key={`${kind}-${id}`} className="flex min-w-0 items-center rounded-lg" style={{ backgroundColor: selected ? "var(--color-orange)" : "rgba(250,248,243,0.48)", color: selected ? "var(--color-white)" : "var(--color-dark)" }}>
        <button type="button" onClick={() => onToggle({ kind, id, title })} className="min-w-0 flex-1 truncate px-3 py-2 text-left font-body" style={{ fontSize: 12, fontWeight: 700 }} title={title}>{title}</button>
        <button type="button" onClick={() => router.push(href)} aria-label={`Open ${title}`} className="px-3 py-2 font-body" style={{ fontSize: 12, opacity: 0.65 }}>↗</button>
      </div>
    );
  }

  return (
    <>
      <button type="button" aria-label="Close context picker" className="fixed inset-0 z-40 cursor-default" onClick={onClose} />
      <div className={`common-popover absolute bottom-[calc(100%+12px)] ${align === "left" ? "left-0" : "right-0"} z-50 w-[min(320px,calc(100vw-32px))] overflow-hidden p-4 shadow-elevated`} style={{ backgroundColor: "var(--color-cream)", borderRadius: 18, color: "var(--color-dark)" }}>
        <div className="mb-3 flex items-center justify-between">
          <span className="font-body" style={{ fontSize: 10, fontWeight: 800, letterSpacing: "0.14em", opacity: 0.55 }}>ADD CONTEXT</span>
          <button type="button" onClick={onClose} aria-label="Close" style={{ fontSize: 18, lineHeight: 1 }}>×</button>
        </div>
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search notes and files" className="mb-3 w-full rounded-lg px-3 py-2 font-body outline-none" style={{ background: "rgba(250,248,243,0.75)", border: "1px solid rgba(66,25,1,0.16)", color: "var(--color-dark)", fontSize: 13 }} />
        <p className="mb-1 font-body" style={{ fontSize: 10, fontWeight: 800, letterSpacing: "0.12em", opacity: 0.5 }}>NOTES</p>
        <div className="grid gap-1.5">{notes.map((note) => item("note", note.id, note.title || "Untitled note", `/app/notebook?noteId=${encodeURIComponent(note.id)}`))}</div>
        <p className="mb-1 mt-3 font-body" style={{ fontSize: 10, fontWeight: 800, letterSpacing: "0.12em", opacity: 0.5 }}>FILES</p>
        <div className="grid gap-1.5">{visibleFiles.map((file) => item("file", file.id, file.title || file.original_name, "/app/library?view=files"))}</div>
        {notes.length === 0 && visibleFiles.length === 0 && <p className="mt-2 font-body" style={{ fontSize: 12, opacity: 0.6 }}>Nothing matches your search.</p>}
      </div>
    </>
  );
}
