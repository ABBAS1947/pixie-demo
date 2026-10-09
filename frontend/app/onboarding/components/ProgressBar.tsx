"use client";

import styles from "../onboarding.module.css";

interface Props {
  total: number;
  current: number;
}

export default function ProgressBar({ total, current }: Props) {
  return (
    <div className={styles.progress} role="progressbar" aria-label="Onboarding progress"
      aria-valuemin={0} aria-valuemax={total} aria-valuenow={Math.min(current + 1, total)}>
      {Array.from({ length: total }, (_, index) => (
        <span key={index} className={index <= current ? styles.progressFilled : ""} />
      ))}
    </div>
  );
}
