"use client";

import { useRouter } from "next/navigation";

interface DueTomorrowCardProps {
  title: string;
  items: { label: string; detail: string }[];
  className?: string;
}

/**
 * Due card — cream background, dark text, nearest deadline day.
 * Height: 152px (fixed from Figma), card radius 28px, shadow.
 * Zero deadlines renders the onboarding state, never an empty box.
 */
export default function DueTomorrowCard({ title, items, className = "" }: DueTomorrowCardProps) {
  const router = useRouter();

  if (items.length === 0) {
    return (
      <div
        className={`flex flex-col items-center justify-center rounded-[16px] p-5 shadow-elevated text-center ${className}`}
        style={{
          backgroundColor: "var(--color-cream)",
          minHeight: 88,
        }}
      >
        <h3 className="font-card-heading text-dark">No deadlines yet</h3>
        <p className="font-body text-dark mt-1" style={{ opacity: 0.8 }}>
          Add exam and assignment dates so Pixie can plan around them.
        </p>
        <button
          onClick={() => router.push("/app/calendar")}
          className="btn-3d-rect font-body mt-3"
        >
          <span className="bs"></span>
          <span className="be"></span>
          <span className="bf">Add one</span>
        </button>
      </div>
    );
  }

  return (
    <div
      className={`flex flex-col rounded-[16px] p-5 shadow-elevated ${className}`}
      style={{
        backgroundColor: "var(--color-cream)",
        height: 88,
      }}
    >
      <h3 className="font-card-heading text-dark mb-2">{title}</h3>
      <ul className="flex flex-col gap-1">
        {items.map((item, i) => (
          <li key={i} className="font-body text-dark">
            {item.label} — {item.detail}
          </li>
        ))}
      </ul>
    </div>
  );
}
