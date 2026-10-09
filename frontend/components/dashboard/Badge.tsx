import { ReactNode } from "react";

interface BadgeProps {
  label: string;
  icon?: ReactNode;
  variant: "dark" | "orange";
  width?: number;
  height?: number;
  className?: string;
}

/**
 * Reusable badge — Day badge (dark) and Rank badge (orange).
 * Dimensions: 197x70px, pill radius 35px.
 * Accepts a React component (icon) instead of a file path.
 *
 * Label truncates with an ellipsis instead of overflowing the pill — this
 * badge is used with dynamic server text (rank_name, streak count), which
 * won't always be as short as the placeholder examples.
 */
export default function Badge({
  label,
  icon,
  variant,
  width = 130,
  height = 48,
  className = "",
}: BadgeProps) {
  const bgColor = variant === "dark" ? "var(--color-dark)" : "var(--color-orange)";

  return (
    <div
      className={`flex items-center justify-center gap-2 shadow-elevated rounded-[35px] ${className}`}
      style={{
        width,
        height,
        backgroundColor: bgColor,
        padding: "0 16px",
      }}
    >
      {icon}
      <span
        className="font-badge-label text-white"
        style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
      >
        {label}
      </span>
    </div>
  );
}
