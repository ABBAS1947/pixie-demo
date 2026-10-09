"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { commitOnboarding, fetchMe } from "@/lib/api";
import { supabase } from "@/lib/supabase";
import type { Tone } from "@/lib/types";
import {
  EMPTY_ANSWERS,
  buildCommitPayload,
  looksLikeGrade,
  type Answers,
} from "@/lib/onboarding";
import { QUESTIONS, type QuestionConfig } from "./question-config";
import ProgressBar from "./components/ProgressBar";
import TextQuestion from "./components/TextQuestion";
import ChoiceCards from "./components/ChoiceCards";
import ChipGrid from "./components/ChipGrid";
import ToneCards from "./components/ToneCards";
import WelcomeScreen from "./components/WelcomeScreen";
import styles from "./onboarding.module.css";

const EMPTY_VALUE: Record<QuestionConfig["type"], unknown> = {
  text: "",
  choice: null,
  chips: [],
  tone: null,
};

// Wizard-only onboarding. Auth moved to /login; a user only
// reaches this page with a session. The backend enforces the token on every API call.
export default function Onboarding() {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  // Route guard: onboarding is only for accounts that haven't completed
  // their profile yet. No session -> login; already onboarded -> app.
  useEffect(() => {
    (async () => {
      const { data } = await supabase.auth.getSession();
      if (!data.session?.access_token) {
        router.replace("/login");
        return;
      }
      try {
        const me = await fetchMe();
        if (me.grade_level) {
          router.replace("/app");
          return;
        }
      } catch {
        // backend hiccup — let the wizard render; API calls surface errors
      }
      setReady(true);
    })();
  }, [router]);

  const [idx, setIdx] = useState(0);
  const [answers, setAnswers] = useState<Answers>(EMPTY_ANSWERS);
  const [error, setError] = useState<string | null>(null);
  const [otherError, setOtherError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const autoAdvanceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [customValues, setCustomValues] = useState<Record<string, string>>({});

  const isSummary = idx >= QUESTIONS.length;

  function clearAutoAdvance() {
    if (autoAdvanceRef.current) {
      clearTimeout(autoAdvanceRef.current);
      autoAdvanceRef.current = null;
    }
  }

  function goNext() {
    clearAutoAdvance();
    setIdx((i) => Math.min(i + 1, QUESTIONS.length));
  }

  function goBack() {
    clearAutoAdvance();
    if (isSummary) {
      setIdx(QUESTIONS.length - 1);
      return;
    }
    setIdx((i) => Math.max(0, i - 1));
  }

  /** Single-select (choice/tone): store + cancelable 350ms auto-advance. */
  function handlePick(q: QuestionConfig, v: string) {
    clearAutoAdvance();
    setAnswers((a) => ({ ...a, [q.answerKey]: v }) as Answers);
    autoAdvanceRef.current = setTimeout(() => {
      autoAdvanceRef.current = null;
      goNext();
    }, 350);
  }

  function handleSkip() {
    const q = QUESTIONS[idx];
    if (!q) return;
    if (q.id === "grade") return;
    clearAutoAdvance();
    setAnswers((a) => ({ ...a, [q.answerKey]: EMPTY_VALUE[q.type] }) as Answers);
    if (customValues[q.id]) {
      setCustomValues((values) => ({ ...values, [q.id]: "" }));
    }
    goNext();
  }

  function handleContinue() {
    const q = QUESTIONS[idx];
    if (!q) return;
    if (q.type === "text" && !(answers[q.answerKey as keyof Answers] as string).trim()) return;
    if (q.type === "chips" && (answers[q.answerKey as keyof Answers] as string[]).length === 0) return;
    goNext();
  }

  function handleChipToggle(q: QuestionConfig, v: string) {
    setAnswers((a) => {
      const cur = [...((a[q.answerKey as keyof Answers] as string[]) ?? [])];
      const next = cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v];
      return { ...a, [q.answerKey]: next } as Answers;
    });
  }

  /** ChipGrid "Other" — the typed value is a normal entry in the array. */
  function handleChipOther(q: QuestionConfig, text: string) {
    const prev = customValues[q.id] ?? "";
    setAnswers((a) => {
      const cur = [...((a[q.answerKey as keyof Answers] as string[]) ?? [])];
      if (prev && cur.includes(prev)) cur.splice(cur.indexOf(prev), 1);
      const t = text.trim();
      if (t) cur.push(t);
      return { ...a, [q.answerKey]: cur } as Answers;
    });
    setCustomValues((values) => ({ ...values, [q.id]: text.trim() }));
  }

  /** Grade "Other" — the typed value must pass the grade rule. */
  function handleGradeOther(text: string) {
    const t = text.trim();
    if (!t) return;
    if (looksLikeGrade(t)) {
      setOtherError(null);
      handlePick(QUESTIONS[1], t);
    } else {
      setOtherError(
        "Try a grade like 9th or College.",
      );
    }
  }

  async function handleConfirm() {
    if (busy || !answers.grade) return;
    setBusy(true);
    setError(null);
    try {
      await commitOnboarding(buildCommitPayload(answers));
      router.replace("/app");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save your profile");
      setBusy(false);
    }
  }

  const q = isSummary ? null : QUESTIONS[idx];

  function renderQuestion(question: QuestionConfig) {
    const key = question.answerKey as keyof Answers;
    switch (question.type) {
      case "text":
        return (
          <TextQuestion
            value={answers[key] as string}
            onChange={(v) => setAnswers((a) => ({ ...a, [key]: v }) as Answers)}
            placeholder={question.placeholder}
            onContinue={goNext}
            autoFocus
          />
        );
      case "choice":
        return (
          <ChoiceCards
            options={question.options ?? []}
            value={answers[key] as string | null}
            onPick={(v) => handlePick(question, v)}
            onOtherSubmit={question.id === "grade" ? handleGradeOther : undefined}
            otherError={question.id === "grade" ? otherError : null}
            onOtherDismiss={() => setOtherError(null)}
          />
        );
      case "chips":
        return (
          <ChipGrid
            options={question.options ?? []}
            selected={answers[key] as string[]}
            onToggle={(v) => handleChipToggle(question, v)}
            customValue={customValues[question.id] ?? ""}
            onCustomChange={(t) => handleChipOther(question, t)}
          />
        );
      case "tone":
        return (
          <ToneCards
            value={answers[key] as Tone | null}
            onPick={(v) => handlePick(question, v)}
          />
        );
    }
  }

  if (!ready) return null;

  return (
    <main className={styles.page}>
      <div className={styles.shell}>
        <header className={styles.header}>
          <div className={styles.headerTop}>
            {idx > 0 ? (
              <button type="button" onClick={goBack} aria-label="Back" className={styles.back}>
                <ArrowLeft size={22} aria-hidden="true" />
              </button>
            ) : <span className={styles.backSpace} aria-hidden="true" />}
            {!isSummary && <span className={styles.stepCount}>{`${idx + 1} of ${QUESTIONS.length}`}</span>}
          </div>
          {!isSummary && <ProgressBar total={QUESTIONS.length} current={idx} />}
        </header>

        <section className={styles.content} aria-live="polite">
          {isSummary ? (
            <WelcomeScreen answers={answers} onContinue={handleConfirm} busy={busy} error={error} />
          ) : q ? (
            <div className={styles.questionPanel} key={q.id}>
              <h1 className={styles.title}>{q.question}</h1>
              <div className={styles.answerArea}>{renderQuestion(q)}</div>
            </div>
          ) : null}
        </section>

        {!isSummary && q && (
          <footer className={styles.footer}>
            {q.id !== "grade" ? (
              <button type="button" onClick={handleSkip} className={styles.skip}>Skip</button>
            ) : <span />}
            {(q.type === "text" || q.type === "chips") && (
              <button type="button" onClick={handleContinue}
                disabled={q.type === "text"
                  ? !(answers[q.answerKey as keyof Answers] as string).trim()
                  : (answers[q.answerKey as keyof Answers] as string[]).length === 0}
                className={styles.primary}>
                Continue
              </button>
            )}
          </footer>
        )}
      </div>
    </main>
  );
}
