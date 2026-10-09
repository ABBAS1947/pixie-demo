import type { TeacherStudentRow } from "./api";

export type StudentFilter = "all" | "review" | "active" | "inactive" | "strong" | "building" | "developing" | "unassessed";
export type MasteryBand = "strong" | "building" | "developing" | "unassessed";

export interface TeacherLesson {
  topic: string;
  subject: string | null;
  phase: string;
  chunk_index: number;
  total_chunks: number;
  updated_at: string | null;
  items: { kind: string; idx: number; title: string; body: string; clothing: string; check_question: string; failure_mode: string | null }[];
  events: { turn: number; signal: string; move: string; latency_ms: number | null; understood: boolean | null }[];
  mastery: { concept: string; p_known: number; attempts: number }[];
  probes: number;
  escalated: boolean;
}

export interface TeacherStudentDetail {
  student: string;
  grade: string | null;
  lessons: TeacherLesson[];
  profile: { advances: number; probes: number; escalations: number; clothing_wins: Record<string, number>; failure_counts: Record<string, number> } | null;
  activity: { notes: number; deadlines: number; quizzes: number };
  quizzes: { kind: string; status: string; score: number | null; items: number; created_at: string | null; completed_at: string | null }[];
  recent_insights: { topics: string[]; mood: string; summary: string }[];
}

export const masteryBands: { key: MasteryBand; label: string; range: string; color: string }[] = [
  { key: "strong", label: "Strong foundation", range: "80–100%", color: "#557c64" },
  { key: "building", label: "Building understanding", range: "50–79%", color: "#c19449" },
  { key: "developing", label: "Early understanding", range: "Below 50%", color: "#bf7155" },
  { key: "unassessed", label: "No estimate yet", range: "No records", color: "#b6b0a6" },
];

export function masteryBand(value: number | null): MasteryBand {
  if (value === null || !Number.isFinite(value)) return "unassessed";
  return value >= 0.8 ? "strong" : value >= 0.5 ? "building" : "developing";
}

export function percent(value: number): number {
  return Math.round(Math.max(0, Math.min(1, value)) * 100);
}

export function reviewConcepts(student: TeacherStudentRow) {
  // The API returns the three lowest concepts, even when every score is high.
  return student.weak_concepts.filter((concept) => concept.p_known < 0.5);
}

export function followUpReason(student: TeacherStudentRow): string | null {
  const concepts = reviewConcepts(student);
  if (concepts.length) return `Revisit ${concepts[0].concept}`;
  if (student.week_turns === 0) return "No lesson turns in 7 days";
  return null;
}

export function matchesFilter(student: TeacherStudentRow, filter: StudentFilter): boolean {
  if (filter === "all") return true;
  if (filter === "review") return followUpReason(student) !== null;
  if (filter === "active") return student.week_turns > 0;
  if (filter === "inactive") return student.week_turns === 0;
  return masteryBand(student.avg_mastery) === filter;
}

export function initials(name: string): string {
  return name.trim().split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase() || "?";
}

export function gradeLabel(grade: string | null): string {
  if (!grade) return "Grade not set";
  return /^\d+$/.test(grade) ? `Grade ${grade}` : grade;
}

export function formatTeacherDate(value: string | null): string {
  if (!value) return "No lessons yet";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Date unavailable" : new Intl.DateTimeFormat("en", { day: "numeric", month: "short" }).format(date);
}

export function studentHref(userId: string, sample: boolean, returnQuery = ""): string {
  const query = new URLSearchParams({ id: userId });
  if (sample) query.set("sample", "1");
  if (returnQuery) query.set("from", returnQuery);
  return `/school/dashboard/student?${query}`;
}

