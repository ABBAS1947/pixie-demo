"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { AlertCircle, ArrowLeft, BookOpen, Check, ChevronDown, CircleHelp, Flag, Lightbulb, Loader2, Pause, Play, Sparkles } from "lucide-react";
import Dialog from "@/components/Dialog";
import { getReviewConfig, getReviewHome, getReviewSession, prepareReview, sendReviewAction, updateReviewPreferences } from "@/lib/reviewApi";
import type { ReviewConfig, ReviewHome, ReviewLength, ReviewMode, ReviewSession, ReviewSessionItem } from "@/lib/reviewApi";

const modeCards: { id: ReviewMode; icon: string; description: string }[] = [
  { id: "card_quiz", icon: "✓", description: "Decide whether each statement is true or false." },
  { id: "recall", icon: "Aa", description: "Answer in a few words or one short sentence." },
  { id: "smart_mix", icon: "✦", description: "A thoughtful mix based on your current review needs." },
];

function requestId() { return crypto.randomUUID(); }
function titleCase(value: string) { return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase()); }
function resultTone(item: ReviewSessionItem) {
  if (item.result?.judgment === "correct") return "border-emerald-300 bg-emerald-50 text-emerald-950";
  if (item.result?.judgment === "partially_correct") return "border-amber-300 bg-amber-50 text-amber-950";
  if (item.result?.judgment === "incorrect") return "border-orange-300 bg-orange-50 text-orange-950";
  return "border-stone-300 bg-stone-50 text-stone-950";
}

function ActionButton({ children, onClick, disabled = false, kind = "primary", type = "button" }: { children: React.ReactNode; onClick?: () => void; disabled?: boolean; kind?: "primary" | "secondary" | "quiet" | "danger"; type?: "button" | "submit" }) {
  const styles = {
    primary: "bg-[var(--color-orange)] text-white shadow-[0_4px_0_#bd4800] hover:translate-y-px hover:shadow-[0_3px_0_#bd4800]",
    secondary: "border border-[#d7bea1] bg-[#fffaf2] text-[#421901] hover:bg-[#feebcc]",
    quiet: "text-[#704b32] hover:bg-[#f7eadb]",
    danger: "border border-orange-300 bg-white text-orange-800 hover:bg-orange-50",
  };
  return <button type={type} onClick={onClick} disabled={disabled} className={`min-h-12 rounded-2xl px-5 text-sm font-bold transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#fb6b07] disabled:cursor-not-allowed disabled:opacity-45 ${styles[kind]}`}>{children}</button>;
}

function EmptyState({ title, children }: { title: string; children: React.ReactNode }) {
  return <div className="mx-auto flex min-h-[55dvh] max-w-md flex-col items-center justify-center px-5 text-center"><div className="mb-5 grid h-14 w-14 place-items-center rounded-full bg-[#feebcc] text-2xl">✦</div><h1 className="text-2xl font-bold tracking-tight text-[#421901]">{title}</h1><div className="mt-3 text-[15px] leading-6 text-[#704b32]">{children}</div></div>;
}

