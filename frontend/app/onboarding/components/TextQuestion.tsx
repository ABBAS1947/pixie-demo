"use client";

import { useEffect, useRef } from "react";
import styles from "../onboarding.module.css";

interface Props {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  onContinue: () => void;
  autoFocus?: boolean;
}

export default function TextQuestion({ value, onChange, placeholder, onContinue, autoFocus }: Props) {
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (autoFocus) ref.current?.focus();
  }, [autoFocus]);

  return (
    <input ref={ref} value={value} onChange={(event) => onChange(event.target.value)}
      onKeyDown={(event) => { if (event.key === "Enter" && value.trim()) { event.preventDefault(); onContinue(); } }}
      placeholder={placeholder} aria-label="Your name" autoComplete="given-name" maxLength={80}
      className={styles.textInput} />
  );
}
