"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { fetchMe } from "@/lib/api";
import TeacherShell from "@/components/teacher/TeacherShell";

export default function SchoolDashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [checked, setChecked] = useState(false);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const { data } = await supabase.auth.getSession();
        if (!active) return;
        if (!data.session?.access_token) { router.replace("/school/login"); return; }
        const me = await fetchMe();
        if (!active) return;
        if (!me.is_teacher) { setError("This account does not have teacher access."); setChecked(true); return; }
        setName(me.name);
        setChecked(true);
      } catch {
        if (active) {
          setError("We couldn’t verify your teaching account. Check your connection and try again.");
          setChecked(true);
        }
      }
    })();
    return () => { active = false; };
  }, [attempt, router]);

  if (!checked) return <div role="status" style={{ padding: "48px", color: "#796b5d" }}>Opening your teaching space…</div>;
  if (error) return <main role="alert" style={{ maxWidth: 680, margin: "12vh auto", padding: 32, color: "#40220f" }}><h1>Teaching space unavailable</h1><p>{error}</p><button type="button" onClick={() => { setChecked(false); setError(null); setAttempt((value) => value + 1); }}>Try again</button></main>;
  return <TeacherShell name={name}>{children}</TeacherShell>;
}
