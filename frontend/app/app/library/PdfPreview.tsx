"use client";

import { useEffect, useRef, useState } from "react";
import type { PDFDocumentLoadingTask, PDFDocumentProxy, RenderTask, TextLayer } from "pdfjs-dist";
import styles from "./file-viewer.module.css";

// One active page, bounded raster memory. The original download stays intact.
const MAX_PIXELS = 4_000_000;
const MAX_DIMENSION = 8192;

export default function PdfPreview({ blob }: { blob: Blob }) {
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [pageInput, setPageInput] = useState("1");
  const [zoom, setZoom] = useState(1);
  const [width, setWidth] = useState(0);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hasText, setHasText] = useState(true);
  const [failureStage, setFailureStage] = useState<string | null>(null);
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const pageRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let disposed = false;
    let task: PDFDocumentLoadingTask | undefined;
    async function open() {
      let stage = "module";
      try {
        const library = await import("pdfjs-dist");
        if (disposed) return;
        const assets = `/pdfjs/${library.version}/`;
        library.GlobalWorkerOptions.workerSrc = `${assets}pdf.worker.min.mjs`;
        stage = "file-bytes";
        const data = new Uint8Array(await blob.arrayBuffer());
        if (disposed) return;
        stage = "worker-document";
        task = library.getDocument({ data, cMapUrl: `${assets}cmaps/`, cMapPacked: true,
          standardFontDataUrl: `${assets}standard_fonts/`, wasmUrl: `${assets}wasm/`,
          iccUrl: `${assets}iccs/`, enableXfa: false, canvasMaxAreaInBytes: MAX_PIXELS * 4 });
        task.onPassword = () => {
          if (!disposed) setError("This PDF requires a password. Download it to open it in your PDF app.");
          void task?.destroy().catch(() => {});
        };
        const document = await task.promise;
        if (!disposed) setPdf(document);
      } catch {
        if (!disposed) {
          setFailureStage(stage);
          setError(current => current ?? "This PDF could not be previewed. You can still download the original.");
        }
      }
    }
    void open();
    return () => { disposed = true; void task?.destroy().catch(() => {}); };
  }, [blob]);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const observer = new ResizeObserver(() => setWidth(Math.max(1, viewport.clientWidth - 24)));
    observer.observe(viewport);
    setWidth(Math.max(1, viewport.clientWidth - 24));
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!pdf || !width || !pageRef.current) return;
    let disposed = false;
    let renderTask: RenderTask | undefined;
    let layer: TextLayer | undefined;
    let page: Awaited<ReturnType<PDFDocumentProxy["getPage"]>> | undefined;
    const container = pageRef.current;
    // New nodes avoid sharing a canvas with a cancelled asynchronous render.
    const canvas = document.createElement("canvas");
    canvas.setAttribute("aria-hidden", "true");
    const text = document.createElement("div");
    text.className = "textLayer";
    container.replaceChildren(canvas, text);
    setBusy(true);
    setError(null);
    viewportRef.current?.scrollTo({ top: 0, left: 0 });
    async function render() {
      try {
        const library = await import("pdfjs-dist");
        page = await pdf!.getPage(pageNumber);
        if (disposed) { page.cleanup(); return; }
        const original = page.getViewport({ scale: 1 });
        const scale = Math.min(Math.min(width / original.width, 1.5) * zoom,
          MAX_DIMENSION / Math.max(original.width, original.height));
        const viewport = page.getViewport({ scale });
        const ratio = Math.min(window.devicePixelRatio || 1, 2,
          Math.sqrt(MAX_PIXELS / (viewport.width * viewport.height)),
          MAX_DIMENSION / Math.max(viewport.width, viewport.height));
        canvas.width = Math.max(1, Math.floor(viewport.width * ratio));
        canvas.height = Math.max(1, Math.floor(viewport.height * ratio));
        canvas.style.width = `${viewport.width}px`;
        canvas.style.height = `${viewport.height}px`;
        container.style.width = `${viewport.width}px`;
        container.style.height = `${viewport.height}px`;
        container.style.setProperty("--total-scale-factor", String(scale));
        renderTask = page.render({ canvas, viewport,
          transform: [ratio, 0, 0, ratio, 0, 0], annotationMode: library.AnnotationMode.ENABLE });
        await renderTask.promise;
        if (disposed) return;
        const content = await page.getTextContent();
        if (disposed) return;
        setHasText(content.items.some(item => "str" in item && item.str.trim().length > 0));
        layer = new library.TextLayer({ textContentSource: content, container: text, viewport });
        await layer.render();
      } catch {
        if (!disposed) setError("This page could not be previewed. Try another page or download the original.");
      } finally {
        if (!disposed) setBusy(false);
      }
    }
    void render();
    return () => {
      disposed = true;
      renderTask?.cancel();
      layer?.cancel();
      // Release raster allocation only after cancellation has settled.
      void (renderTask?.promise ?? Promise.resolve()).catch(() => {}).finally(() => {
        canvas.width = canvas.height = 0;
        page?.cleanup();
      });
    };
  }, [pdf, pageNumber, width, zoom]);

  function goToPage(value: number) {
    if (!pdf) return;
    const next = Math.min(pdf.numPages, Math.max(1, Math.trunc(value)));
    if (!Number.isFinite(next)) { setPageInput(String(pageNumber)); return; }
    setPageNumber(next);
    setPageInput(String(next));
  }

  return <div className={styles.pdf} data-preview-failure-stage={failureStage ?? undefined}>
    <div className={styles.toolbar} aria-label="PDF controls">
      <div className={styles.toolbarGroup} role="group" aria-label="Page navigation">
      <button type="button" className={styles.control} aria-label="Previous page" disabled={!pdf || pageNumber === 1} onClick={() => goToPage(pageNumber - 1)}>‹</button>
      <label className="flex items-center gap-2">Page
        <input className={styles.pageInput} aria-label="Page number" type="number" min={1} max={pdf?.numPages ?? 1} value={pageInput} disabled={!pdf}
          onChange={event => setPageInput(event.target.value)} onBlur={() => goToPage(Number(pageInput))}
          onKeyDown={event => { if (event.key === "Enter") goToPage(Number(pageInput)); }} />
        <span>of {pdf?.numPages ?? "…"}</span>
      </label>
      <button type="button" className={styles.control} aria-label="Next page" disabled={!pdf || pageNumber === pdf.numPages} onClick={() => goToPage(pageNumber + 1)}>›</button>
      </div>
      <div className={styles.toolbarGroup} role="group" aria-label="Zoom">
      <button type="button" className={styles.control} aria-label="Zoom out" disabled={zoom <= 0.5} onClick={() => setZoom(value => Math.max(0.5, value - 0.25))}>−</button>
      <span className="text-sm">{Math.round(zoom * 100)}%</span>
      <button type="button" className={styles.control} aria-label="Zoom in" disabled={zoom >= 2} onClick={() => setZoom(value => Math.min(2, value + 0.25))}>+</button>
      </div>
    </div>
    <p role="status" className="sr-only">{error ? "" : busy ? "Rendering PDF…" : `Page ${pageNumber} of ${pdf?.numPages} ready.`}</p>
    {error && <p role="alert" className="mb-2 text-sm">{error}</p>}
    {!busy && !error && !hasText && <p className="mb-2 text-sm">This page has no selectable text. The scanned page is shown below.</p>}
    <div ref={viewportRef} className={styles.viewport} role="region" aria-label="PDF page" tabIndex={0} aria-busy={busy && !error}>
      {busy && !error && <p className="text-center text-sm">Rendering PDF…</p>}
      <div ref={pageRef} className={styles.page} />
    </div>
  </div>;
}
