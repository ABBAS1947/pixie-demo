"use client";

// Small kami-styled primitives. Single source of truth for the visual
// language so every screen stays consistent with the design system.

import { cva, type VariantProps } from "class-variance-authority";
import type { ButtonHTMLAttributes, ReactNode } from "react";

// Button — ink-blue primary, warm-sand secondary, quiet text tertiary.
const button = cva(
  "inline-flex items-center justify-center gap-2 rounded-md font-medium transition-[box-shadow] duration-200 select-none disabled:opacity-40 disabled:pointer-events-none",
  {
    variants: {
      variant: {
        primary:
          "bg-accent text-accent-on shadow-ring-accent hover:shadow-whisper active:bg-accent-active",
        secondary:
          "bg-surface-warm text-fg shadow-ring hover:shadow-whisper",
        ghost: "text-muted hover:text-fg hover:bg-surface",
        danger: "bg-danger text-accent-on hover:shadow-whisper",
      },
      size: {
        sm: "h-8 px-3 text-sm",
        md: "h-10 px-4 text-base",
        lg: "h-12 px-6 text-md",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof button> {}

export function Button({ variant, size, className, ...props }: ButtonProps) {
  return <button className={button({ variant, size, className })} {...props} />;
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-lg bg-surface shadow-ring ${className ?? ""}`}>{children}</div>
  );
}

export function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <p
      className="text-xs uppercase text-meta"
      style={{ letterSpacing: "var(--tracking-eyebrow)" }}
    >
      {children}
    </p>
  );
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="flex flex-col gap-2">
      <span className="text-sm font-medium text-fg-2">{label}</span>
      {children}
      {hint ? <span className="text-xs text-meta">{hint}</span> : null}
    </label>
  );
}

export function TextInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={`h-10 w-full rounded-md bg-surface px-3 text-base text-fg shadow-ring transition-shadow placeholder:text-meta focus:shadow-ring-accent ${props.className ?? ""}`}
    />
  );
}

export function TextArea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={`w-full rounded-md bg-surface px-3 py-2 text-base text-fg shadow-ring transition-shadow placeholder:text-meta focus:shadow-ring-accent ${props.className ?? ""}`}
    />
  );
}

// Tag chip — solid hex fills, never rgba (print-safe).
export function Tag({ children, color = "var(--tag-bg-soft)" }: { children: ReactNode; color?: string }) {
  return (
    <span
      className="inline-flex items-center rounded-sm px-2 py-0.5 text-xs text-fg-2"
      style={{ background: color }}
    >
      {children}
    </span>
  );
}

// Notebook tag pill. The accent variable follows the surrounding theme scope.
export function TagPill({ children }: { children: ReactNode }) {
  return (
    <span
      className="inline-flex items-center rounded-full px-2 py-0.5 text-[11px] text-accent"
      style={{
        background: "color-mix(in srgb, var(--accent) 12%, transparent)",
        fontFamily: "var(--nb-ui)",
      }}
    >
      {children}
    </span>
  );
}
