/**
 * Deterministic per-subject color system.
 * Maps a course ID to one of 6 fixed palette colors via a stable hash.
 * The palette variables live in globals.css under .notebook scope.
 */

const PALETTE = [
  "--subject-1", // sage
  "--subject-2", // clay
  "--subject-3", // dusty blue
  "--subject-4", // mustard
  "--subject-5", // muted plum
  "--subject-6", // soft teal
] as const;

/** Return a CSS var() reference for the given courseId's color. */
export function subjectColorVar(courseId: string | null | undefined): string {
  if (!courseId) return "var(--ink-soft)";
  let hash = 0;
  for (let i = 0; i < courseId.length; i++) {
    hash = (hash * 31 + courseId.charCodeAt(i)) >>> 0;
  }
  return `var(${PALETTE[hash % PALETTE.length]})`;
}
