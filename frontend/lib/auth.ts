const USER_KEY = "pixie_user";
let cachedUser: string | null = null;

export function clearSession(): void {
  cachedUser = null;
  if (typeof window === "undefined") return;
  try {
  // Remove the legacy duplicate bearer token from older app builds.
  localStorage.removeItem("pixie_token");
  localStorage.removeItem(USER_KEY);
  for (const key of Object.keys(localStorage)) {
    if (key.startsWith("pixie:sprouts-avatar:")) localStorage.removeItem(key);
  }
  } catch { /* Session invalidation must still work when browser storage is unavailable. */ }
}

export function getCachedUser(): string | null {
  if (typeof window === "undefined") return null;
  return cachedUser;
}

export function setCachedUser(name: string): void {
  cachedUser = name;
  if (typeof window !== "undefined") {
    try { localStorage.removeItem(USER_KEY); } catch { /* Cache remains in memory only. */ }
  }
}

export function postLoginPath(next: string | null, audience: "student" | "teacher", fallback: string): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.includes("\\")) return fallback;
  try {
    const url = new URL(next, "https://pixie.invalid");
    if (url.origin !== "https://pixie.invalid") return fallback;
    const allowed = audience === "teacher"
      ? url.pathname === "/school/dashboard" || url.pathname.startsWith("/school/dashboard/")
      : url.pathname === "/app" || url.pathname.startsWith("/app/")
        || url.pathname === "/dashboard" || url.pathname.startsWith("/dashboard/")
        || url.pathname === "/onboarding" || url.pathname.startsWith("/onboarding/");
    return allowed ? `${url.pathname}${url.search}${url.hash}` : fallback;
  } catch {
    return fallback;
  }
}
