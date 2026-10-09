"use client";

import { useEffect, useState } from "react";

const STATUS_WORDS = ["Preparing your response"];

export default function ThinkingIndicator() {
  const [wordIndex, setWordIndex] = useState(0);
  const [dotCount, setDotCount] = useState(1);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setWordIndex((index) => (index + 1) % STATUS_WORDS.length);
    }, 2800);
    const dotsTimer = window.setInterval(() => {
      setDotCount((count) => count === 3 ? 1 : count + 1);
    }, 420);
    return () => {
      window.clearInterval(timer);
      window.clearInterval(dotsTimer);
    };
  }, []);

  return (
    <div className="flex flex-col items-start gap-2 pl-1" aria-live="polite" aria-label={STATUS_WORDS[wordIndex]}>
      <span className="thinking-shimmer font-body" style={{ fontSize: 15, fontWeight: 650, letterSpacing: "-0.01em" }}>
        {STATUS_WORDS[wordIndex]}{".".repeat(dotCount)}
      </span>
      <img
        src="/icons/PixieLogo(Silhouette)-06.svg"
        alt=""
        width={23}
        height={23}
        className="opacity-85"
      />
    </div>
  );
}
