// Shared types mirroring the backend contract (app/models + app/api).

export type Tone = "playful_sarcastic" | "calm_steady" | "blunt";

export interface User {
  user_id: string;
  name: string;
  grade_level: string | null;
  is_teacher?: boolean;
  honcho_peer_id: string;
  vault_path: string;
  created?: boolean;
}

export interface OnboardingInput {
  name: string;
  grade_level: string;
  tone: Tone;
  resource_constraints: string | null;
  timezone?: string;
}

export interface SubjectInput {
  name: string;
  hardest: boolean;
}

// The confirmed 10-beat grilling interview, committed in one shot after the
// pixie's recap ("did I get you right?"). Soft answers (struggles, learning
// style, schedule, goals) go to Honcho on the backend, not the relational DB.
export interface OnboardingCommitInput {
  name: string | null;
  grade_level: string | null;
  tone: Tone | null;
  resource_constraints: string | null;
  subjects: SubjectInput[];
  struggles: string | null;
  learning_style: string | null;
  schedule: string | null;
  goals: string | null;
}

export interface ChatMessage {
  id: string;
  role: "user" | "pixie";
  content: string;
  saved?: boolean;
}

export interface Note {
  id: string;
  title: string;
  excerpt: string;
  content?: string;
  tags: string[];
  createdAt: string;
  updatedAt?: string;
  backlinks?: string[];
  justSaved?: boolean;
  folderId?: string | null;
}

export type DeadlineKind = "assignment" | "exam" | "project";
export type DeadlineStatus = "upcoming" | "completed" | "overdue";
export type DeadlineSource = "manual" | "file_upload" | "conversation" | "google_sync";
export type CalendarView = "month" | "week" | "day" | "list";

export interface Deadline {
  id: string;
  title: string;
  due_at: string; // ISO timestamp (backend contract, snake_case)
  kind: DeadlineKind;
  course_id?: string | null;
  course?: { name: string } | null;
  status: DeadlineStatus;
  source: DeadlineSource;
  confirmed: boolean; // false for auto-extracted / google-imported
  pace_plan?: string | null;
  google_event_id?: string | null;
  synced_to_google: boolean;
}

export interface GoogleConnectionDetails {
  email: string | null;
  calendar_id: string;
  sync_enabled: boolean;
  last_sync_at: string | null;
}

export interface Flashcard {
  id: string;
  question: string;
  answer: string;
}

export interface Project {
  id: string;
  title: string;
  milestones: { label: string; done: boolean }[];
  deadlineId?: string;
}

export type Subject = {
  id: string;
  name: string;
  color: string; // solid hex tag tint
};
