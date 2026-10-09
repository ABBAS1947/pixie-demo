"use client";

import type { Answers } from "@/lib/onboarding";
import Image from "next/image";
import styles from "../onboarding.module.css";

interface Props {
  answers: Answers;
  onContinue: () => void;
  busy: boolean;
  error: string | null;
}

export default function WelcomeScreen({ answers, onContinue, busy, error }: Props) {
  const name = answers.name.trim();

  return (
    <div className={styles.welcome}>
      <div className={styles.welcomeMascot}>
        <span className={styles.welcomeHalo} aria-hidden="true" />
        <Image src="/icons/fox-logo.svg" alt="" width={270} height={276} priority />
      </div>
      <div className={styles.welcomeCopy}>
        <h1 className={styles.title}>{name ? `You're all set, ${name}!` : "You're all set!"}</h1>
      </div>
      {error && <p className={styles.error} role="alert">{error}</p>}
      <button type="button" onClick={onContinue} disabled={busy} className={styles.primary}>
        {busy ? "Saving…" : "Open dashboard"}
      </button>
    </div>
  );
}
