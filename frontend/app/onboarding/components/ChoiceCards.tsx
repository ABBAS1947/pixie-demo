"use client";

import { useEffect, useRef, useState } from "react";
import { Check } from "lucide-react";
import styles from "../onboarding.module.css";

interface Props {
  options: string[];
  value: string | null;
  onPick: (v: string) => void;
  onOtherSubmit?: (text: string) => void;
  otherError?: string | null;
  onOtherDismiss?: () => void;
}

export default function ChoiceCards({ options, value, onPick, onOtherSubmit, otherError, onOtherDismiss }: Props) {
  const [otherOpen, setOtherOpen] = useState(false);
  const [otherText, setOtherText] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (otherOpen) inputRef.current?.focus();
  }, [otherOpen]);

  function select(option: string) {
    if (option === "Other") {
      setOtherOpen(true);
      onOtherDismiss?.();
      return;
    }
    setOtherOpen(false);
    setOtherText("");
    onOtherDismiss?.();
    onPick(option);
  }

  return (
    <div className={styles.choiceList}>
      {options.map((option) => {
        const selected = value === option || (option === "Other" && !!value && !options.includes(value));
        return (
          <button key={option} type="button" onClick={() => select(option)}
            className={`${styles.choice} ${selected ? styles.selected : ""}`} aria-pressed={selected}>
            <span>{option === "Other" && selected ? value : option}</span>
            {selected && <Check size={20} strokeWidth={2.5} aria-hidden="true" />}
          </button>
        );
      })}
      {otherOpen && (
        <form className={styles.otherForm} onSubmit={(event) => {
          event.preventDefault();
          if (otherText.trim()) onOtherSubmit?.(otherText.trim());
        }}>
          <input ref={inputRef} value={otherText} onChange={(event) => setOtherText(event.target.value)}
            placeholder="Your grade" aria-label="Your grade" aria-invalid={!!otherError}
            className={styles.textInput} />
          <button type="submit" className={styles.smallButton} disabled={!otherText.trim()}>Use this</button>
          {otherError && <p className={styles.error} role="alert">{otherError}</p>}
        </form>
      )}
    </div>
  );
}
