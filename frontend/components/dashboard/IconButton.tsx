import { ReactNode } from "react";

interface IconButtonProps {
  icon: ReactNode;
  alt: string;
  size?: number;
  variant?: "circle" | "square";
  color?: "orange" | "dark";
  className?: string;
  onClick?: () => void;
}

/**
 * Reusable icon button.
 * Accepts a React component (icon) instead of a file path.
 * Colors are set directly on the icon component via its color prop.
 */
export default function IconButton({
  icon,
  alt,
  size = 83,
  variant = "circle",
  color = "orange",
  className = "",
  onClick,
}: IconButtonProps) {
  const radius = variant === "circle" ? "rounded-full" : "rounded-[20px]";
  const bgColor = color === "dark" ? "var(--color-dark)" : "var(--color-orange)";

  return (
    <button
      onClick={onClick}
      className={`flex items-center justify-center shadow-elevated ${radius} ${className}`}
      style={{
        width: size,
        height: size,
        backgroundColor: bgColor,
        flexShrink: 0,
      }}
      aria-label={alt}
    >
      {icon}
    </button>
  );
}