function Setup({ config, home, onPrepared, onResume }: { config: ReviewConfig; home: ReviewHome; onPrepared: (session: ReviewSession) => void; onResume: (session: ReviewSession) => void }) {
  const [mode, setMode] = useState<ReviewMode>(config.defaults.mode);
  const [length, setLength] = useState<ReviewLength>(config.defaults.length);
  const [noteIds, setNoteIds] = useState<string[]>([]);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const toggleNote = (id: string) => setNoteIds((current) => current.includes(id) ? current.filter((value) => value !== id) : [...current, id]);
  async function begin() {
    setStarting(true); setError(null);
    try {
      // Consent is a persisted learner preference. The first preparation opts
      // in automatically; subsequent reviews never show an interruption.
      if (!config.preferences.external_processing_consent) await updateReviewPreferences({ external_processing_consent: true });
      onPrepared(await prepareReview({ request_id: requestId(), mode, length, note_ids: noteIds, concept_ids: [], selection_policy: "priority" }));
    } catch (err) { setError(err instanceof Error ? err.message : "Your review could not be prepared. Try again when you are ready."); }
    finally { setStarting(false); }
  }
  return <div className="review-shell">
    <header className="review-hero"><div><p className="review-kicker">Your review space</p><h1>Practice that meets you where you are.</h1><p>Choose a small, clear scope. Feedback stays here until you are ready to continue.</p></div><div className="review-orb" aria-hidden>✦</div></header>
    {home.resumable.length > 0 && <section className="review-section" aria-labelledby="resume-title"><div className="section-label"><span>Continue</span><h2 id="resume-title">Your saved reviews</h2></div><div className="resume-grid">{home.resumable.map((session) => <button key={session.id} onClick={() => onResume(session)} className="resume-card"><span className="status-dot"/><span><b>{session.status === "prepared" ? "Ready to start" : session.status === "preparing" ? "Preparing" : "Continue review"}</b><small>{session.progress.finished} of {session.actual_count || session.requested_count} items complete · {titleCase(session.mode)}</small></span><span aria-hidden>→</span></button>)}</div></section>}
    <section className="review-section" aria-labelledby="setup-title"><div className="section-label"><span>Set up</span><h2 id="setup-title">Make this review yours</h2></div><div className="review-setup">
      <fieldset><legend>1. Study material</legend><p className="field-help">{noteIds.length ? `${noteIds.length} selected` : "Use up to five recent notes, or choose exactly what to practise."}</p><div className="material-list">{home.materials.length ? home.materials.map((note) => <label key={note.id} className={`material-option ${noteIds.includes(note.id) ? "is-selected" : ""}`}><input type="checkbox" checked={noteIds.includes(note.id)} onChange={() => toggleNote(note.id)}/><span>{note.title || "Untitled note"}</span><Check size={16}/></label>) : <p className="field-help">Add study material before starting a review.</p>}</div></fieldset>
      <fieldset><legend>2. How would you like to practise?</legend><div className="mode-grid">{modeCards.map((choice) => <label key={choice.id} className={`mode-card ${mode === choice.id ? "is-selected" : ""}`}><input type="radio" name="mode" value={choice.id} checked={mode === choice.id} onChange={() => setMode(choice.id)}/><span className="mode-icon">{choice.icon}</span><b>{config.modes[choice.id]}</b><small>{choice.description}</small><span className="mode-check"><Check size={14}/></span></label>)}</div><button type="button" onClick={() => setMode("browse_cards")} className={`browse-link ${mode === "browse_cards" ? "is-selected" : ""}`}><BookOpen size={16}/><span><b>Browse cards</b><small>Reveal answers and reflect privately. This is practice, not a scored quiz.</small></span>{mode === "browse_cards" && <Check size={16}/>}</button></fieldset>
      <fieldset><legend>3. Choose a pace</legend><div className="length-grid">{(Object.keys(config.lengths) as ReviewLength[]).map((id) => { const option = config.lengths[id]; return <label key={id} className={`length-card ${length === id ? "is-selected" : ""}`}><input type="radio" name="length" value={id} checked={length === id} onChange={() => setLength(id)}/><b>{option.label}</b><span>{option.description}</span><small>Up to {option.cap} items</small></label>; })}</div></fieldset>
      <div className="review-rules"><div><Sparkles size={18}/><p><b>At your pace.</b> There is no timer. You can save and leave whenever you need.</p></div><div><AlertCircle size={18}/><p><b>Clear outcomes.</b> The actual item count and any XP adjustment are shown by the server before they apply.</p></div></div>
      {config.external_processing.requires_explicit_consent && <div className="consent-card consent-auto"><span className="consent-auto-mark">✓</span><span><b>Pixie uses your selected notes to prepare this review</b><small>{config.external_processing.payload} This preference is saved for future reviews.</small></span></div>}
      {error && <p className="form-error" role="alert">{error}</p>}
      <ActionButton onClick={begin} disabled={starting || !home.materials.length}>{starting ? <><Loader2 className="mr-2 inline animate-spin" size={16}/>Preparing your review…</> : "Prepare review"}</ActionButton>
    </div></section>
    {home.suggested_concepts.length > 0 && <section className="review-section suggestion"><div className="section-label"><span>Why this is suggested</span><h2>Ideas ready for another look</h2></div><p>{home.adaptation_basis}</p><div className="concept-pills">{home.suggested_concepts.slice(0, 8).map((concept) => <span key={concept.id}>{concept.label}<small>{titleCase(concept.reason)}</small></span>)}</div></section>}
  </div>;
}

