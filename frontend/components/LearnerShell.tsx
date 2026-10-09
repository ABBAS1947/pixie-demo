"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import LearnerSidebar from "@/components/LearnerSidebar";
import { LearnerIdentityContext, type LearnerIdentity } from "@/components/LearnerIdentityContext";
import { supabase } from "@/lib/supabase";
import { fetchMe } from "@/lib/api";
import { fetchDashboard, type DashboardData } from "@/lib/dashboard";

function identityFromDashboard(dashboard: DashboardData): LearnerIdentity {
  return {
    userId: typeof dashboard.user_id === "string" && dashboard.user_id.trim() ? dashboard.user_id.trim() : null,
    name: dashboard.student_name?.trim() || null,
    rank: dashboard.rank_name?.trim() || null,
  };
}

export default function LearnerShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isLearnerRoute = pathname === "/dashboard" || pathname.startsWith("/dashboard/") || pathname === "/app" || pathname.startsWith("/app/");
  const isAppRoute = pathname === "/app" || pathname.startsWith("/app/");
  const [sessionUserId, setSessionUserId] = useState<string | null>(null);
  const [sessionResolved, setSessionResolved] = useState(false);
  const [identity, setIdentity] = useState<LearnerIdentity | null>(null);
  const [loading, setLoading] = useState(true);
  const sessionUserIdRef = useRef<string | null>(null);

  const acceptSessionUser = useCallback((userId: string | null) => {
    if (sessionUserIdRef.current !== userId) {
      sessionUserIdRef.current = userId;
      setSessionUserId(userId);
      setIdentity(null);
      setLoading(Boolean(userId));
    }
    setSessionResolved(true);
  }, []);

  useEffect(() => {
    let active = true;
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      if (active) acceptSessionUser(session?.user.id ?? null);
    });
    void supabase.auth.getSession().then(({ data }) => {
      if (active) acceptSessionUser(data.session?.user.id ?? null);
    }).catch(() => {
      if (active) acceptSessionUser(null);
    });
    return () => {
      active = false;
      subscription.unsubscribe();
    };
  }, [acceptSessionUser]);

  const updateFromDashboard = useCallback((dashboard: DashboardData, expectedSessionUserId: string) => {
    const next = identityFromDashboard(dashboard);
    if (expectedSessionUserId === sessionUserIdRef.current && next.userId) {
      setIdentity(next);
      setLoading(false);
    }
  }, []);

  const updateUserId = useCallback((userId: string, expectedSessionUserId: string, name?: string) => {
    const normalizedId = userId.trim();
    if (normalizedId && expectedSessionUserId === sessionUserIdRef.current) {
      setIdentity((current) => ({ userId: normalizedId, name: name?.trim() || current?.name || null, rank: current?.rank || null }));
      setLoading(false);
    }
  }, []);

  const markIdentityUnavailable = useCallback((expectedSessionUserId: string) => {
    if (expectedSessionUserId === sessionUserIdRef.current) setLoading(false);
  }, []);

  useEffect(() => {
    if (!isAppRoute || !sessionResolved || !sessionUserId) return;
    if (identity) return;

    let active = true;
    setLoading(true);
    void fetchDashboard().then((dashboard) => {
      const next = identityFromDashboard(dashboard);
      if (!active || sessionUserIdRef.current !== sessionUserId) return;
      if (!next.userId) throw new Error("Dashboard response did not include a user ID.");
      setIdentity(next);
      setLoading(false);
    }).catch(async () => {
      try {
        const user = await fetchMe();
        if (active && sessionUserIdRef.current === sessionUserId) {
          const userId = user.user_id?.trim();
          if (userId) setIdentity({ userId, name: user.name?.trim() || null, rank: null });
          setLoading(false);
        }
      } catch {
        if (active && sessionUserIdRef.current === sessionUserId) setLoading(false);
      }
    });
    return () => { active = false; };
  }, [identity, isAppRoute, sessionResolved, sessionUserId]);

  const contextValue = useMemo(() => ({ identity, loading, sessionUserId, sessionResolved, updateFromDashboard, updateUserId, markIdentityUnavailable }), [identity, loading, sessionUserId, sessionResolved, updateFromDashboard, updateUserId, markIdentityUnavailable]);

  return (
    <LearnerIdentityContext.Provider value={contextValue}>
      {isLearnerRoute && sessionResolved && sessionUserId && <LearnerSidebar />}
      {children}
    </LearnerIdentityContext.Provider>
  );
}
