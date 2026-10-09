"use client";

import { useState } from "react";
import { MessageCircle, X, Bug, Lightbulb, MessageSquare } from "lucide-react";
import { apiFetch } from "@/lib/apiRequest";

const API_URL = typeof window !== "undefined" ? window.location.origin : process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:9000";

type FeedbackType = "bug" | "feedback" | "feature";

const TYPES: { value: FeedbackType; label: string; icon: React.ReactNode }[] = [
  { value: "bug", label: "Bug", icon: <Bug size={16} /> },
  { value: "feedback", label: "Feedback", icon: <MessageSquare size={16} /> },
  { value: "feature", label: "Feature", icon: <Lightbulb size={16} /> },
];

interface FeedbackButtonProps {
  /** Controlled open state — if provided, the component is controlled */
  open?: boolean;
  /** Called when the open state should change */
  onOpenChange?: (open: boolean) => void;
}

export default function FeedbackButton({ open: controlledOpen, onOpenChange }: FeedbackButtonProps = {}) {
  const [internalOpen, setInternalOpen] = useState(false);
  const open = controlledOpen ?? internalOpen;
  const setOpen = onOpenChange ?? setInternalOpen;

  const [type, setType] = useState<FeedbackType>("feedback");
  const [message, setMessage] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);

  async function handleSubmit() {
    if (!message.trim()) return;
    setBusy(true);
    try {
      const res = await apiFetch(`${API_URL}/feedback`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          feedback_type: type,
          message: message.trim(),
          page: window.location.pathname,
        }),
      });
      if (res.ok) {
        setSent(true);
        setTimeout(() => {
          setOpen(false);
          setSent(false);
          setMessage("");
        }, 1500);
      }
    } catch (e) {
      console.error("Feedback failed", e);
    } finally {
      setBusy(false);
    }
  }

  function close() {
    setOpen(false);
    setSent(false);
    setMessage("");
  }

  return (
    <>
      {/* Floating button — only shown in uncontrolled mode */}
      {controlledOpen === undefined && (
        <button
          onClick={() => setOpen(true)}
          style={{
            position: 'fixed',
            bottom: '24px',
            right: '24px',
            zIndex: 9999,
            width: '48px',
            height: '48px',
            borderRadius: '50%',
            backgroundColor: '#3b6e5e',
            color: 'white',
            border: 'none',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
          }}
          aria-label="Send feedback"
        >
          <MessageCircle size={20} />
        </button>
      )}

      {/* Modal overlay */}
      {open && (
        <div className="fixed inset-0 z-50 flex items-end justify-center p-4 sm:items-center">
          <div
            className="fixed inset-0 bg-black/30 backdrop-blur-sm"
            onClick={close}
          />
          <div className="relative w-full max-w-md rounded-2xl bg-surface p-6 shadow-xl">
            {/* Close button */}
            <button
              onClick={close}
              className="absolute right-4 top-4 text-meta hover:text-fg"
            >
              <X size={18} />
            </button>

            {sent ? (
              <div className="flex flex-col items-center gap-3 py-8">
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-accent/10 text-accent">
                  <MessageCircle size={24} />
                </div>
                <p className="text-lg font-medium text-fg">Thanks!</p>
                <p className="text-sm text-meta">Your feedback helps us improve Pixie.</p>
              </div>
            ) : (
              <>
                <h3 className="text-lg font-medium text-fg">Send feedback</h3>
                <p className="mt-1 text-sm text-meta">Help us make Pixie better.</p>

                {/* Type selector */}
                <div className="mt-4 flex gap-2">
                  {TYPES.map((t) => (
                    <button
                      key={t.value}
                      onClick={() => setType(t.value)}
                      className={`flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                        type === t.value
                          ? "bg-accent text-white"
                          : "bg-bg text-meta hover:bg-surface-warm"
                      }`}
                    >
                      {t.icon}
                      {t.label}
                    </button>
                  ))}
                </div>

                {/* Message */}
                <textarea
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  placeholder={
                    type === "bug"
                      ? "What happened? What did you expect?"
                      : type === "feature"
                      ? "What would you like Pixie to do?"
                      : "What's on your mind?"
                  }
                  rows={4}
                  className="mt-4 w-full rounded-lg border border-paper-line bg-bg px-3 py-2 text-sm text-fg outline-none transition-colors placeholder:text-meta/50 focus:border-accent"
                />

                {/* Submit */}
                <button
                  onClick={handleSubmit}
                  disabled={!message.trim() || busy}
                  className={`mt-4 w-full rounded-lg py-2.5 text-sm font-medium transition-colors ${
                    message.trim()
                      ? "bg-accent text-white hover:bg-accent-active"
                      : "bg-paper-dim text-meta cursor-not-allowed"
                  }`}
                >
                  {busy ? "Sending…" : "Send"}
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}
