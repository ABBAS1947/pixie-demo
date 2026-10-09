// Display thresholds only, matching the existing XP policy. Never awards,
// deducts, persists, or overrides the rank/balance returned by the server.
const RANKS = [
  { name: "Novice", xp: 0 },
  { name: "Apprentice", xp: 40 },
  { name: "Journeyman", xp: 120 },
  { name: "Expert", xp: 280 },
  { name: "Grandmaster", xp: 600 },
] as const;

export function rankProgress(xp: number, rank: string) {
  if (!Number.isFinite(xp) || xp < 0) return null;
  const index = RANKS.findIndex((item) => item.name === rank);
  if (index < 0) return null;
  const current = RANKS[index];
  const next = RANKS[index + 1];
  // A changed server policy must not produce a misleading local progress bar.
  if (xp < current.xp || (next && xp >= next.xp)) return null;
  return { current, next, earned: xp - current.xp, required: next ? next.xp - current.xp : null, remaining: next ? next.xp - xp : 0 };
}
