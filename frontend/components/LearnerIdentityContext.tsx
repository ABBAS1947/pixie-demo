"use client";

import { createContext, useContext } from "react";
import type { DashboardData } from "@/lib/dashboard";

export type LearnerIdentity = { userId: string | null; name: string | null; rank: string | null };

export type LearnerIdentityContextValue = {
  identity: LearnerIdentity | null;
  loading: boolean;
  sessionUserId: string | null;
  sessionResolved: boolean;
  updateFromDashboard: (dashboard: DashboardData, expectedSessionUserId: string) => void;
  updateUserId: (userId: string, expectedSessionUserId: string, name?: string) => void;
  markIdentityUnavailable: (expectedSessionUserId: string) => void;
};

export const LearnerIdentityContext = createContext<LearnerIdentityContextValue | null>(null);

export function useLearnerIdentity() {
  const context = useContext(LearnerIdentityContext);
  if (!context) throw new Error("useLearnerIdentity must be used inside LearnerShell");
  return context;
}