function Preparation({ session, refresh, onStart, onBack }: { session: ReviewSession; refresh: () => void; onStart: () => void; onBack: () => void }) {
  const failed = session.status === "failed";
  if (failed) return <><EmptyState title="This review needs another try."><p>Pixie could not prepare this review. Choose whether to retry or return to setup.</p></EmptyState><Dialog open title="Review preparation needs attention" message={session.preparation?.last_error || "We could not prepare a clear set of questions from this material."} confirmLabel="Try again" cancelLabel="Back to setup" onConfirm={refresh} onCancel={onBack} /></>;
  return <EmptyState title={session.status === "prepared" ? "Your review is ready." : "Preparing your review…"}>{session.status === "prepared" ? <><p>{session.actual_count} carefully selected {session.actual_count === 1 ? "item is" : "items are"} ready. Read each correction at your own pace.</p>{session.limitations.map((item) => <p key={item} className="mt-3 rounded-xl bg-[#feebcc] p-3 text-sm">{item}</p>)}<div className="mt-6"><ActionButton onClick={onStart}>Start review</ActionButton></div></> : <><p>We are selecting clear, source-grounded questions. This page will update when they are ready.</p><div className="mt-6 flex justify-center"><Loader2 className="animate-spin text-[#fb6b07]"/></div><div className="mt-6"><ActionButton kind="secondary" onClick={refresh}>Check status</ActionButton></div></>}</EmptyState>;
}

function Feedback({ item, onAction, busy }: { item: ReviewSessionItem; onAction: (action: "retry_practice" | "report") => void; busy: boolean }) {
  const result = item.result;
  if (!result) return null;
  const label = result.judgment === "correct" ? "Correct" : result.judgment === "partially_correct" ? "Good start" : result.judgment === "incorrect" ? "Let’s revisit this" : result.kind === "practice" ? "Your reflection" : "Skipped";
  const latestPractice = item.retries[item.retries.length - 1];
  return <section className={`feedback-panel ${resultTone(item)}`} aria-live="polite"><div className="feedback-title"><span>{result.judgment === "correct" ? "✓" : "✦"}</span><h3>{label}</h3></div>{result.response && <p className="feedback-response">Your answer: <b>{result.response}</b></p>}{result.feedback && <p>{result.feedback}</p>}{item.explanation && <p>{item.explanation}</p>}{latestPractice?.feedback && <p className="practice-note"><b>Practice attempt:</b> {latestPractice.feedback}</p>}{item.source.quote && <details><summary>Show source</summary><blockquote>{item.source.quote}<cite>{item.source.title}</cite></blockquote></details>}<div className="feedback-actions">{item.retries.length < 3 && result.kind === "assessment" && <ActionButton kind="secondary" onClick={() => onAction("retry_practice")} disabled={busy}>Try again for practice</ActionButton>}<ActionButton kind="quiet" onClick={() => onAction("report")} disabled={busy}><Flag className="mr-1 inline" size={14}/>Report a problem</ActionButton></div></section>;
}

