"use client";

import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import styles from "../onboarding.module.css";

interface Props {
  options: string[];
  selected: string[];
  onToggle: (v: string) => void;
  customValue: string;
  onCustomChange: (text: string) => void;
}

export default function ChipGrid({ options, selected, onToggle, customValue, onCustomChange }: Props) {
  const [otherOpen, setOtherOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (otherOpen) inputRef.current?.focus();
  }, [otherOpen]);

  function saveOther() {
    if (!draft.trim()) return;
    onCustomChange(draft.trim());
    setOtherOpen(false);
    setDraft("");
  }

  return (
    <div className={styles.chipGrid}>
      {options.filter((option) => option !== "Other").map((option) => {
        const active = selected.includes(option);
        return (
          <button key={option} type="button" onClick={() => onToggle(option)}
            className={`${styles.chip} ${active ? styles.selected : ""}`} aria-pressed={active}>
            {option}
          </button>
        );
      })}
      {options.includes("Other") && (customValue ? (
        <div className={`${styles.chip} ${styles.selected} ${styles.customChip}`} key="Other">
          <span>{customValue}</span>
          <button type="button" onClick={() => onCustomChange("")}
            aria-label={`Remove ${customValue}`} className={styles.removeChip}>
            <X size={17} aria-hidden="true" />
          </button>
        </div>
      ) : (
        <button key="Other" type="button" onClick={() => setOtherOpen(true)} className={styles.chip}>Other</button>
      ))}
      {otherOpen && !customValue && (
        <form className={styles.otherForm} onSubmit={(event) => { event.preventDefault(); saveOther(); }}>
          <input ref={inputRef} value={draft} onChange={(event) => setDraft(event.target.value)}
            placeholder="Add a subject" aria-label="Other subject" className={styles.textInput} />
          <button type="submit" className={styles.smallButton} disabled={!draft.trim()}>Add</button>
        </form>
      )}
    </div>
  );
}
