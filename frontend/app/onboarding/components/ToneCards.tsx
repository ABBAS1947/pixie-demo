"use client";

import { Check } from "lucide-react";
import { TONE_OPTIONS } from "../tone-options";
import styles from "../onboarding.module.css";

interface Props {
  value: string | null;
  onPick: (v: string) => void;
  toneIds?: string[];
}

export default function ToneCards({ value, onPick, toneIds }: Props) {
  const tones = toneIds ? TONE_OPTIONS.filter((tone) => toneIds.includes(tone.id)) : TONE_OPTIONS;
  return (
    <div className={styles.choiceList}>
      {tones.map((tone) => {
        const selected = value === tone.id;
        return (
          <button key={tone.id} type="button" onClick={() => onPick(tone.id)}
            className={`${styles.choice} ${styles.toneChoice} ${selected ? styles.selected : ""}`} aria-pressed={selected}>
            <span className={styles.toneCopy}><strong>{tone.label}</strong><span>{tone.preview}</span></span>
            {selected && <Check size={20} strokeWidth={2.5} aria-hidden="true" />}
          </button>
        );
      })}
    </div>
  );
}
