"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, FileText, FolderPlus, Pencil, Plus, Upload, X } from "lucide-react";
import { createFolder, createNote, listFiles, listNoteFolders, listNotes, uploadFile, type FileDoc, type NoteFolderDoc } from "@/lib/api";
import SourceFilesPanel from "./SourceFilesPanel";
import { getReviewConfig } from "@/lib/reviewApi";
import type { Note } from "@/lib/types";
import styles from "./library.module.css";

type LibraryFolder = NoteFolderDoc;
const colorLuminance = (color: string) => {
  const channels = color.slice(1).match(/.{2}/g)?.map((channel) => parseInt(channel, 16) / 255) ?? [];
  if (channels.length !== 3 || channels.some((channel) => !Number.isFinite(channel))) return 0;
  const [red, green, blue] = channels.map((channel) => channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4);
  return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
};
const contrastRatio = (first: string, second: string) => {
  const [lighter, darker] = [colorLuminance(first), colorLuminance(second)].sort((a, b) => b - a);
  return (lighter + 0.05) / (darker + 0.05);
};
const vividFolderColors = ["#2387F5", "#E53935", "#FF7A00", "#7B2FF7", "#00A6E8", "#D81B60", "#2E9B45", "#F4B400", "#3949AB", "#A52DB5", "#546E7A", "#7CB342"];
const folderColorAt = (index: number) => {
  if (index < vividFolderColors.length) return vividFolderColors[index];
  const hue = ((index - vividFolderColors.length) * 137.508 + 19) % 360;
  const saturation = 0.78;
  const lightness = 0.52;
  const chroma = (1 - Math.abs(2 * lightness - 1)) * saturation;
  const section = hue / 60;
  const second = chroma * (1 - Math.abs(section % 2 - 1));
  const [red, green, blue] = section < 1 ? [chroma, second, 0]
    : section < 2 ? [second, chroma, 0]
      : section < 3 ? [0, chroma, second]
        : section < 4 ? [0, second, chroma]
          : section < 5 ? [second, 0, chroma]
            : [chroma, 0, second];
  const offset = lightness - chroma / 2;
  return `#${[red, green, blue].map((channel) => Math.round((channel + offset) * 255).toString(16).padStart(2, "0")).join("")}`;
};
const folderStyle = (storedColor: string): React.CSSProperties => {
  const color = /^#[\da-f]{6}$/i.test(storedColor) ? storedColor : vividFolderColors[0];
  const ink = contrastRatio(color, "#421901") >= contrastRatio(color, "#FFFFFF") ? "#421901" : "#FFFFFF";
  return { "--folder-color": color, "--folder-ink": ink } as React.CSSProperties;
};
const shortText = (value: string, limit = 118) => {
  const plain = value.replace(/^#+\s*/gm, "").replace(/[>*_`#]/g, "").replace(/\s+/g, " ").trim();
  return plain.length > limit ? `${plain.slice(0, limit).trimEnd()}…` : plain;
};
const dateLabel = (value: string) => new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(new Date(value));

export default function LibraryPage() {
  const router = useRouter();
  const [notes, setNotes] = useState<Note[]>([]);
  const [folders, setFolders] = useState<LibraryFolder[]>([]);
  const [files, setFiles] = useState<FileDoc[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [folderFilter, setFolderFilter] = useState<string | null>(null);
  const [viewAllNotes, setViewAllNotes] = useState(false);
  const [creatingNote, setCreatingNote] = useState(false);
  const [pickedFile, setPickedFile] = useState<File | null>(null);
  const [uploadFolderId, setUploadFolderId] = useState("");
  const [externalProcessingAllowed, setExternalProcessingAllowed] = useState<boolean | null>(null);
  const [uploading, setUploading] = useState(false);
  const [folderDialogOpen, setFolderDialogOpen] = useState(false);
  const [newFolderName, setNewFolderName] = useState("");
  const [creatingFolder, setCreatingFolder] = useState(false);
  const [folderDialogError, setFolderDialogError] = useState("");
  const [sourceFilesOpen, setSourceFilesOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const folderNameRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    try {
      const [nextNotes, nextFolders, nextFiles] = await Promise.all([listNotes(100), listNoteFolders(), listFiles(undefined, 100)]);
      setNotes(nextNotes);
      setFolders(nextFolders);
      setFiles(nextFiles);
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Your library could not be loaded.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { const timer = window.setTimeout(() => { void refresh(); }, 0); return () => window.clearTimeout(timer); }, [refresh]);
  useEffect(() => { const timer = window.setTimeout(() => { if (new URLSearchParams(window.location.search).get("view") === "files") setSourceFilesOpen(true); }, 0); return () => window.clearTimeout(timer); }, []);
  useEffect(() => {
    if (!pickedFile) return;
    let current = true;
    void getReviewConfig().then((config) => { if (current) setExternalProcessingAllowed(config.preferences.external_processing_consent); }).catch(() => { if (current) setExternalProcessingAllowed(false); });
    return () => { current = false; };
  }, [pickedFile]);
  useEffect(() => {
    if (!files.some((file) => ["pending", "processing"].includes(file.status))) return;
    const timer = window.setInterval(() => { void refresh(); }, 3000);
    return () => window.clearInterval(timer);
  }, [files, refresh]);

  const visibleNotes = useMemo(() => {
    const list = folderFilter ? notes.filter((note) => note.folderId === folderFilter) : notes;
    const sorted = [...list].sort((a, b) => new Date(b.updatedAt ?? b.createdAt).getTime() - new Date(a.updatedAt ?? a.createdAt).getTime());
    return viewAllNotes ? sorted : sorted.slice(0, 4);
  }, [folderFilter, notes, viewAllNotes]);
  const folderCounts = useMemo(() => new Map(folders.map((folder) => [folder.id, (folder.note_count ?? notes.filter((note) => note.folderId === folder.id).length) + (folder.file_count ?? files.filter((file) => file.folder_id === folder.id).length)])), [files, folders, notes]);

  function addFolder() {
    setNewFolderName("");
    setFolderDialogError("");
    setFolderDialogOpen(true);
  }

  async function submitFolder(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = newFolderName.trim();
    if (!name || creatingFolder) return;
    setCreatingFolder(true);
    setFolderDialogError("");
    try {
      await createFolder(name);
      await refresh();
      setFolderDialogOpen(false);
      setNewFolderName("");
    } catch (cause) {
      setFolderDialogError(cause instanceof Error ? cause.message : "The folder could not be created. Please try again.");
    } finally { setCreatingFolder(false); }
  }

  useEffect(() => {
    if (!folderDialogOpen) return;
    folderNameRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !creatingFolder) setFolderDialogOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [creatingFolder, folderDialogOpen]);

  async function newNote() {
    if (creatingNote) return;
    setCreatingNote(true);
    try {
      const note = await createNote({ title: "", content: "", folder_id: folderFilter });
      router.push(`/app/notebook?noteId=${encodeURIComponent(note.id)}`);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "A new note could not be created."); }
    finally { setCreatingNote(false); }
  }

  async function submitUpload(noteMode: "summary" | "full_text", folderId: string | null) {
    if (!pickedFile || uploading) return;
    setUploading(true);
    try {
      await uploadFile(pickedFile, { note_mode: noteMode, folder_id: folderId });
      setPickedFile(null);
      setUploadFolderId("");
      await refresh();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "The file could not be uploaded."); }
    finally { setUploading(false); if (inputRef.current) inputRef.current.value = ""; }
  }

  const selectedFolder = folders.find((folder) => folder.id === folderFilter);
  const folderColors = useMemo(() => {
    const stableOrder = [...folders].sort((first, second) => first.created_at.localeCompare(second.created_at) || first.id.localeCompare(second.id));
    const used = new Set<string>();
    return new Map(stableOrder.map((folder, index) => {
      let colorIndex = index;
      while (used.has(folderColorAt(colorIndex))) colorIndex += 1;
      const color = folderColorAt(colorIndex);
      used.add(color);
      return [folder.id, color];
    }));
  }, [folders]);
  return <main className={styles.page}>
    <header className={styles.header}>
      <div><h1>Notes & folders</h1></div>
      <div className={styles.actions}>
        <button className={styles.primaryAction} type="button" onClick={() => void newNote()} disabled={creatingNote}><Plus size={18} />{creatingNote ? "Creating…" : "New note"}</button>
        <button className={styles.uploadAction} type="button" onClick={() => inputRef.current?.click()}><Upload size={17} />Add material</button>
      </div>
      <input ref={inputRef} type="file" className={styles.hiddenInput} accept=".pdf,.doc,.docx,.txt,.png,.jpg,.jpeg,.gif,.webp" onChange={(event) => { setExternalProcessingAllowed(null); setPickedFile(event.target.files?.[0] ?? null); setUploadFolderId(folderFilter ?? ""); }} />
    </header>

    {error && <div className={styles.error} role="alert">{error}<button type="button" aria-label="Dismiss" onClick={() => setError("")}><X size={16} /></button></div>}

    <section className={styles.section} aria-labelledby="recent-heading">
      <div className={styles.sectionHeading}><div><h2 id="recent-heading">{selectedFolder ? selectedFolder.name : viewAllNotes ? "All notes" : "Recent notes"}</h2>{(selectedFolder || viewAllNotes) && <p>{selectedFolder ? "Notes saved in this subject folder" : `${notes.length} notes`}</p>}</div><div className={styles.headingActions}>{folderFilter && <button type="button" className={styles.textButton} onClick={() => setFolderFilter(null)}>All notes</button>}{notes.length > 4 && <button type="button" className={styles.textButton} onClick={() => setViewAllNotes((current) => !current)}>{viewAllNotes ? "Recent" : "See all"} <ArrowRight size={16} /></button>}</div></div>
      {loading ? <div className={styles.skeletonGrid} aria-label="Loading notes"><i /><i /><i /></div> : visibleNotes.length ? <div className={`${styles.noteGrid}${viewAllNotes ? ` ${styles.allNotes}` : ""}`}>{visibleNotes.map((note) => {
        const folder = folders.find((item) => item.id === note.folderId);
        return <article key={note.id} className={`${styles.noteCard}${folder ? ` ${styles.filedNote}` : ""}`} style={folder ? folderStyle(folderColors.get(folder.id) ?? folder.color) : undefined}>
          <Link href={`/app/notebook?noteId=${encodeURIComponent(note.id)}`} className={styles.noteMain} aria-label={`Open ${note.title || "Untitled note"}`}>
            <span className={styles.noteTitle}>{note.title?.trim() || "Untitled note"}</span>
            <span className={styles.noteDescription}>{shortText(note.content || note.excerpt) || "A note ready for your ideas."}</span>
          </Link>
          <div className={styles.noteFooter}><span>{dateLabel(note.createdAt)}</span>{folder ? <button type="button" onClick={() => setFolderFilter(folder.id)}>{folder.name}</button> : <span>Unfiled</span>}</div>
          <Link className={styles.editButton} href={`/app/notebook?noteId=${encodeURIComponent(note.id)}`} aria-label={`Edit ${note.title || "Untitled note"}`}><Pencil size={15} /></Link>
        </article>;
      })}</div> : <div className={styles.emptyNotes}><span className={styles.emptyIcon}><FileText size={21} /></span><div><h3>{selectedFolder ? "No notes in this folder yet" : "Your notes will appear here"}</h3><p>Create a note or turn a study file into a summary or full-text note.</p></div><button type="button" onClick={() => void newNote()} disabled={creatingNote}>{creatingNote ? "Creating…" : "Create a note"} <ArrowRight size={16} /></button></div>}
    </section>

    <section className={styles.section} aria-labelledby="folders-heading">
      <div className={styles.sectionHeading}><div><h2 id="folders-heading">Subject folders</h2></div><button type="button" className={styles.textButton} onClick={addFolder}><FolderPlus size={16} />New folder</button></div>
      {folders.length ? <div className={styles.folderGrid}>{folders.map((folder) => {
        const count = folderCounts.get(folder.id) ?? 0;
        return <button key={folder.id} type="button" className={`${styles.folderCard}${folderFilter === folder.id ? ` ${styles.folderSelected}` : ""}`} style={folderStyle(folderColors.get(folder.id) ?? folder.color)} onClick={() => setFolderFilter(folderFilter === folder.id ? null : folder.id)} aria-pressed={folderFilter === folder.id}>
          <svg className={styles.folderBack} viewBox="0 0 310 200" preserveAspectRatio="none" aria-hidden="true"><path d="M5 60V28C5 17 14 8 25 8H93C102 8 109 12 114 20L124 34C126 37 128 39 133 39H285C296 39 305 48 305 59V175C305 186 296 195 285 195H25C14 195 5 186 5 175Z" fill="currentColor" /></svg>
          {count > 0 && <span className={styles.folderPapers} aria-hidden="true"><span /><span /></span>}
          <svg className={styles.folderFront} viewBox="0 0 310 200" preserveAspectRatio="none" aria-hidden="true"><path d="M5 78C5 67 14 58 25 58H285C296 58 305 67 305 78V175C305 186 296 195 285 195H25C14 195 5 186 5 175Z" fill="currentColor" /></svg>
          <span className={styles.folderText}><strong>{folder.name}</strong><small>{count} {count === 1 ? "item" : "items"}</small></span>
        </button>;
      })}</div> : !loading && <button type="button" className={styles.addFolderCard} onClick={addFolder}><FolderPlus size={18} />Create a subject folder</button>}
    </section>

    <section className={styles.sourceFilesSection} aria-labelledby="source-files-heading">
      <div className={styles.sectionHeading}><div><h2 id="source-files-heading">Original files</h2></div><button type="button" className={styles.textButton} aria-expanded={sourceFilesOpen} aria-controls="source-files-panel" onClick={() => setSourceFilesOpen((open) => !open)}>{sourceFilesOpen ? "Hide files" : "Manage files"}<ArrowRight size={16} /></button></div>
      {sourceFilesOpen && <div id="source-files-panel" className={styles.sourceFilesPanel}><SourceFilesPanel files={files} folders={folders} onChanged={refresh} onUpload={() => inputRef.current?.click()} /></div>}
    </section>

    {folderDialogOpen && <div className={styles.modalBackdrop} role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !creatingFolder) setFolderDialogOpen(false); }}><section className={styles.modal} role="dialog" aria-modal="true" aria-labelledby="create-folder-title" aria-describedby="create-folder-description"><button type="button" className={styles.modalClose} aria-label="Close" onClick={() => setFolderDialogOpen(false)} disabled={creatingFolder}><X size={18} /></button><p className={styles.kicker}>ORGANIZE YOUR LIBRARY</p><h2 id="create-folder-title">Create a subject folder</h2><p id="create-folder-description" className={styles.dialogDescription}>Group notes and study files by subject.</p><form className={styles.folderForm} onSubmit={(event) => void submitFolder(event)}><label htmlFor="new-folder-name">Folder name</label><input ref={folderNameRef} id="new-folder-name" className={styles.folderNameInput} value={newFolderName} onChange={(event) => { setNewFolderName(event.target.value); setFolderDialogError(""); }} maxLength={255} placeholder="e.g. Biology" autoComplete="off" required disabled={creatingFolder} />{folderDialogError && <p className={styles.folderDialogError} role="alert">{folderDialogError}</p>}<div className={styles.dialogActions}><button type="button" className={styles.cancelButton} onClick={() => setFolderDialogOpen(false)} disabled={creatingFolder}>Cancel</button><button type="submit" className={styles.createButton} disabled={creatingFolder || !newFolderName.trim()}>{creatingFolder ? "Creating…" : "Create folder"}</button></div></form></section></div>}

    {pickedFile && <div className={styles.modalBackdrop} role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !uploading) setPickedFile(null); }}><section className={styles.modal} role="dialog" aria-modal="true" aria-labelledby="upload-choice-title"><button type="button" className={styles.modalClose} aria-label="Close" onClick={() => setPickedFile(null)} disabled={uploading}><X size={18} /></button><p className={styles.kicker}>ADD TO YOUR LIBRARY</p><h2 id="upload-choice-title">What should Pixie save?</h2><p className={styles.fileName}>{pickedFile.name}</p><label className={styles.folderSelect}>Save in <select value={uploadFolderId} onChange={(event) => setUploadFolderId(event.target.value)}><option value="">No folder</option>{folders.map((folder) => <option key={folder.id} value={folder.id}>{folder.name}</option>)}</select></label><div className={styles.modeOptions}><button type="button" disabled={uploading || externalProcessingAllowed !== true} onClick={() => void submitUpload("summary", uploadFolderId || null)}><strong>Summary</strong><span>A concise study note with the key ideas.</span></button><button type="button" disabled={uploading} onClick={() => void submitUpload("full_text", uploadFolderId || null)}><strong>Full text</strong><span>Keep the extracted material word for word.</span></button></div>{externalProcessingAllowed === false && <p className={styles.consentHint}>Summaries use Pixie’s configured AI provider. Enable study material processing in <Link href="/app/settings">Settings</Link> to use this option.</p>}{externalProcessingAllowed === null && <p className={styles.consentHint}>Checking summary availability…</p>}{uploading && <p className={styles.uploading}>Uploading and preparing your note…</p>}<p className={styles.sourceHint}>Your original file stays available in Source files. Removing it later will not change the saved note.</p></section></div>}
  </main>;
}
