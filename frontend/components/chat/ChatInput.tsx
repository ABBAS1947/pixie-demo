"use client";

import { useState } from "react";

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
}

/**
 * Chat input bar — Figma dims: 806x115, radius 50, 45px bottom inset.
 * Send button 60x60, arrow glyph slot 23.5x12.8.
 */
export default function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [value, setValue] = useState("");

  function submit() {
    const msg = value.trim();
    if (!msg || disabled) return;
    setValue("");
    onSend(msg);
  }

  return (
    <div
      className="flex items-center w-full"
      style={{
        width: 467,
        maxWidth: "100%",
        height: 67,
        backgroundColor: "var(--color-dark)",
        borderRadius: 29,
        padding: "0 16px 0 21px",
        gap: 9,
      }}
    >
      <input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
        placeholder="Ask Pixie anything…"
        disabled={disabled}
        className="flex-1 bg-transparent outline-none font-body"
        style={{ fontSize: 10, fontWeight: 500, color: "var(--color-white)" }}
      />
      <button
        onClick={submit}
        disabled={disabled || !value.trim()}
        aria-label="Send message"
        className="flex items-center justify-center disabled:opacity-40"
        style={{
          width: 35,
          height: 35,
          borderRadius: "50%",
          backgroundColor: "var(--color-orange)",
          color: "var(--color-white)",
          flexShrink: 0,
        }}
      >
        <img
          src="/icons/send-arrow.svg"
          alt="Send"
          width={14}
          height={7}
          style={{ transform: "rotate(-90deg)", flexShrink: 0 }}
        />
      </button>
    </div>
  );
}
