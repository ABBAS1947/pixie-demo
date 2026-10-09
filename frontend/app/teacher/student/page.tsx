"use client";
import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { fetchTeacherStudent, type SchoolStudentRecord } from "@/lib/api";
import styles from "./student.module.css";

export default function StudentPage() {
  return <Suspense fallback={<p role="status">Loading record…</p>}><StudentRoute /></Suspense>;
}
function StudentRoute() {
  const id = useSearchParams().get("id") ?? "";
  return <StudentRecord key={id} id={id} />;
}
function StudentRecord({ id }: { id: string }) {
  const [record, setRecord] = useState<SchoolStudentRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    fetchTeacherStudent(id).then(data => { if (active) setRecord(data); })
      .catch(cause => { if (active) setError(cause instanceof Error ? cause.message : "Record unavailable."); });
    return () => { active = false; };
  }, [id]);
  return <main className={styles.page}><Link className={styles.backLink} href="/school/dashboard">Back to school progress</Link>
    {error && <p role="alert">{error}</p>}
    {!record && !error && <p role="status">Loading record…</p>}
    {record && <><header className={styles.header}><h1>{record.projection.display_name}</h1></header>
      <section className={styles.panel}>
      <h2>Mastery</h2><ul>{record.projection.skills.map(skill => <li key={skill.code}>{skill.code}: {Math.round(skill.mastery * 100)}% ({skill.attempts} attempts)</li>)}</ul>
      <h2>Assessment results</h2><ul>{record.projection.results.map(result => <li key={result.assessment_id}>{result.assessment_id}: {result.score}%</li>)}</ul>
      <h2>Suggested practice</h2><ul>{record.projection.suggested_skill_codes.map(code => <li key={code}>{code}</li>)}</ul>
      <p>{record.projection.completed_practice} completed practice activities; {record.projection.independent_correct} independent correct responses.</p>
      </section>
    </>}
  </main>;
}