function Question({ session, onUpdate, onExit }: { session: ReviewSession; onUpdate: (session: ReviewSession) => void; onExit: () => void }) {
  const item = session.items[session.cursor];
  const [draft, setDraft] = useState(""); const [busy, setBusy] = useState(false); const [practicing, setPracticing] = useState(false); const [error, setError] = useState<string | null>(null); const [exitOpen, setExitOpen] = useState(false); const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { setDraft(""); setPracticing(false); setError(null); heading.current?.focus(); }, [item?.id]);
  if (!item) return <EmptyState title="Nothing left to review."><ActionButton onClick={onExit}>Back to Review</ActionButton></EmptyState>;
  const dispatch = async (action: Parameters<typeof sendReviewAction>[1]["action"], extra: Record<string, string> = {}) => { setBusy(true); setError(null); try { const next = await sendReviewAction(session.id, { request_id: requestId(), state_version: session.state_version, action, item_id: item.id, ...extra }); onUpdate(next); return next; } catch (err) { setError(err instanceof Error ? err.message : "We could not save that. Your answer is still here—try again."); } finally { setBusy(false); } };
  const next = () => dispatch(session.cursor + 1 < session.items.length ? "next" : "complete");
  const submit = async (event: FormEvent) => { event.preventDefault(); if (draft.trim()) { await dispatch(practicing ? "retry_practice" : "answer", { response: draft.trim() }); setPracticing(false); } };
  const rendered = item.result && !practicing ? <Feedback item={item} busy={busy} onAction={(action) => action === "retry_practice" ? (setDraft(""), setPracticing(true)) : dispatch("report", { category: "other", detail: "Learner reported this review item." })}/> : item.format === "reveal_card" ? <RevealCard item={item} busy={busy} onAction={dispatch}/> : <form onSubmit={submit} className="question-response"><fieldset disabled={busy}><legend className="sr-only">Your answer</legend>{practicing && <p className="practice-note">This is practice. It will not replace your first result.</p>}{item.format === "short_answer" ? <><label htmlFor="short-answer">Your answer</label><textarea id="short-answer" value={draft} onChange={(event) => setDraft(event.target.value)} rows={4} placeholder="Write a few words or one short sentence."/><p>Short and clear is enough.</p></> : <div className="choice-list">{item.options.map((option) => <label key={option} className={`choice ${draft === option ? "is-selected" : ""}`}><input type="radio" name="answer" value={option} checked={draft === option} onChange={() => setDraft(option)}/><span>{option}</span></label>)}</div>}</fieldset><ActionButton type="submit" disabled={!draft.trim() || busy}>{busy ? <><Loader2 className="mr-2 inline animate-spin" size={16}/>Checking your answer…</> : practicing ? "Save practice attempt" : "Check answer"}</ActionButton><div className="question-secondary">{!practicing && <ActionButton kind="quiet" onClick={() => dispatch("help")} disabled={busy}><CircleHelp className="mr-1 inline" size={15}/>I need a hint</ActionButton>}{!practicing && <ActionButton kind="quiet" onClick={() => dispatch("skip")} disabled={busy}>Skip this item</ActionButton>}</div></form>;
  return <div className="review-task"><header className="task-header"><button onClick={() => setExitOpen(true)} className="back-button"><ArrowLeft size={18}/>Leave review</button><div className="task-count">{session.cursor + 1} of {session.actual_count}<span>{session.progress.finished} answered</span></div><button onClick={() => dispatch("pause")} className="icon-button" aria-label="Save and pause review"><Pause size={17}/></button></header><div className="task-progress" aria-label={`${session.progress.finished} of ${session.actual_count} complete`}><span style={{ width: `${session.actual_count ? session.progress.finished / session.actual_count * 100 : 0}%` }}/></div><main className="question-card"><div className="question-meta"><span>{item.format === "true_false" ? "Card quiz" : item.format === "short_answer" ? "Recall" : item.format === "reveal_card" ? "Browse cards" : "Choice question"}</span><span>{item.source.title}</span></div><h1 ref={heading} tabIndex={-1}>{item.question}</h1>{item.hint && !item.result && <aside className="hint"><Lightbulb size={17}/>{item.hint}</aside>}{item.clarification && <aside className="clarification"><AlertCircle size={17}/>{item.clarification}</aside>}{rendered}{item.result && <div className="continue-row"><ActionButton onClick={next} disabled={busy}>{session.cursor + 1 === session.items.length ? "See results" : "Continue"}</ActionButton></div>}{error && <p role="alert" className="form-error">{error}</p>}</main>{exitOpen && <Dialog open role="alertdialog" title="Leave this review?" message={<>{session.abandon_preview.delta < 0 && <p className="xp-preview">Ending now would adjust XP by {session.abandon_preview.delta}. This is the server-calculated amount.</p>}<p>Your progress is saved. Keep reviewing if you want to finish, or end this session permanently.</p></>} confirmLabel="End review" cancelLabel="Keep reviewing" destructive onConfirm={async () => { const ended = await dispatch("abandon", { reason: "voluntary" }); if (ended) onExit(); }} onCancel={() => setExitOpen(false)} />}</div>;
}

