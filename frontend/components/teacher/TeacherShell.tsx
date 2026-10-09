"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ArrowUpRight, BookOpen, LayoutDashboard, LogOut, Users } from "lucide-react";
import { supabase } from "@/lib/supabase";
import { clearSession } from "@/lib/auth";
import { initials } from "@/lib/teacher-dashboard";
import styles from "./teacher.module.css";

export default function TeacherShell({ children, name }: { children: React.ReactNode; name: string }) {
  return <div className={styles.school}>
    <a href="#teacher-content" className={styles.skipLink}>Skip to dashboard</a>
    <Suspense fallback={<aside className={styles.sidebar} aria-label="Loading navigation" />}>
      <TeacherNavigation name={name} />
    </Suspense>
    <main className={styles.main} id="teacher-content" tabIndex={-1}>{children}</main>
  </div>;
}

function TeacherNavigation({ name }: { name: string }) {
  const search = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();
  const [signingOut, setSigningOut] = useState(false);
  const [error, setError] = useState(false);
  const sample = search.get("sample") === "1";
  const studentsSelected = pathname.endsWith("/student") || search.get("view") === "students";
  const overviewHref = `/school/dashboard${sample ? "?sample=1" : ""}`;
  const studentsHref = `/school/dashboard?view=students${sample ? "&sample=1" : ""}`;

  async function signOut() {
    setSigningOut(true);
    setError(false);
    try {
      const { error: authError } = await supabase.auth.signOut();
      if (authError) throw authError;
      clearSession();
      router.replace("/school/login");
    } catch {
      setError(true);
      setSigningOut(false);
    }
  }

  return <aside className={styles.sidebar} aria-label="Teacher workspace">
    <Link className={styles.brand} href={overviewHref} aria-label="Pixie teacher home">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/icons/PixieLogo(silhouette)-06.svg" alt="" width={37} height={39} />
      <span>pixie<span className={styles.brandLabel}>For teachers</span></span>
    </Link>
    <div className={styles.workspaceLabel}>Your workspace</div>
    <nav className={styles.navigation} aria-label="Teacher navigation">
      <Link className={!studentsSelected ? styles.navActive : undefined} href={overviewHref} aria-current={!studentsSelected ? "page" : undefined}><LayoutDashboard size={19} aria-hidden="true" />Overview</Link>
      <Link className={studentsSelected ? styles.navActive : undefined} href={studentsHref} aria-current={studentsSelected ? "page" : undefined}><Users size={19} aria-hidden="true" />Students</Link>
    </nav>
    <div className={styles.sidebarHelp}>
      <span className={styles.helpIcon}><BookOpen size={21} strokeWidth={1.6} aria-hidden="true" /></span>
      <h2>See the learning behind the numbers.</h2>
      <p>Open a student to explore their concepts, practice, and lessons.</p>
      <Link href={studentsHref}>Explore your students<ArrowUpRight size={16} aria-hidden="true" /></Link>
    </div>
    <div className={styles.teacherIdentity}>
      <span className={styles.identityAvatar} aria-hidden="true">{initials(name)}</span>
      <span><strong>{name || "Teacher"}</strong><small>Teacher account</small></span>
      <button type="button" className={styles.iconButton} onClick={signOut} disabled={signingOut} aria-label={signingOut ? "Signing out" : "Sign out"} title="Sign out"><LogOut size={17} aria-hidden="true" /></button>
    </div>
    {error && <p className={styles.signOutError} role="alert">Couldn’t sign out. Please try again.</p>}
  </aside>;
}
