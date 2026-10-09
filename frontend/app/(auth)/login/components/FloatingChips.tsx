"use client";

import type { AuthMode } from "../page";

const CHIPS = ["Biology", "Focused", "Chapter 4"];
const ROTATIONS = ["-rotate-2", "rotate-1 translate-y-2", "-rotate-1"];

export default function FloatingChips({ mode }: { mode: AuthMode }) {
  const headline = mode === "login" ? "Welcome back." : "Let's get you set up.";
  return (
    <div style={{ width: "100%" }} className="lg:hidden">
      <div
        style={{
          position: "relative",
          padding: "40px 32px 16px",
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "center",
          gap: "12px",
          maxWidth: "400px",
          margin: "0 auto",
        }}
        aria-hidden
      >
        {CHIPS.map((label, i) => (
          <span
            key={label}
            className={ROTATIONS[i]}
            style={{
              padding: "6px 12px",
              borderRadius: "20px",
              fontSize: "14px",
              fontWeight: 500,
              background: "var(--color-cream)",
              border: "1px solid var(--auth-border)",
              color: "var(--auth-muted)",
              opacity: 0.6,
            }}
          >
            {label}
          </span>
        ))}
      </div>
      <h1
        style={{
          fontFamily: "'DM Sans', system-ui, sans-serif",
          fontSize: "28px",
          fontWeight: 700,
          color: "var(--auth-ink)",
          textAlign: "center",
          padding: "0 24px",
          marginTop: "-8px",
        }}
      >
        {headline}
      </h1>
    </div>
  );
}
