"use client";

import { Suspense, useEffect, useState } from "react";
import AuthLayout from "./components/AuthLayout";
import { useRouter, useSearchParams } from "next/navigation";
import { fetchMe } from "@/lib/api";
import { postLoginPath, setCachedUser } from "@/lib/auth";
import { supabase } from "@/lib/supabase";

export type AuthMode = "login" | "signup";
export type AuthAudience = "student" | "teacher";

function LoginInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [mode, setMode] = useState<AuthMode>(
    (searchParams.get("mode") as AuthMode) || "login"
  );
  const [ready, setReady] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      const error = searchParams.get("error");
      if (error) {
        setAuthError(decodeURIComponent(error));
      } else if (searchParams.get("reason") === "api-restarted") {
        setAuthError("Pixie restarted or updated, so we signed you out. Please sign in again.");
      } else if (searchParams.get("reason") === "session-expired") {
        setAuthError("Your session expired. Please sign in again.");
      }

      // Recovery routes are intentional logged-out states. Do not race the
      // restart notice against a stale Supabase session still clearing locally.
      if (!error && (searchParams.get("reason") === "api-restarted" || searchParams.get("reason") === "session-expired")) {
        if (active) setReady(true);
        return;
      }

      const { data } = await supabase.auth.getSession();
      if (!data.session?.access_token) {
        if (active) setReady(true);
        return;
      }
      try {
        const me = await fetchMe();
        if (!active) return;
        setCachedUser(me.name);
        const fallback = me.is_teacher ? "/school/dashboard" : me.grade_level ? "/app" : "/onboarding";
        router.replace(postLoginPath(searchParams.get("next"), me.is_teacher ? "teacher" : "student", fallback));
        return;
      } catch (initialError) {
        // Only rotate the Supabase session when the backend explicitly rejects
        // the token. Network/server errors should not trigger an auth change.
        if (!(initialError instanceof Error) || initialError.message !== "Invalid or expired token") {
          if (active) {
            setAuthError(initialError instanceof Error ? initialError.message : "Couldn't reach Pixie's API.");
            setReady(true);
          }
          return;
        }
      }

      const { data: refreshed, error: refreshError } = await supabase.auth.refreshSession();
      if (refreshError || !refreshed.session?.access_token) {
        // Keep recovery available; don't send the user back into pages whose
        // API requests would all fail with 401s.
        if (active) {
          setAuthError("Your session needs to be refreshed. Sign in again to continue.");
          setReady(true);
        }
        return;
      }

      try {
        const me = await fetchMe();
        if (!active) return;
        setCachedUser(me.name);
        const fallback = me.is_teacher ? "/school/dashboard" : me.grade_level ? "/app" : "/onboarding";
        router.replace(postLoginPath(searchParams.get("next"), me.is_teacher ? "teacher" : "student", fallback));
      } catch (refreshValidationError) {
        if (active) {
          setAuthError(refreshValidationError instanceof Error
            ? refreshValidationError.message
            : "Your session needs to be refreshed. Sign in again to continue.");
          setReady(true);
        }
      }
    })();
    return () => { active = false; };
  }, [router, searchParams]);

  if (!ready) return null;
  return (
    <AuthLayout
      mode={mode}
      onModeChange={setMode}
      initialError={authError}
    />
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginInner />
    </Suspense>
  );
}