// Fictional fixtures are selected explicitly. Live API failures never activate them.
export function sampleStudents(now: number): TeacherStudentRow[] {
  const records: [string, number | null, number, number, number, string[]][] = [
    ["Aisha Khan", 0.86, 42, 4, 1, ["Cell structure", "Photosynthesis", "Plant transport"]],
    ["Oliver Chen", 0.68, 35, 3, 0, ["Linear equations", "Quadratic graphs", "Factorisation"]],
    ["Sara Ahmed", 0.38, 18, 2, 2, ["Equivalent fractions", "Adding fractions", "Mixed numbers"]],
    ["Lucas Martin", 0.58, 9, 1, 3, ["Atomic structure", "Chemical bonds", "The periodic table"]],
    ["Maya Patel", 0.81, 31, 3, 0, ["Energy transfer", "Forces", "Motion graphs"]],
    ["Adam Hassan", 0.44, 0, 0, 10, ["Sentence structure", "Paragraphs", "Using evidence"]],
    ["Emma Wilson", 0.72, 23, 2, 1, ["Ecosystems", "Food webs", "Biodiversity"]],
    ["Noah Kim", null, 0, 0, 0, []],
  ];
  return records.map(([name, mastery, turns, quizzes, days, concepts], index) => ({
    user_id: `sample-${index + 1}`, name, grade_level: index === 3 || index === 5 ? "9" : "8",
    lessons: concepts.length,
    concepts: concepts.length,
    avg_mastery: mastery,
    weak_concepts: concepts.map((concept, n) => ({ concept, p_known: Math.max(0, Math.min(1, (mastery ?? 0) + (n - 1) * 0.1)) })),
    advances: mastery === null ? 0 : concepts.length * 2,
    probes: mastery === null ? 0 : concepts.length,
    escalations: index === 2 || index === 5 ? 1 : 0,
    last_active: mastery === null ? null : new Date(now - days * 86400000).toISOString(),
    recent_mood: null, week_turns: turns, week_quizzes: quizzes, weekly_target: 30, on_track: turns >= 30,
  }));
}

export function sampleStudentDetail(id: string, now: number): TeacherStudentDetail | null {
  const student = sampleStudents(now).find((item) => item.user_id === id);
  if (!student) return null;
  const updated = student.last_active;
  const lessons: TeacherLesson[] = student.weak_concepts.map((concept, index) => ({
    topic: concept.concept, subject: null, phase: index === 0 ? "teaching" : "complete",
    chunk_index: index === 0 ? 2 : 4, total_chunks: 4, updated_at: updated,
    items: [{ kind: "chunk", idx: 0, title: concept.concept, body: `An explanation of ${concept.concept.toLowerCase()}, followed by a worked example and an independent practice question.`, clothing: "worked_example", check_question: "Can you explain the idea in your own words?", failure_mode: null }],
    events: [
      { turn: 1, signal: "advance", move: "teach", latency_ms: null, understood: null },
      { turn: 2, signal: "probe", move: "alt", latency_ms: null, understood: false },
      { turn: 3, signal: "advance", move: "teach", latency_ms: null, understood: true },
      ...(student.escalations > 0 && index === 0 ? [{ turn: 4, signal: "probe", move: "escalate", latency_ms: null, understood: false }] : []),
    ],
    mastery: [{ ...concept, attempts: 4 + index }], probes: student.escalations > 0 && index === 0 ? 2 : 1,
    escalated: student.escalations > 0 && index === 0,
  }));
  const quizzes = student.avg_mastery === null ? [] : Array.from({ length: student.week_quizzes + 2 }, (_, index) => {
    const offset = [0.1, -0.1, 0.05, -0.15][index % 4];
    const daysAgo = index < student.week_quizzes ? index : index + 8;
    const date = new Date(now - daysAgo * 86400000).toISOString();
    return { kind: index % 2 ? "focus" : "spark", status: "completed", score: Math.max(0, Math.min(1, student.avg_mastery! + offset)), items: index % 2 ? 10 : 5, created_at: date, completed_at: date };
  });
  return {
    student: student.name, grade: student.grade_level, lessons,
    profile: student.avg_mastery === null ? null : { advances: student.advances, probes: student.probes, escalations: student.escalations, clothing_wins: { worked_example: 6, analogy_fun: 3 }, failure_counts: { concept: 2, procedure: 1 } },
    activity: { notes: lessons.length * 2, deadlines: lessons.length ? 2 : 0, quizzes: quizzes.length },
    quizzes, recent_insights: [],
  };
}
