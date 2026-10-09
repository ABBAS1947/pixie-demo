interface BehindOnCardProps {
  subjects: { name: string; topic: string; score: number }[];
  streakDays: number;
  streakEarned?: number[];
  className?: string;
  style?: React.CSSProperties;
}

const STREAK_GOALS = [3, 7, 14, 30, 60, 100];

const STREAK_TIPS = [
  "One short session a day beats a long one once a week.",
  "Same time every day turns studying into habit.",
  "Stuck? Ask Pixie for a smaller piece, then build up.",
  "Finish one quiz before you close the app.",
  "Review yesterday's weakest topic first.",
  "Teach it back to Pixie — explaining locks it in.",
];

/**
 * Behind-on card — orange background, white text, list of subjects.
 * Height: 321px (fixed from Figma), card radius 28px, shadow.
 * Empty state flips to the streak card: the count, the next goal with its
 * reward, and one rotating tip. No pill, no count shown at zero — a fresh
 * board invites the start instead.
 */
export default function BehindOnCard({ subjects, streakDays, streakEarned = [], className = "", style }: BehindOnCardProps) {
  if (subjects.length > 0) {
    return (
      <div
        className={`flex flex-col rounded-[16px] p-6 shadow-elevated ${className}`}
        style={{
          backgroundColor: "var(--color-orange)",
          minHeight: 186,
          ...style,
        }}
        >
        <h2 className="font-section-heading text-white mb-4">You&apos;re behind on:</h2>
        <ul className="flex flex-col gap-2">
          {subjects.map((s, i) => (
            <li key={i} className="font-body text-white">
              {s.name} — {s.topic} — {s.score}%
            </li>
          ))}
        </ul>
      </div>
    );
  }

  const nextGoal = STREAK_GOALS.find((g) => streakDays < g) ?? null;
  const tip = STREAK_TIPS[streakDays % STREAK_TIPS.length];

  return (
    <div
      className={`flex flex-col items-center justify-center rounded-[16px] p-6 shadow-elevated text-center ${className}`}
      style={{
        backgroundColor: "var(--color-orange)",
        minHeight: 186,
        ...style,
      }}
    >
      {streakDays <= 0 ? (
        <>
          <h2 className="font-section-heading text-white">A clean board</h2>
          <p className="font-body text-white mt-2" style={{ opacity: 0.9 }}>
            Start your streak today — one session counts.
          </p>
        </>
      ) : (
        <>
          <p
            className="font-body text-white"
            style={{ fontSize: 37, fontWeight: 800, lineHeight: 1 }}
          >
            {streakDays}
          </p>
          <h2 className="font-section-heading text-white mt-2">
            day streak
          </h2>
        </>
      )}
      {streakEarned.length > 0 && (
        <p className="font-body text-white mt-2" style={{ fontWeight: 700 }}>
          Reward earned: {streakEarned.join(", ")}-day goal!
        </p>
      )}
      {nextGoal !== null && streakDays > 0 && (
        <p className="font-body text-white mt-2" style={{ opacity: 0.9 }}>
          {nextGoal - streakDays} day{nextGoal - streakDays === 1 ? "" : "s"} to your {nextGoal}-day reward
        </p>
      )}
      <p className="font-body text-white mt-3" style={{ opacity: 0.85, fontSize: 15 }}>
        Tip: {tip}
      </p>
    </div>
  );
}
