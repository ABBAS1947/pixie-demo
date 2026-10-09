"use client";

import { useCallback, useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

const FOCUSABLE = 'button:not([disabled]), [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

type DialogProps = {
  open: boolean;
  role?: "dialog" | "alertdialog";
  title: string;
  message?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel?: () => void;
  destructive?: boolean;
  icon?: ReactNode | null;
  dismissOnScrimClick?: boolean;
};

function WarningGlyph() {
  return <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 3.6 2.9 19.2a1.2 1.2 0 0 0 1 1.8h16.2a1.2 1.2 0 0 0 1-1.8L12 3.6Z" stroke="white" strokeWidth="2" strokeLinejoin="round"/><path d="M12 9.6v4.2" stroke="white" strokeWidth="2" strokeLinecap="round"/><circle cx="12" cy="17.1" r="1.15" fill="white"/></svg>;
}

/** Shared modal with explicit semantics for informational and response dialogs. */
export default function Dialog({ open, role = "dialog", title, message, confirmLabel = "OK", cancelLabel, onConfirm, onCancel, destructive = false, icon, dismissOnScrimClick = true }: DialogProps) {
  const [mounted, setMounted] = useState(open);
  const [visible, setVisible] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);
  const titleId = useId();
  const messageId = useId();
  const reduceMotion = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

  useEffect(() => {
    if (open) {
      restoreFocusRef.current = document.activeElement as HTMLElement | null;
      setMounted(true);
      const frame = requestAnimationFrame(() => setVisible(true));
      return () => cancelAnimationFrame(frame);
    }
    setVisible(false);
    const timer = window.setTimeout(() => setMounted(false), reduceMotion ? 0 : 140);
    return () => window.clearTimeout(timer);
  }, [open, reduceMotion]);

  useEffect(() => {
    if (!mounted) return;
    const root = document.documentElement;
    const previous = root.style.overflow;
    root.style.overflow = "hidden";
    return () => { root.style.overflow = previous; };
  }, [mounted]);

  useEffect(() => {
    if (!visible) return;
    (destructive && cancelRef.current ? cancelRef.current : confirmRef.current)?.focus();
  }, [visible, destructive]);

  useEffect(() => {
    if (mounted) return;
    restoreFocusRef.current?.focus?.();
  }, [mounted]);

  const handleKeyDown = useCallback((event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.stopPropagation();
      (onCancel ?? onConfirm)();
      return;
    }
    if (event.key !== "Tab" || !cardRef.current) return;
    const nodes = Array.from(cardRef.current.querySelectorAll<HTMLElement>(FOCUSABLE));
    if (!nodes.length) return;
    const first = nodes[0]; const last = nodes[nodes.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }, [onCancel, onConfirm]);

  if (!mounted) return null;
  return <div className="pixie-dialog-root" onKeyDown={handleKeyDown}>
    <div className="pixie-dialog-scrim" aria-hidden="true" onClick={dismissOnScrimClick ? () => (onCancel ?? onConfirm)() : undefined} style={{ opacity: visible ? 1 : 0, transition: reduceMotion ? "none" : `opacity ${visible ? 0.2 : 0.14}s ease` }} />
    <div ref={cardRef} role={role} aria-modal="true" aria-labelledby={titleId} aria-describedby={message ? messageId : undefined} className="pixie-dialog-card" style={{ opacity: visible ? 1 : 0, transform: visible ? "scale(1) translateY(0)" : "scale(.97) translateY(6px)", transition: reduceMotion ? "none" : `opacity ${visible ? 0.2 : 0.14}s ease, transform ${visible ? 0.2 : 0.14}s ease` }}>
      {icon !== null && <div className="pixie-dialog-icon" style={{ background: destructive ? "var(--color-orange)" : "var(--color-dark)" }}>{icon ?? <WarningGlyph />}</div>}
      <h2 id={titleId}>{title}</h2>
      {message && <div id={messageId} className="pixie-dialog-message">{message}</div>}
      <div className="pixie-dialog-actions">
        {cancelLabel && <button ref={cancelRef} type="button" className="pixie-dialog-cancel" onClick={onCancel}>{cancelLabel}</button>}
        <button ref={confirmRef} type="button" className={`pixie-dialog-confirm ${destructive ? "is-destructive" : ""}`} onClick={onConfirm}>{confirmLabel}</button>
      </div>
    </div>
  </div>;
}
