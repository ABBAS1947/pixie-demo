interface SessionBannerProps {
  title: string;
  onPrev: () => void;
  onNext: () => void;
}

function Arrow({ dir, onClick }: { dir: "prev" | "next"; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      aria-label={dir === "prev" ? "Previous session" : "Next session"}
      className="flex items-center justify-center"
      style={{
        width: 28,
        height: 28,
        borderRadius: "50%",
        backgroundColor: "var(--color-dark)",
        flexShrink: 0,
      }}
    >
      <img
        src="/icons/send-arrow.svg"
        alt=""
        width={14}
        height={7}
        style={{ transform: dir === "prev" ? "rotate(90deg)" : "rotate(-90deg)" }}
      />
    </button>
  );
}

/**
 * Session switcher banner — cream pill 589x71 with prev/next arrows.
 * Same component family as the dashboard's Recent Activity banner.
 */
export default function SessionBanner({ title, onPrev, onNext }: SessionBannerProps) {
  return (
    <div
      className="flex items-center justify-between"
      style={{
        width: 341,
        maxWidth: "100%",
        height: 41,
        backgroundColor: "var(--color-cream)",
        borderRadius: 20,
        padding: "0 7px",
        margin: "0 auto",
      }}
    >
      <Arrow dir="prev" onClick={onPrev} />
      <h2
        className="font-body text-center flex-1"
        style={{ fontSize: 12, fontWeight: 700, color: "var(--color-dark)" }}
      >
        {title}
      </h2>
      <Arrow dir="next" onClick={onNext} />
    </div>
  );
}
