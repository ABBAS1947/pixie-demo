interface RecentActivityProps {
  title: string;
  subtitle: string;
  onPrev?: () => void;
  onNext?: () => void;
  className?: string;
  style?: React.CSSProperties;
}

/**
 * Recent Activity banner — cream background, title/subtitle, carousel arrows.
 * Height: 102px (fixed from Figma), banner radius 40px, HAS shadow.
 * Text is centered, dark brown color, larger size, heavier weight.
 */
export default function RecentActivity({
  title,
  subtitle,
  onPrev,
  onNext,
  className = "",
  style,
}: RecentActivityProps) {
  return (
    <div
      className={`flex items-center gap-4 rounded-[23px] px-6 shadow-elevated ${className}`}
      style={{
        height: 59,
        backgroundColor: "var(--color-cream)",
        ...style,
      }}
    >
      {/* Prev arrow */}
      <button
        onClick={onPrev}
        className="flex items-center justify-center rounded-full shrink-0"
        style={{
          width: 34,
          height: 34,
          backgroundColor: "var(--color-dark)",
        }}
        aria-label="Previous"
      >
        <img
          src="/icons/send-arrow.svg"
          alt=""
          width={23.5}
          height={12.8}
          style={{ transform: "rotate(90deg)" }}
        />
      </button>

      {/* Content — centered */}
      <div className="flex-1 flex flex-col items-center justify-center gap-1">
        <h3
          className="font-bold text-center"
          style={{
            fontSize: 14,
            color: "var(--color-dark)",
            fontWeight: 700,
          }}
        >
          {title}
        </h3>
        <p
          className="text-center"
          style={{
            fontSize: 9,
            color: "var(--color-dark)",
            opacity: 0.7,
          }}
        >
          {subtitle}
        </p>
      </div>

      {/* Next arrow */}
      <button
        onClick={onNext}
        className="flex items-center justify-center rounded-full shrink-0"
        style={{
          width: 34,
          height: 34,
          backgroundColor: "var(--color-dark)",
        }}
        aria-label="Next"
      >
        <img
          src="/icons/send-arrow.svg"
          alt=""
          width={23.5}
          height={12.8}
          style={{ transform: "rotate(-90deg)" }}
        />
      </button>
    </div>
  );
}
