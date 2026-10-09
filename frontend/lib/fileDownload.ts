/** Start a browser download and keep its blob alive until navigation consumes it. */
export function saveBlobUrl(url: string, filename: string): void {
  const link = document.createElement("a");
  try {
    link.href = url;
    link.download = filename;
    link.rel = "noopener";
    document.body.appendChild(link);
    link.click();
  } finally {
    link.remove();
    // Immediate revocation races the browser's asynchronous download handling.
    // This is an in-memory object, not an application or service-worker cache.
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
  }
}
