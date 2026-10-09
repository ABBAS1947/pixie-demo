"use client";

import { Fragment, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { clearSession } from "@/lib/auth";
import { AUTH_INVALID_EVENT } from "@/lib/apiRequest";
import { supabase } from "@/lib/supabase";

const PUBLIC_PATHS = new Set(["/", "/login", "/school/login", "/deletion-status"]);

function loginPathFor(pathname: string): string {
  return pathname === "/school" || pathname.startsWith("/school/")
    ? "/school/login"
    : "/login";
}

function returnPath(): string {
  if (typeof window === "undefined") return "/";
  return `${window.location.pathname}${window.location.search}${window.location.hash}`;
}

export default function ApiSessionGuard({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() ?? "/";
  const router = useRouter();
  const [authorizedPath, setAuthorizedPath] = useState<string | null>(null);
  const [sessionCheckErrorPath, setSessionCheckErrorPath] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [identity, setIdentity] = useState<string | null>(null);
  const isPublic = PUBLIC_PATHS.has(pathname);

  useEffect(() => {
    if (isPublic) return;

    let active = true;
    let redirecting = false;
    const redirectToLogin = (reason = "session-expired") => {
      if (!active || redirecting) return;
      redirecting = true;
      setAuthorizedPath(null);
      clearSession();
      void supabase.auth.signOut({ scope: "local" });
      const query = new URLSearchParams({ reason, next: returnPath() });
      router.replace(`${loginPathFor(pathname)}?${query.toString()}`);
    };

    const handleInvalidSession = () => redirectToLogin();
    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === "SIGNED_OUT") redirectToLogin();
      if (session?.user.id) setIdentity(session.user.id);
    });
    window.addEventListener(AUTH_INVALID_EVENT, handleInvalidSession);

    void supabase.auth.getSession().then(({ data, error }) => {
      if (!active) return;
      if (data.session?.access_token) {
        setIdentity(data.session.user.id);
        setSessionCheckErrorPath(null);
        setAuthorizedPath(pathname);
      } else if (error && (error.name !== "AuthApiError" || (error.status !== 400 && error.status !== 401))) {
        setSessionCheckErrorPath(pathname);
      } else {
        redirectToLogin();
      }
    }).catch(() => {
      if (active) setSessionCheckErrorPath(pathname);
    });

    return () => {
      active = false;
      subscription.unsubscribe();
      window.removeEventListener(AUTH_INVALID_EVENT, handleInvalidSession);
    };
  }, [attempt, isPublic, pathname, router]);

  if (isPublic) return children;
  if (authorizedPath !== pathname) {
    return sessionCheckErrorPath === pathname
      ? <main role="alert" style={{ minHeight: "100vh", display: "grid", placeContent: "center", gap: 12, color: "#40220f" }}><p>We couldn’t check your sign-in. Check your connection and try again.</p><button type="button" onClick={() => { setSessionCheckErrorPath(null); setAttempt((value) => value + 1); }}>Try again</button></main>
      : <div role="status" aria-live="polite" style={{ minHeight: "100vh" }} />;
  }
  return <Fragment key={identity}>{children}</Fragment>;
}
