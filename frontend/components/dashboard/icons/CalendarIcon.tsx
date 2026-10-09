interface CalendarIconProps { color?: string; size?: number; }

/** Filled calendar glyph used in navigation; the previous path was not a calendar shape. */
export default function CalendarIcon({ color = "currentColor", size = 24 }: CalendarIconProps) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <rect x="3" y="4" width="18" height="17" rx="3" fill={color} />
    <path d="M3 9h18M8 2v4M16 2v4" stroke="var(--color-orange,#fb6b07)" strokeWidth="2" strokeLinecap="round" />
    <path d="M7 13h.01M12 13h.01M17 13h.01M7 17h.01M12 17h.01M17 17h.01" stroke="var(--color-orange,#fb6b07)" strokeWidth="2.2" strokeLinecap="round" />
  </svg>;
}