function RevealCard({ item, busy, onAction }: { item: ReviewSessionItem; busy: boolean; onAction: (action: "reveal" | "self_rate", extra?: Record<string, string>) => void }) { return <div className="reveal-card">{!item.revealed ? <ActionButton onClick={() => onAction("reveal")} disabled={busy}>Reveal answer</ActionButton> : <><p className="reveal-answer">{item.answer}</p>{item.explanation && <p>{item.explanation}</p>}<p className="reflection-prompt">How did that feel?</p><div className="rating-row"><ActionButton kind="secondary" onClick={() => onAction("self_rate", { rating: "need_practice" })} disabled={busy}>Need practice</ActionButton><ActionButton kind="secondary" onClick={() => onAction("self_rate", { rating: "almost" })} disabled={busy}>Almost</ActionButton><ActionButton onClick={() => onAction("self_rate", { rating: "knew_it" })} disabled={busy}>I knew it</ActionButton></div></>}</div>; }

function Results({ session, onBack, onTeach }: { session: ReviewSession; onBack: () => void; onTeach: () => void }) { const score = session.score === null ? null : Math.round(session.score * 100); const headline = score === null ? "You completed your practice." : score >= 80 ? "Excellent recall." : score >= 50 ? "Good progress—let’s revisit a few ideas." : "You completed your review. Here is what to practise next."; const needs = session.items.filter((item) => item.result?.correct === false); return <div className="review-results"><header><p className="review-kicker">Review complete</p><h1>{headline}</h1><p>{session.progress.correct} of {session.progress.assessed} first attempts correct{score !== null ? ` · ${score}%` : ""}</p>{session.xp_receipt && <span className="xp-receipt">{session.xp_receipt.delta >= 0 ? "+" : ""}{session.xp_receipt.delta} XP</span>}</header><section className="results-card"><h2>Your review</h2>{session.items.map((item, index) => <details key={item.id} className="result-row"><summary><span>{item.result?.correct ? "✓" : item.result?.kind === "practice" ? "•" : "→"}</span><b>{index + 1}. {item.question}</b><ChevronDown size={17}/></summary><div><p>{item.result?.response && <>Your answer: <b>{item.result.response}</b></>}</p>{item.answer && <p>Answer: <b>{item.answer}</b></p>}{item.explanation && <p>{item.explanation}</p>}{item.source.quote && <blockquote>{item.source.quote}<cite>{item.source.title}</cite></blockquote>}</div></details>)}</section>{needs.length > 0 && <section className="next-step"><Sparkles size={20}/><div><h2>One useful next step</h2><p>Continue learning these {needs.length === 1 ? "idea" : "ideas"} in Chat, where Pixie can explain them with you.</p></div>{session.next_step && <ActionButton onClick={onTeach}>Teach me this</ActionButton>}</section>}<div className="results-actions"><ActionButton kind="secondary" onClick={onBack}>Back to Review</ActionButton></div></div>; }

