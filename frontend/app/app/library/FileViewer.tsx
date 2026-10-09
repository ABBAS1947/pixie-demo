"use client";

import { useEffect, useId, useRef, useState } from "react";
import { X, Download, Loader2 } from "lucide-react";
import { downloadFileBlob, downloadFileUrl, downloadFileText } from "@/lib/api";
import type { FileDoc } from "@/lib/api";
import { saveBlobUrl } from "@/lib/fileDownload";
import styles from "./file-viewer.module.css";
import PdfPreview from "./PdfPreview";

function isPdf(doc: FileDoc) {
  return doc.file_type === "pdf";
}

function isImage(doc: FileDoc) {
  return ["jpg", "jpeg", "png", "gif", "webp", "bmp"].includes(doc.file_type);
}

function isText(doc: FileDoc) {
  return doc.file_type === "txt" || doc.file_type === "text";
}

export default function FileViewer({
  doc,
  onClose,
}: {
  doc: FileDoc;
  onClose: () => void;
}) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [pdfBlob, setPdfBlob] = useState<Blob | null>(null);
  const [textContent, setTextContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const dialogRef = useRef<HTMLDialogElement | null>(null);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);
  const downloadInFlight = useRef(false);
  const mounted = useRef(false);
  const titleId = useId();

  // All preview content lives in this native modal; no manual Tab trap.
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    mounted.current = true;
    const root = document.documentElement;
    const previousOverflow = root.style.overflow;
    let notified = false;
    function closed() {
      // Strict Mode can queue a close event before immediately reopening.
      if (dialog!.open || notified) return;
      notified = true;
      root.style.overflow = previousOverflow;
      onClose();
    }
    dialog.addEventListener("close", closed);
    if (!dialog.open) dialog.showModal();
    root.style.overflow = "hidden";
    closeButtonRef.current?.focus({ preventScroll: true });
    return () => {
      mounted.current = false;
      dialog.removeEventListener("close", closed);
      if (dialog.open) dialog.close();
      root.style.overflow = previousOverflow;
    };
  }, [onClose]);

  // ── Load file on mount ───────────────────────────────────────────────
  useEffect(() => {
    let revoked = false;
    let loadedUrl: string | null = null;
    const controller = new AbortController();

    async function load() {
      setLoading(true);
      setError(null);
      setDownloadError(null);
      try {
        if (isPdf(doc)) {
          const blob = await downloadFileBlob(doc.id, controller.signal);
          if (!revoked) setPdfBlob(blob);
        } else if (isImage(doc)) {
          const url = await downloadFileUrl(doc.id, controller.signal);
          if (!revoked) {
            loadedUrl = url;
            setBlobUrl(url);
          } else {
            URL.revokeObjectURL(url);
          }
        } else if (isText(doc)) {
          const text = await downloadFileText(doc.id, controller.signal);
          if (!revoked) setTextContent(text);
        } else {
          // Unsupported type — show a message
          setError(`Cannot preview "${doc.file_type}" files. Use download instead.`);
        }
      } catch (e: unknown) {
        if (!revoked) {
          setError(e instanceof Error ? e.message : "Failed to load file");
        }
      } finally {
        if (!revoked) setLoading(false);
      }
    }

    load();
    return () => {
      revoked = true;
      controller.abort();
      if (loadedUrl) URL.revokeObjectURL(loadedUrl);
    };
  }, [doc]);

  // ── Download handler ─────────────────────────────────────────────────
  async function handleDownload() {
    if (downloadInFlight.current) return;
    downloadInFlight.current = true;
    setDownloading(true);
    setDownloadError(null);
    try {
      const url = await downloadFileUrl(doc.id);
      saveBlobUrl(url, doc.original_name);
    } catch (cause) {
      if (mounted.current) setDownloadError(cause instanceof Error ? cause.message : "The file could not be downloaded.");
    } finally {
      downloadInFlight.current = false;
      if (mounted.current) setDownloading(false);
    }
  }

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby={titleId}
      onCancel={(event) => { event.preventDefault(); dialogRef.current?.close(); }}
      className={styles.dialog}
      style={{ backgroundColor: "var(--paper)", color: "var(--ink)" }}
    >
      {/* Top bar */}
      <div
        className="flex shrink-0 items-center justify-between border-b px-4 py-3"
        style={{ borderColor: "var(--paper-line)" }}
      >
        <p id={titleId} className="truncate pr-4 font-onb-ui text-sm font-medium text-ink" title={doc.original_name}>
          {doc.original_name}
        </p>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={handleDownload}
            className={`${styles.control} rounded p-1.5 text-ink-soft transition-colors hover:text-accent motion-reduce:transition-none`}
            title="Download"
            aria-label="Download file"
            disabled={downloading}
            aria-busy={downloading}
          >
            <Download size={16} aria-hidden="true" />
          </button>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={() => dialogRef.current?.close()}
            className={`${styles.control} rounded p-1.5 text-ink-soft transition-colors hover:text-ink motion-reduce:transition-none`}
            title="Close"
            aria-label="Close preview"
          >
            <X size={16} aria-hidden="true" />
          </button>
        </div>
      </div>

      {/* Content area */}
      <div className="min-h-0 flex-1 overflow-auto p-4">
        <p role="status" className="sr-only">{loading ? "Loading preview…" : error || isPdf(doc) ? "" : "Preview ready."}{downloading ? " Downloading file…" : ""}</p>
        {downloadError && <p role="alert" className="mb-3 font-onb-ui text-sm text-danger">{downloadError}</p>}
        {loading ? (
          <div className="flex flex-col items-center gap-2 pt-20 text-ink-soft">
            <Loader2 size={24} aria-hidden="true" className="animate-spin motion-reduce:animate-none" />
            <p className="font-onb-ui text-sm">Loading…</p>
          </div>
        ) : error ? (
          <div className="flex flex-col items-center gap-2 pt-20 text-center">
            <p role="alert" className="font-onb-ui text-sm text-danger">{error}</p>
            <button
              type="button"
              onClick={handleDownload}
              disabled={downloading}
              className={`${styles.control} mt-2 rounded-md border px-3 py-1.5 font-onb-ui text-xs text-ink-soft transition-colors hover:border-accent hover:text-accent motion-reduce:transition-none`}
              style={{ borderColor: "var(--paper-line)" }}
            >
              Try downloading instead
            </button>
          </div>
        ) : pdfBlob && isPdf(doc) ? (
          <PdfPreview blob={pdfBlob} />
        ) : blobUrl && isImage(doc) ? (
          <div className="flex h-full items-center justify-center">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={blobUrl}
              alt={doc.original_name}
              className="max-h-full max-w-full rounded object-contain"
            />
          </div>
        ) : textContent !== null ? (
          <pre tabIndex={0} aria-label="File text" className={`${styles.text} overflow-x-auto whitespace-pre-wrap break-words rounded border p-4 font-mono text-sm leading-relaxed`} style={{ borderColor: "var(--paper-line)", backgroundColor: "var(--paper)" }}>
            <code>{textContent}</code>
          </pre>
        ) : null}
      </div>
    </dialog>
  );
}
