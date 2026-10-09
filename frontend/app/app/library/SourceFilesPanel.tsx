"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Download, Eye, FileText, RotateCcw, Trash2, Upload } from "lucide-react";
import Dialog from "@/components/Dialog";
import { deleteFile, downloadFileUrl, moveFiles, retryFileProcessing, type FileDoc, type NoteFolderDoc } from "@/lib/api";
import FileViewer from "./FileViewer";
import { saveBlobUrl } from "@/lib/fileDownload";
import styles from "./source-files.module.css";

function fileStatus(file: FileDoc) {
  if (file.status === "failed") return "Needs attention";
  if (file.status === "pending_consent") return "Permission needed";
  if (file.status === "pending" || file.status === "processing") return "Processing";
  if (file.needs_ocr) return "Scan queued";
  return file.processed_note_id ? "Note created" : "Uploaded";
}

export default function SourceFilesPanel({ files, folders, onChanged, onUpload }: {
  files: FileDoc[];
  folders: NoteFolderDoc[];
  onChanged: () => Promise<void>;
  onUpload: () => void;
}) {
  const [viewing, setViewing] = useState<FileDoc | null>(null);
  const [deleting, setDeleting] = useState<FileDoc | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const openedFromLink = useRef(false);
  const previewOpener = useRef<HTMLButtonElement | null>(null);
  const previewButtons = useRef(new Map<string, HTMLButtonElement>());
  const addMaterialButton = useRef<HTMLButtonElement | null>(null);

  const closePreview = useCallback(() => {
    setViewing(null);
    const opener = previewOpener.current;
    const target = opener?.isConnected ? opener : addMaterialButton.current;
    target?.focus({ preventScroll: true });
    previewOpener.current = null;
  }, []);

  useEffect(() => {
    if (openedFromLink.current) return;
    const fileId = new URLSearchParams(window.location.search).get("fileId");
    const file = files.find((candidate) => candidate.id === fileId);
    if (file) {
      const timer = window.setTimeout(() => {
        openedFromLink.current = true;
        previewOpener.current = previewButtons.current.get(file.id) ?? null;
        setViewing(file);
      }, 0);
      return () => window.clearTimeout(timer);
    }
  }, [files]);

  async function act(file: FileDoc, action: () => Promise<unknown>) {
    setBusyId(file.id);
    setError("");
    try {
      await action();
      await onChanged();
      return true;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "That file could not be updated.");
      return false;
    } finally {
      setBusyId(null);
    }
  }

  async function download(file: FileDoc) {
    setError("");
    try {
      const url = await downloadFileUrl(file.id);
      saveBlobUrl(url, file.original_name);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The file could not be downloaded.");
    }
  }

  return <>
    <div className={styles.toolbar}><span>{files.length} {files.length === 1 ? "source file" : "source files"}</span><button ref={addMaterialButton} type="button" onClick={onUpload}><Upload size={16} />Add material</button></div>
    {error && <p className={styles.error} role="alert">{error}</p>}
    {files.length ? <ul className={styles.list}>{files.map((file) => <li key={file.id} className={styles.row}>
      <span className={styles.icon}><FileText size={18} aria-hidden="true" /></span>
      <div className={styles.details}><strong title={file.title?.trim() || file.original_name}>{file.title?.trim() || file.original_name}</strong><span>{fileStatus(file)} · {file.original_name}</span></div>
      <select aria-label={`Move ${file.title?.trim() || file.original_name} to folder`} value={file.folder_id ?? ""} disabled={busyId === file.id} onChange={(event) => void act(file, () => moveFiles([file.id], event.target.value || null))}><option value="">Unfiled</option>{folders.map((folder) => <option key={folder.id} value={folder.id}>{folder.name}</option>)}</select>
      <div className={styles.actions}>
        <button ref={(button) => { if (button) previewButtons.current.set(file.id, button); else previewButtons.current.delete(file.id); }} type="button" aria-label={`Preview ${file.original_name}`} title="Preview" onClick={(event) => { previewOpener.current = event.currentTarget; setViewing(file); }}><Eye size={17} /></button>
        <button type="button" aria-label={`Download ${file.original_name}`} title="Download" onClick={() => void download(file)}><Download size={17} /></button>
        {(file.status === "failed" || file.status === "pending_consent") && <button type="button" aria-label={`Retry ${file.original_name}`} title="Retry" disabled={busyId === file.id} onClick={() => void act(file, () => retryFileProcessing(file.id))}><RotateCcw size={17} /></button>}
        <button type="button" aria-label={`Delete ${file.original_name}`} title="Delete" disabled={busyId === file.id} onClick={() => setDeleting(file)}><Trash2 size={17} /></button>
      </div>
    </li>)}</ul> : <p className={styles.empty}>No source files yet. Add material when you need it.</p>}
    {viewing && <FileViewer key={viewing.id} doc={viewing} onClose={closePreview} />}
    {deleting && <Dialog open role="alertdialog" title={`Delete ${deleting.original_name}?`} message="This removes the original file. Any note saved from it will stay in your Library." confirmLabel="Delete file" cancelLabel="Cancel" destructive onConfirm={() => void act(deleting, () => deleteFile(deleting.id)).then((done) => { if (done) setDeleting(null); })} onCancel={() => setDeleting(null)} />}
  </>;
}
