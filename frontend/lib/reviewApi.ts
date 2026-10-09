import { apiFetch } from "./apiRequest";

import { API_URL } from "./apiOrigin";
const reviewErrorCopy: Record<string, string> = {
  external_processing_consent_required: "Allow note processing in Review setup to prepare new source-grounded questions.",
  source_changed: "This material changed since the review was prepared. Start a fresh review to use the latest notes.",
  stale_session: "This review changed in another tab. Your saved progress has been restored—please choose your next action again.",
  action_not_available: "That action is no longer available for this review item. Your saved state has not changed.",
  no_testable_content: "Pixie could not find clear, testable material in the selected notes.",
  no_valid_questions: "Pixie could not prepare clear questions from this material. Try another note or mode.",
  preparation_service_unavailable: "Preparation is temporarily unavailable. Your review is saved; try again shortly.",
  grading_service_unavailable: "We could not assess that answer right now. It was not recorded as wrong.",
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await apiFetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!response.ok) {
    let message = response.statusText;
    try {
      const body = await response.json();
      const detail = body.detail;
      if (typeof detail === "string") message = detail;
      else if (Array.isArray(detail)) message = detail[0]?.msg ?? message;
      else if (detail?.code) message = reviewErrorCopy[detail.code] ?? "This review action could not be completed. Please try again.";
    } catch { /* Keep the HTTP status message. */ }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export type ReviewMode = "card_quiz" | "recall" | "smart_mix" | "browse_cards";
export type ReviewLength = "spark" | "focus" | "deep_dive";
export type ReviewAction = "start" | "answer" | "help" | "reveal" | "self_rate" | "retry_practice" | "skip" | "next" | "pause" | "resume" | "abandon" | "complete" | "retry_preparation" | "report";

export interface ReviewPreferences { penalties_enabled: boolean; external_processing_consent: boolean; reduced_motion: boolean; reduced_text: boolean; }
export interface ReviewConfig {
  policy_version: string;
  modes: Record<ReviewMode, string>;
  lengths: Record<ReviewLength, { label: string; description: string; cap: number; max_xp: number; loss_cap: number }>;
  defaults: { mode: ReviewMode; length: ReviewLength; selection_policy: "priority" | "shuffle" };
  preferences: ReviewPreferences;
  external_processing: { provider: string; payload: string; requires_explicit_consent: boolean };
  xp_rules: { poor_score_threshold: number; exemptions: string[]; settlement: string; balance_floor: number };
}
export interface ReviewItemResult { kind: "assessment" | "practice" | "skipped"; score: number | null; correct: boolean | null; independence: "independent" | "supported" | "unknown"; judgment?: "correct" | "partially_correct" | "incorrect" | "unassessable"; feedback?: string; response?: string; rating?: "knew_it" | "almost" | "need_practice"; }
export interface ReviewSessionItem { id: string; position: number; concept_id: string; format: "mcq" | "true_false" | "short_answer" | "reveal_card"; question: string; options: string[]; source: { note_id: string; title: string; hash: string; quote?: string }; supported: boolean; revealed: boolean; result: ReviewItemResult | null; retries: ReviewItemResult[]; clarification: string | null; hint?: string; answer?: string; explanation?: string; rubric?: string; }
export interface ReviewSession {
  id: string; status: "preparing" | "prepared" | "active" | "paused" | "completed" | "abandoned" | "failed"; state_version: number; mode: ReviewMode; length: ReviewLength; cursor: number; requested_count: number; actual_count: number; limitations: string[];
  progress: { finished: number; total: number; assessed: number; independent: number; correct: number; skipped: number; practice: number }; score: number | null; items: ReviewSessionItem[]; available_actions: ReviewAction[];
  xp_policy: { max_xp: number; loss_cap: number; penalties_enabled: boolean }; abandon_preview: { requested_delta: number; delta: number; reason: string }; xp_receipt: { delta: number; requested_delta: number; reason: string; balance_after: number } | null;
  preparation: { status: string; attempts: number; last_error: string | null } | null; next_step: { surface: "chat_learn"; concept_ids: string[] } | null;
}
export interface ReviewHome { preferences: ReviewPreferences; resumable: ReviewSession[]; materials: { id: string; title: string }[]; suggested_concepts: { id: string; label: string; note_id: string; reason: "new" | "due" | "needs_practice" | "reinforcement"; independent_signal_count: number }[]; adaptation_basis: string; }

export const getReviewConfig = () => request<ReviewConfig>("/review/config");
export const getReviewHome = () => request<ReviewHome>("/review/home");
export const getReviewSession = (id: string) => request<ReviewSession>(`/review/sessions/${id}`);
export const updateReviewPreferences = (value: Partial<ReviewPreferences>) => request<ReviewPreferences>("/review/preferences", { method: "PUT", body: JSON.stringify(value) });
export const prepareReview = (value: { request_id: string; mode: ReviewMode; length: ReviewLength; note_ids: string[]; concept_ids: string[]; selection_policy: "priority" | "shuffle" }) => request<ReviewSession>("/review/sessions", { method: "POST", body: JSON.stringify(value) });
export const sendReviewAction = (id: string, value: { request_id: string; state_version: number; action: ReviewAction; item_id?: string; response?: string; rating?: "knew_it" | "almost" | "need_practice"; reason?: "voluntary" | "unassessable" | "service_failure"; category?: "incorrect_answer" | "ambiguous" | "irrelevant" | "accessibility" | "other"; detail?: string }) => request<ReviewSession>(`/review/sessions/${id}/actions`, { method: "POST", body: JSON.stringify(value) });
