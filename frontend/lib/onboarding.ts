// The 6-question wizard — state shape, commit payload, summary prose,
// and the client-side grade rule.
//
// Data rules: fully generic — no pre-known user info.
// Answers stay in the same shape the backend expects; the "no field names
// on screen" rule is about rendered text, not the data model.

import type { OnboardingCommitInput, Tone } from "./types";
import { TONE_OPTIONS } from "@/app/onboarding/tone-options";

export interface Answers {
  name: string;
  grade: string | null;
  subjects: string[];
  goals: string[];
  learningStyle: string | null;
  tone: Tone | null;
}

export const EMPTY_ANSWERS: Answers = {
  name: "",
  grade: null,
  subjects: [],
  goals: [],
  learningStyle: null,
  tone: null,
};

/** True when a question has a real answer (used for progress + skip). */
export function hasAnswer(answerKey: string, answers: Answers): boolean {
  const v = answers[answerKey as keyof Answers];
  if (v == null) return false;
  if (Array.isArray(v)) return v.length > 0;
  if (typeof v === "string") return v.trim().length > 0;
  return Boolean(v);
}

/**
 * Client-side grade validation for the "Other" text input.
 * Accepts grouped values like "Middle School (6th-8th)" or raw
 * grade strings like "8th", "Grade 9", "College".
 */
const GRADE_RE =
  /^\s*(middle\s*school|high\s*school|college|university|grade\s*)?(?:\(.*?\))?\s*(?:grade\s*)?(?:\d{1,2}(st|nd|rd|th)?(\s*(year|grade))?(\s+(of\s+)?(college|university))?)?\s*$/i;

export function looksLikeGrade(raw: string): boolean {
  // Accept the grouped values directly
  if (/^(middle\s*school|high\s*school|college\s*\/\s*university)/i.test(raw.trim())) return true;
  // Also accept raw grade strings
  return GRADE_RE.test(raw);
}

export function buildCommitPayload(a: Answers): OnboardingCommitInput {
  return {
    name: a.name.trim() || null,
    grade_level: a.grade?.trim() || null,
    tone: a.tone,
    resource_constraints: null,
    subjects: a.subjects.map((name) => ({ name, hardest: false })),
    struggles: null,
    learning_style: a.learningStyle?.trim() || null,
    schedule: null,
    goals: a.goals.length ? a.goals.join(", ") : null,
  };
}

function gradePhrase(grade: string): string {
  const t = grade.trim();
  if (/college|university/i.test(t)) return "in college";
  if (/high\s*school/i.test(t)) return "in high school";
  if (/middle\s*school/i.test(t)) return "in middle school";
  return `in ${t} grade`;
}

/**
 * Deterministic sentence-template summary — no LLM call, no field
 * names, no skip-list. Only answers actually given appear; a near-empty
 * profile gets the explicit fallback so the paragraph never renders empty.
 */
export function buildSummary(a: Answers): string {
  const answered =
    a.name.trim() ||
    a.grade ||
    a.subjects.length ||
    a.goals.length ||
    a.tone;

  if (!answered) return "Not much to go on yet — I'll figure you out as we go.";

  const sentences: string[] = [];

  const who: string[] = [];
  if (a.name.trim()) who.push(`You're ${a.name.trim()}`);
  if (a.grade) who.push(gradePhrase(a.grade));
  if (who.length) sentences.push(who.join(", ") + ".");

  if (a.subjects.length) {
    const list = a.subjects.slice(0, 3).join(", ");
    sentences.push(`Studying ${list}${a.subjects.length > 3 ? " and more" : ""}.`);
  }
  if (a.goals.length) {
    const list = a.goals.join(", ").toLowerCase();
    sentences.push(`Working toward ${list}.`);
  }
  if (a.tone) {
    const label = TONE_OPTIONS.find((t) => t.id === a.tone)?.label ?? a.tone;
    sentences.push(`I'll keep things ${label.toLowerCase()}.`);
  }

  sentences.push("I'll learn the rest as we go.");
  return sentences.join(" ");
}
