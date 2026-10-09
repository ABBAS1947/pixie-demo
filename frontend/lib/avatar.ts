/** Build a stable Sprouts avatar URL from the account's opaque ID. */
export function avatarUrlForUserId(userId: string | null | undefined): string {
  const seed = userId?.trim() || "pixie-default";
  return `https://api.dicebear.com/10.x/sprouts/svg?seed=${encodeURIComponent(seed)}`;
}
