"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import AuthLayout from "@/app/(auth)/login/components/AuthLayout";
import { fetchMe } from "@/lib/api";
import { postLoginPath } from "@/lib/auth";
import { supabase } from "@/lib/supabase";

function TeacherLoginInner() {
  const router = useRouter(); const searchParams = useSearchParams(); const [ready, setReady] = useState(false); const [error, setError] = useState<string | null>(searchParams.get("error") || (searchParams.get("reason") === "api-restarted" ? "Pixie restarted or updated, so we signed you out. Please sign in again." : searchParams.get("reason") === "session-expired" ? "Your session expired. Please sign in again." : null));
  useEffect(() => { (async () => { const { data } = await supabase.auth.getSession(); if (!data.session?.access_token) { setReady(true); return; } try { const me = await fetchMe(); if (me.is_teacher) router.replace(postLoginPath(searchParams.get("next"), "teacher", "/school/dashboard")); else { await supabase.auth.signOut(); setError("This account does not have teacher access."); setReady(true); } } catch { setReady(true); } })(); }, [router, searchParams]);
  if (!ready) return null;
  return <AuthLayout mode="login" onModeChange={() => undefined} initialError={error} audience="teacher" />;
}
export default function TeacherLoginPage() { return <Suspense><TeacherLoginInner /></Suspense>; }
