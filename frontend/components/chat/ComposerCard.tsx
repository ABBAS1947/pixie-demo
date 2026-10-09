"use client";

import { motion } from "framer-motion";
import { ArrowUp, Plus } from "lucide-react";
import { useRef, useState } from "react";
import ContextPopup, { type ContextChip } from "@/components/chat/ContextPopup";

export type ComposerMode = "chat" | "learn";

interface ComposerCardProps {
  onSend: (text: string, mode: ComposerMode, chips: ContextChip[]) => void;
  value?: string;
  onValueChange?: (value: string) => void;
  mode?: ComposerMode;
  onModeChange?: (mode: ComposerMode) => void;
  compact?: boolean;
  disabled?: boolean;
}

export default function ComposerCard({
  onSend,
  value: controlledValue,
  onValueChange,
  mode: controlledMode,
  onModeChange,
  compact = false,
  disabled = false,
}: ComposerCardProps) {
  const [localValue, setLocalValue] = useState("");
  const [localMode, setLocalMode] = useState<ComposerMode>("chat");
  const [chips, setChips] = useState<ContextChip[]>([]);
  const [popup, setPopup] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const value = controlledValue ?? localValue;
  const mode = controlledMode ?? localMode;

  function setValue(next: string) {
    setLocalValue(next);
    onValueChange?.(next);
    requestAnimationFrame(() => {
      const textarea = textareaRef.current;
      if (!textarea) return;
      const maximumHeight = compact ? 112 : 140;
      textarea.style.height = "auto";
      textarea.style.height = `${Math.min(textarea.scrollHeight, maximumHeight)}px`;
      textarea.style.overflowY = textarea.scrollHeight > maximumHeight ? "auto" : "hidden";
    });
  }

  function setMode(next: ComposerMode) {
    setLocalMode(next);
    onModeChange?.(next);
  }

  function submit() {
    const text = value.trim();
    if (!text || disabled) return;
    const context = chips.map((chip) => `[${chip.kind}: ${chip.title}]`).join(" ");
    onSend(context ? `${context} ${text}` : text, mode, chips);
    setValue("");
    setChips([]);
  }

  function toggleChip(chip: ContextChip) {
    setChips((previous) =>
      previous.some((item) => item.kind === chip.kind && item.id === chip.id)
        ? previous.filter((item) => !(item.kind === chip.kind && item.id === chip.id))
        : [...previous, chip]
    );
  }

  const iconButtonClass = "flex shrink-0 items-center justify-center rounded-full transition-colors focus-visible:outline-2 focus-visible:outline-offset-2";
  const modeSelector = <div role="group" aria-label="Conversation mode" className="flex w-fit shrink-0 items-center rounded-xl border border-white/20 p-0.5">
    {(["chat", "learn"] as ComposerMode[]).map((item) => <button key={item} type="button" onClick={() => setMode(item)} aria-pressed={mode === item} disabled={disabled}
      className={`min-h-9 min-w-[60px] rounded-lg px-3 text-[13px] font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-50 ${mode === item ? "bg-[var(--color-cream)] text-[var(--color-dark)]" : "text-[var(--color-cream)] hover:bg-white/10"}`}>
      {item === "chat" ? "Chat" : "Learn"}
    </button>)}
  </div>;

  return (
    <motion.div
      layout
      transition={{ layout: { type: "spring", stiffness: 300, damping: 32 } }}
      className="w-full"
      style={{
        backgroundColor: "var(--color-dark)",
        borderRadius: compact ? 24 : 23,
        border: compact ? "1px solid rgba(254, 235, 204, 0.34)" : "1px solid transparent",
        boxShadow: compact
          ? "0 10px 28px rgba(66, 25, 1, 0.16)"
          : "0 20px 25px -5px rgba(0, 0, 0, 0.2), 0 10px 10px -5px rgba(0, 0, 0, 0.1)",
        padding: compact ? "6px 10px" : "12px 16px",
      }}
    >
      {chips.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-1.5 px-1">
          {chips.map((chip) => (
            <span key={`${chip.kind}-${chip.id}`} className="flex items-center gap-1 rounded-full bg-[var(--color-cream)] py-1 pl-2.5 pr-1.5 font-body text-[10px] font-bold text-[var(--color-dark)]">
              {chip.title.length > 24 ? `${chip.title.slice(0, 24)}…` : chip.title}
              <button type="button" onClick={() => toggleChip(chip)} aria-label={`Remove ${chip.title}`} className="px-1 text-xs opacity-60">×</button>
            </span>
          ))}
        </div>
      )}

      <>
        {compact ? (
          <div className="flex min-h-10 items-end gap-2">
            <div className="relative">
              <button type="button" onClick={() => setPopup((open) => !open)} aria-label="Add context" className={`${iconButtonClass} h-10 w-10 text-[var(--color-cream)] hover:bg-white/12 hover:text-white active:bg-white/18`}>
                <Plus size={20} strokeWidth={2} />
              </button>
              {popup && <ContextPopup chips={chips} onToggle={toggleChip} onClose={() => setPopup(false)} align="left" />}
            </div>
            <textarea
              ref={textareaRef}
              value={value}
              onChange={(event) => setValue(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  submit();
                }
              }}
              placeholder="Write a message…"
              aria-label="Write a message"
              rows={1}
              disabled={disabled}
              className="min-h-10 flex-1 resize-none bg-transparent px-1 py-2.5 font-body leading-5 text-[var(--color-white)] outline-none placeholder:text-[var(--color-cream)]/55"
              style={{ fontSize: 16, lineHeight: 1.35 }}
            />
            <button type="button" onClick={submit} disabled={disabled || !value.trim()} aria-label="Send message" className={`${iconButtonClass} h-10 w-10 bg-[var(--color-orange)] text-white hover:bg-[#d95500] active:bg-[var(--color-cream)] active:text-[var(--color-dark)] disabled:opacity-35`}>
              <ArrowUp size={19} strokeWidth={2.4} />
            </button>
          </div>
        ) : (
          <div>
            <textarea
              ref={textareaRef}
              value={value}
              onChange={(event) => setValue(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  submit();
                }
              }}
              placeholder={mode === "chat" ? "How can I help you today?" : "What would you like to learn?"}
              aria-label={mode === "chat" ? "Message Pixie" : "Choose a learning topic"}
              rows={1}
              disabled={disabled}
              className="min-h-[42px] w-full resize-none bg-transparent px-2 py-2 font-body font-semibold leading-5 text-[var(--color-white)] outline-none placeholder:text-[var(--color-cream)]/55"
              style={{ fontSize: 16, lineHeight: 1.4 }}
            />
            <div className="mt-2 flex items-center justify-between gap-2">
              <div className="flex min-w-0 items-center gap-2">
                <div className="relative">
                  <button type="button" onClick={() => setPopup((open) => !open)} aria-label="Add context" className={`${iconButtonClass} h-9 w-9 border border-[var(--color-orange)] text-[var(--color-orange)] hover:bg-[var(--color-orange)] hover:text-white active:bg-[var(--color-dark)]`}>
                    <Plus size={17} />
                  </button>
                  {popup && <ContextPopup chips={chips} onToggle={toggleChip} onClose={() => setPopup(false)} align="left" />}
                </div>
                {modeSelector}
              </div>
              <button type="button" onClick={submit} disabled={disabled || !value.trim()} aria-label="Send message" className={`${iconButtonClass} h-9 w-9 bg-[var(--color-orange)] text-white hover:bg-[#d95500] active:bg-[var(--color-dark)] disabled:opacity-35`}>
                <ArrowUp size={18} strokeWidth={2.4} />
              </button>
            </div>
          </div>
        )}
      </>
    </motion.div>
  );
}
