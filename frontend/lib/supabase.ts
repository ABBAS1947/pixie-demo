// Supabase client + session sync. Talks to Supabase Auth only; the FastAPI
// backend is reached via lib/api.ts using the access token as a Bearer header.

import { createClient } from "@supabase/supabase-js";
import { clearSession } from "./auth";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

export const supabase = createClient(url, anonKey, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
  },
});

// Keep lib/api.ts's synchronous token store in sync with the live Supabase
// session. supabase-js auto-refreshes access tokens in the background and
// fires this listener on every change (sign-in, refresh, sign-out).
if (typeof window !== "undefined") {
  supabase.auth.onAuthStateChange((event, session) => {
    if (!session && event === "SIGNED_OUT") clearSession();
  });
}
