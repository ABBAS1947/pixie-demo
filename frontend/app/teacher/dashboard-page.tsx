"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchTeacherOverview, type SchoolStudentSummary } from "@/lib/api";
import styles from "@/components/teacher/teacher.module.css";

export default function TeacherDashboard() {
  const [students, setStudents] = useState<SchoolStudentSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    fetchTeacherOverview().then(data => { if (active) setStudents(data.students); })
      .catch(cause => { if (active) setError(cause instanceof Error ? cause.message : "Records unavailable."); });
    return () => { active = false; };
  }, []);
  return <main className={styles.page}><header className={styles.pageHeader}><div><h1>School progress</h1>
    <p>Only authorized school progress and assessment records appear here.</p>
    </div></header>
    {error && <p className={styles.errorBanner} role="alert">{error}</p>}
    {!students && !error && <p role="status">Loading records…</p>}
    {students?.length === 0 && <p>No authorized school records are available.</p>}
    {students?.map(student => <article className={styles.panel} key={student.enrollment_id}>
      <h2><Link className={styles.studentLink} href={`/school/dashboard/student?id=${encodeURIComponent(student.enrollment_id)}`}>{student.name}</Link></h2>
      <p>Mastery: {student.avg_mastery === null ? "Not assessed" : `${Math.round(student.avg_mastery * 100)}%`}</p>
      <p>{student.completed_practice} completed practice activities</p>
    </article>)}
  </main>;
}