export default function ReviewFlow({ initialSessionId, onSessionChange }: { initialSessionId?: string | null; onSessionChange: (id: string | null, summary?: boolean) => void }) {
  const [config, setConfig] = useState<ReviewConfig | null>(null); const [home, setHome] = useState<ReviewHome | null>(null); const [session, setSession] = useState<ReviewSession | null>(null); const [loading, setLoading] = useState(true); const [error, setError] = useState<string | null>(null);
  const loadHome = async () => { const [nextConfig, nextHome] = await Promise.all([getReviewConfig(), getReviewHome()]); setConfig(nextConfig); setHome(nextHome); };
  useEffect(() => { (async () => { setLoading(true); try { if (initialSessionId) setSession(await getReviewSession(initialSessionId)); else await loadHome(); } catch (err) { setError(err instanceof Error ? err.message : "Review could not be loaded."); } finally { setLoading(false); } })(); }, [initialSessionId]);
  // Preparation is asynchronous. Poll the durable session instead of leaving
  // the learner on an optimistic spinner; failed jobs become actionable too.
  useEffect(() => {
    if (!session || session.status !== "preparing") return;
    let stopped = false;
    const poll = async () => {
      try {
        const latest = await getReviewSession(session.id);
        if (!stopped) setSession(latest);
      } catch {
        // A transient polling failure must not erase the saved session or
        // present it as a failed review. The next interval reconciles it.
      }
    };
    const timer = window.setInterval(poll, 1500);
    return () => { stopped = true; window.clearInterval(timer); };
  }, [session?.id, session?.status]);
  const update = (next: ReviewSession) => { setSession(next); if (next.status === "completed") onSessionChange(next.id, true); };
  const leave = async () => { setSession(null); onSessionChange(null); setLoading(true); setError(null); try { await loadHome(); } catch (err) { setError(err instanceof Error ? err.message : "Review could not be loaded."); } finally { setLoading(false); } };
  if (loading) return <EmptyState title="Opening Review"><Loader2 className="mx-auto animate-spin text-[#fb6b07]"/><p className="mt-4">Getting your saved practice ready.</p></EmptyState>;
  if (error) return <EmptyState title="Review is unavailable"><p>{error}</p><div className="mt-6"><ActionButton onClick={() => window.location.reload()}>Try again</ActionButton></div></EmptyState>;
  if (!session && config && home) return <Setup config={config} home={home} onPrepared={(next) => { setSession(next); onSessionChange(next.id); }} onResume={(next) => { setSession(next); onSessionChange(next.id); }}/>;
  if (!session) return null;
  if (session.status === "completed") return <Results session={session} onBack={leave} onTeach={() => { window.location.assign(`/app/chat?learn=1&review=${session.id}`); }}/>;
  if (["preparing", "prepared", "failed"].includes(session.status)) return <Preparation session={session} refresh={async () => { if (session.status === "failed") { await updateReviewPreferences({ external_processing_consent: true }); update(await sendReviewAction(session.id, { request_id: requestId(), state_version: session.state_version, action: "retry_preparation" })); } else update(await getReviewSession(session.id)); }} onStart={async () => update(await sendReviewAction(session.id, { request_id: requestId(), state_version: session.state_version, action: "start" }))} onBack={leave}/>;
  if (session.status === "paused") return <EmptyState title="Your review is saved."><p>Everything is still here, exactly where you left it.</p><div className="mt-6 flex justify-center gap-3"><ActionButton kind="secondary" onClick={leave}>Back to Review</ActionButton><ActionButton onClick={async () => update(await sendReviewAction(session.id, { request_id: requestId(), state_version: session.state_version, action: "resume" }))}><Play className="mr-2 inline" size={16}/>Resume</ActionButton></div></EmptyState>;
  return <Question session={session} onUpdate={update} onExit={leave}/>;
}
