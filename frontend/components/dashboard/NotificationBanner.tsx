import { ReactNode } from "react";

interface NotificationBannerProps {
  message: string;
  icon?: ReactNode;
  onView?: () => void;
  className?: string;
  style?: React.CSSProperties;
}

/**
 * Notification strip — cream background, bell icon, message, view button.
 * Height: 71px (fixed from Figma), pill radius 35px, HAS shadow.
 * View button does NOT have shadow.
 * Accepts a React component (icon) instead of a file path.
 */
export default function NotificationBanner({
  message,
  icon,
  onView,
  className = "",
  style,
}: NotificationBannerProps) {
  return (
    <div
      className={`flex items-center gap-4 rounded-[20px] px-6 shadow-elevated ${className}`}
      style={{
        height: 41,
        backgroundColor: "var(--color-cream)",
        ...style,
      }}
    >
      {icon}
      <span className="flex-1 font-body-large text-dark">{message}</span>
      <button
        onClick={onView}
        className="btn-3d-pill flex items-center justify-center px-6 py-2"
        style={{
          height: 34,
          minWidth: 71,
        }}
      >
        <span className="bs" aria-hidden="true" />
        <span className="be" aria-hidden="true" />
        <span className="bf font-body-large text-white font-medium" style={{ height: "100%", padding: "0 14px" }}>view</span>
      </button>
    </div>
  );
}
