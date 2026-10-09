"use client";

import { ThemeProvider } from "@/lib/ThemeContext";
import LearnerShell from "@/components/LearnerShell";
import ApiSessionGuard from "@/components/ApiSessionGuard";

export default function ClientProviders({ children }: { children: React.ReactNode }) {
  return <ThemeProvider><ApiSessionGuard><LearnerShell>{children}</LearnerShell></ApiSessionGuard></ThemeProvider>;
}
