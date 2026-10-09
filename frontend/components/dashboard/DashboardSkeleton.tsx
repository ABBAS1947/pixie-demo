interface DashboardSkeletonProps {
  iconSize: number;
}

/**
 * Loading placeholder for the Dashboard.
 *
 * Mirrors DashboardContent's flow structure — same gaps, card heights,
 * badge sizes — so the swap to real data doesn't jump. No absolute icon
 * math: the top row preserves the dashboard's page-level spacing.
 */
export default function DashboardSkeleton({ iconSize }: DashboardSkeletonProps) {
  return (
    <div className="w-full flex flex-col">
      {/* ── Top bar ───────────────────────────────────────────────────── */}
      <div className="w-full flex items-start justify-between" style={{ marginBottom: 61 }}>
        <div className="flex items-start" style={{ gap: 15 }}>
          <Bone shape="circle" style={{ width: iconSize, height: iconSize }} />
          <Bone radius={24} style={{ width: 130, height: 48 }} />
        </div>
        <div className="flex items-start" style={{ gap: 15 }}>
          <Bone radius={24} style={{ width: 130, height: 48 }} />
          <Bone shape="circle" style={{ width: iconSize, height: iconSize }} />
        </div>
      </div>

      {/* ── Content column ────────────────────────────────────────────── */}
      <div
        className="flex flex-col w-full"
        style={{ width: "min(100%, var(--content-dashboard))", marginInline: "auto" }}
      >
        {/* Greeting */}
        <div className="flex justify-center" style={{ marginBottom: 15 }}>
          <Bone radius={10} style={{ width: 220, height: 21 }} />
        </div>

        {/* Notification banner */}
        <Bone radius={20} style={{ width: "100%", height: 41, marginBottom: 10 }} />

        {/* Cards row — same wrap behavior as the real row */}
        <div className="flex" style={{ gap: 15, marginBottom: 19, flexWrap: "wrap" }}>
          <Bone radius={16} style={{ flex: "1 1 197px", height: 186 }} />
          <div className="flex flex-col" style={{ flex: "1 1 197px", gap: 10 }}>
            <div className="flex" style={{ gap: 15, flexWrap: "wrap" }}>
              <Bone radius={16} style={{ flex: "1 1 128px", height: 88 }} />
              <Bone radius={16} style={{ flex: "1 1 128px", height: 88 }} />
            </div>
            <Bone radius={16} style={{ width: "100%", height: 88 }} />
          </div>
        </div>

        {/* Recent activity */}
        <Bone radius={23} style={{ width: "100%", height: 59, marginBottom: 57 }} />
      </div>

      {/* ── Bottom nav ────────────────────────────────────────────────── */}
      <div className="flex items-center justify-center w-full" style={{ flexWrap: "wrap", rowGap: 16 }}>
        {[48, 48, 112, 48, 48].map((w, i) => (
          <Bone
            key={i}
            shape={w === 112 ? undefined : "circle"}
            radius={w === 112 ? 23 : undefined}
            style={{
              width: w,
              height: w === 112 ? 47 : 48,
              marginRight: i < 4 ? [43, 28, 29, 43][i] : 0,
            }}
          />
        ))}
      </div>
    </div>
  );
}

function Bone({
  style,
  radius,
  shape,
}: {
  style: React.CSSProperties;
  radius?: number;
  shape?: "circle";
}) {
  return (
    <div
      className="animate-pulse"
      style={{
        backgroundColor: "rgba(66, 25, 1, 0.08)",
        borderRadius: shape === "circle" ? "50%" : radius,
        flexShrink: 0,
        ...style,
      }}
    />
  );
}
