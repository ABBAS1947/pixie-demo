"use client";

import type { AuthAudience, AuthMode } from "../page";
import type { CSSProperties } from "react";
import AuthForm from "./AuthForm";
import PreviewPanel from "./PreviewPanel";
import FloatingChips from "./FloatingChips";

interface Props {
  mode: AuthMode;
  onModeChange: (m: AuthMode) => void;
  initialError?: string | null;
  audience?: AuthAudience;
}

export default function AuthLayout({ mode, onModeChange, initialError, audience = "student" }: Props) {
  return (
    <main
      style={{
        fontFamily: "'DM Sans', system-ui, sans-serif",
        minHeight: "100dvh",
        width: "100%",
        background: "var(--color-background)",
        color: "var(--color-dark)",
        "--auth-ink": "var(--color-dark)",
        "--auth-muted": "rgba(66, 25, 1, 0.64)",
        "--auth-quiet": "rgba(66, 25, 1, 0.45)",
        "--auth-border": "#eadfd3",
        "--auth-focus": "var(--color-orange)",
        "--auth-error": "#a4382e",
      } as CSSProperties}
      className="auth-layout flex flex-col lg:flex-row"
    >
      {/* left: form */}
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          padding: "48px 24px",
          background: "var(--color-background)",
        }}
        className="lg:px-16"
      >
        <FloatingChips mode={mode} />
        <AuthForm mode={mode} onModeChange={onModeChange} initialError={initialError} audience={audience} />
      </div>

      {/* right: desktop only */}
      <div
        style={{
          flex: 1,
          background: "var(--color-background)",
          alignItems: "center",
          justifyContent: "center",
          position: "relative",
          overflow: "hidden",
          display: "none",
        }}
        className="lg:!flex"
      >
        <PreviewPanel />
      </div>
    </main>
  );
}
