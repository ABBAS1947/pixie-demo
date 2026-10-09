import { supabase } from "@/lib/supabase";
import { API_URL } from "./apiOrigin";

export const AUTH_INVALID_EVENT = "pixie:auth-invalid";

let refreshInFlight: Promise<{ token: string | null; invalid: boolean }> | null = null;

async function currentAccessToken(): Promise<{ token: string | null; unavailable: boolean }> {
  try {
    const { data, error } = await supabase.auth.getSession();
    return { token: data.session?.access_token ?? null, unavailable: !data.session && Boolean(error) };
  } catch {
    return { token: null, unavailable: true };
  }
}

async function refreshAccessToken(): Promise<{ token: string | null; invalid: boolean }> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const { data, error } = await supabase.auth.refreshSession();
        if (error) {
          return { token: null, invalid: error.name === "AuthApiError" || error.status === 400 };
        }
        const token = data.session?.access_token ?? null;
        return { token, invalid: !token };
      } catch {
        return { token: null, invalid: false };
      }
    })().finally(() => { refreshInFlight = null; });
  }
  return refreshInFlight;
}

function signalInvalidSession(): void {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(AUTH_INVALID_EVENT));
  }
}

/**
 * Forward the current Supabase access token to same-origin API calls. A 401
 * gets one refresh and replay; transport failures and 5xx responses never
 * clear the user's session.
 */
export async function apiFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  if (typeof window === "undefined") return fetch(input, init);

  const target = input instanceof Request ? input.url : String(input);
  const targetUrl = new URL(target, window.location.origin);
  const approvedOrigin = new URL(API_URL, window.location.origin).origin;
  if (targetUrl.origin !== approvedOrigin) {
    const foreignHeaders = new Headers(init.headers ?? (input instanceof Request ? input.headers : undefined));
    foreignHeaders.delete("Authorization");
    return fetch(input, { ...init, headers: foreignHeaders, credentials: "omit" });
  }

  const headers = new Headers(init.headers ?? (input instanceof Request ? input.headers : undefined));
  // Never fall back to a stale mirrored token from localStorage.
  headers.delete("Authorization");
  const session = await currentAccessToken();
  const token = session.token;
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const requestInit: RequestInit = { ...init, headers, cache: "no-store", credentials: "omit", redirect: "error" };
  const response = await fetch(input, requestInit);
  if (response.status !== 401) return response;

  const refresh = await refreshAccessToken();
  if (!refresh.token) {
    if ((!token && !session.unavailable) || refresh.invalid) signalInvalidSession();
    return response;
  }

  headers.set("Authorization", `Bearer ${refresh.token}`);
  const retry = await fetch(input, { ...requestInit, headers });
  if (retry.status === 401) signalInvalidSession();
  return retry;
}
