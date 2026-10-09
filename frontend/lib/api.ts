// API client — talks to the FastAPI backend. Never touches Honcho/DeepSeek/DB
// directly; the backend is the only component with access to those.

import { apiFetch } from "./apiRequest";
import type { Deadline, GoogleConnectionDetails, Note, OnboardingCommitInput, OnboardingInput, User } from "./types";

// The backend serves the static export same-origin, so the API base must
// follow the page's own origin at runtime. A hardcoded localhost here breaks
// ngrok/phone access: the phone's 127.0.0.1 is the phone itself.
import { API_URL } from "./apiOrigin";



async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body.detail) {
        if (typeof body.detail === "string") {
          detail = body.detail;
        } else if (Array.isArray(body.detail) && body.detail.length > 0) {
          // FastAPI 422 validation errors arrive as an array of objects.
          // Surface the first human-readable message, not the raw JSON.
          const msg = (body.detail[0] as { msg?: string })?.msg;
          detail = msg ? msg.replace(/^Value error,?\s*/i, "") : res.statusText;
        } else {
          detail = JSON.stringify(body.detail);
        }
      }
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

function mapNote(n: Record<string, unknown>): Note {
  return {
    id: n.id as string,
    title: n.title as string,
    excerpt: (n.excerpt as string) ?? "",
    content: n.content as string | undefined,
    tags: (n.tags as string[]) ?? [],
    createdAt: n.created_at as string,
    updatedAt: n.updated_at as string | undefined,
    folderId: (n.folder_id as string | null) ?? null,
  };
}

export async function fetchMe(): Promise<User> {
  const res = await apiFetch(`${API_URL}/users/me`, { headers: {} });
  return handle(res);
}

export interface PrivacyStatement {
  version: number;
  stored: string[];
  location: string;
  viewers: string[];
  commitments: string[];
}

export async function fetchPrivacyStatement(): Promise<PrivacyStatement> {
  const res = await apiFetch(`${API_URL}/privacy/statement`);
  return handle(res);
}

/* ── Teacher dashboard ────────────────────────────────────────────── */

export interface TeacherStudentRow {
  user_id: string;
  name: string;
  grade_level: string | null;
  lessons: number;
  concepts: number;
  avg_mastery: number | null;
  weak_concepts: { concept: string; p_known: number }[];
  advances: number;
  probes: number;
  escalations: number;
  last_active: string | null;
  recent_mood: string | null;
  week_turns: number;
  week_quizzes: number;
  weekly_target: number;
  on_track: boolean;
}

export interface SchoolStudentSummary {
  enrollment_id: string; school_id: string; name: string;
  mastery: { code: string; mastery: number; attempts: number }[];
  avg_mastery: number | null; completed_practice: number; independent_correct: number; updated_at: string;
}
export interface SchoolStudentRecord {
  enrollment_id: string; school_id: string; updated_at: string;
  projection: { display_name: string; skills: SchoolStudentSummary["mastery"];
    results: { assessment_id: string; score: number; assessed_at: string }[];
    completed_practice: number; independent_correct: number; suggested_skill_codes: string[] };
}
export async function fetchTeacherOverview(): Promise<{ teacher: string; students: SchoolStudentSummary[] }> {
  const res = await apiFetch(`${API_URL}/teacher/overview`, { headers: {} });
  return handle(res);
}

export async function fetchTeacherStudent(userId: string): Promise<SchoolStudentRecord> {
  const res = await apiFetch(`${API_URL}/teacher/students/${userId}`, { headers: {} });
  return handle(res);
}

export async function updateOnboarding(input: OnboardingInput): Promise<{ updated: boolean }> {
  const res = await apiFetch(`${API_URL}/users/me`, {
    method: "PUT",
    headers: { "Content-Type": "application/json",  },
    body: JSON.stringify(input),
  });
  return handle(res);
}

export async function commitOnboarding(
  input: OnboardingCommitInput,
): Promise<{ committed: boolean; courses_created: number }> {
  const res = await apiFetch(`${API_URL}/onboarding/commit`, {
    method: "POST",
    headers: { "Content-Type": "application/json",  },
    body: JSON.stringify(input),
  });
  return handle(res);
}

export async function listNotes(limit = 100): Promise<Note[]> {
  const safeLimit = Math.max(1, Math.min(100, Math.floor(limit)));
  const res = await apiFetch(`${API_URL}/notes?limit=${safeLimit}`, { headers: {} });
  return (await handle<Record<string, unknown>[]>(res)).map(mapNote);
}

export interface QuickNoteLine {
  id: string;
  text: string;
  checked: boolean;
}

export interface QuickNote {
  body: string;
  checklist: QuickNoteLine[];
  revision: number;
  updated_at: string | null;
}

export async function getQuickNote(): Promise<QuickNote> {
  const res = await apiFetch(`${API_URL}/quick-note`);
  return handle<QuickNote>(res);
}

export async function saveQuickNote(input: Pick<QuickNote, "body" | "checklist" | "revision">): Promise<QuickNote> {
  const res = await apiFetch(`${API_URL}/quick-note`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return handle<QuickNote>(res);
}

export async function getNote(id: string): Promise<Note> {
  const res = await apiFetch(`${API_URL}/notes/${encodeURIComponent(id)}`, { headers: {} });
  return mapNote(await handle<Record<string, unknown>>(res));
}

export async function searchNotes(q: string): Promise<Note[]> {
  const res = await apiFetch(`${API_URL}/notes/search?q=${encodeURIComponent(q)}`, { headers: {} });
  return (await handle<Record<string, unknown>[]>(res)).map(mapNote);
}

export async function createNote(input: { title: string; content: string; tags?: string; folder_id?: string | null }): Promise<Note> {
  const res = await apiFetch(`${API_URL}/notes`, {
    method: "POST",
    headers: { "Content-Type": "application/json",  },
    body: JSON.stringify(input),
  });
  return mapNote(await handle<Record<string, unknown>>(res));
}

export async function updateNote(
  id: string,
  input: { title?: string; content?: string; tags?: string; folder_id?: string | null },
): Promise<Note> {
  const res = await apiFetch(`${API_URL}/notes/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json",  },
    body: JSON.stringify(input),
  });
  return mapNote(await handle<Record<string, unknown>>(res));
}

export interface NoteFolderDoc { id: string; name: string; color: string; created_at: string; note_count?: number; file_count?: number }

export async function listNoteFolders(): Promise<NoteFolderDoc[]> {
  const res = await apiFetch(`${API_URL}/notes/folders`, { headers: {} });
  return handle<NoteFolderDoc[]>(res);
}

export async function createNoteFolder(name: string): Promise<NoteFolderDoc> {
  const res = await apiFetch(`${API_URL}/notes/folders`, { method: "POST", headers: { "Content-Type": "application/json",  }, body: JSON.stringify({ name }) });
  return handle<NoteFolderDoc>(res);
}

export async function deleteNoteFolder(id: string): Promise<void> {
  const res = await apiFetch(`${API_URL}/notes/folders/${id}`, { method: "DELETE", headers: {} });
  if (!res.ok) throw new Error("That folder could not be removed.");
}

export async function deleteNote(id: string): Promise<void> {
  const res = await apiFetch(`${API_URL}/notes/${id}`, { method: "DELETE", headers: {} });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
}

// ── Calendar (MASTER-CALENDAR backend, guide §6.5) ─────────────────────────

export async function listDeadlines(start?: string, end?: string): Promise<Deadline[]> {
  const params = new URLSearchParams();
  if (start) params.set("start", start);
  if (end) params.set("end", end);
  const qs = params.toString();
  const res = await apiFetch(`${API_URL}/calendar/deadlines${qs ? `?${qs}` : ""}`, {
    headers: {},
  });
  const data = await handle<{ deadlines: Deadline[] }>(res);
  return data.deadlines;
}

export async function createDeadline(input: {
  title: string;
  due_at: string;
  kind: string;
  course_id?: string | null;
  pace_plan?: string | null;
  confirmed?: boolean;
}): Promise<Deadline> {
  const res = await apiFetch(`${API_URL}/calendar/deadlines`, {
    method: "POST",
    headers: { "Content-Type": "application/json",  },
    body: JSON.stringify(input),
  });
  return handle<Deadline>(res);
}

export async function updateDeadline(
  id: string,
  input: Partial<{
    title: string;
    due_at: string;
    kind: string;
    course_id: string | null;
    pace_plan: string | null;
    confirmed: boolean;
    status: string;
  }>,
): Promise<Deadline> {
  const res = await apiFetch(`${API_URL}/calendar/deadlines/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json",  },
    body: JSON.stringify(input),
  });
  return handle<Deadline>(res);
}

export async function deleteDeadline(id: string): Promise<void> {
  const res = await apiFetch(`${API_URL}/calendar/deadlines/${id}`, {
    method: "DELETE",
    headers: {},
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const b = await res.json();
      if (b.detail) detail = typeof b.detail === "string" ? b.detail : JSON.stringify(b.detail);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
}

export async function googleStatus(): Promise<{
  connected: boolean;
  details: GoogleConnectionDetails | null;
}> {
  const res = await apiFetch(`${API_URL}/calendar/google/status`, { headers: {} });
  return handle<{ connected: boolean; details: GoogleConnectionDetails | null }>(res);
}

export async function googleAuthorizeUrl(): Promise<{ url: string }> {
  const res = await apiFetch(`${API_URL}/calendar/google/authorize`, { headers: {} });
  return handle<{ url: string }>(res);
}

export async function googleDisconnect(): Promise<{ success: boolean }> {
  const res = await apiFetch(`${API_URL}/calendar/google/disconnect`, {
    method: "POST",
    headers: {},
  });
  return handle<{ success: boolean }>(res);
}

export async function syncCalendar(full = true): Promise<{
  success: boolean;
  pushed?: number;
  imported?: number;
}> {
  const res = await apiFetch(`${API_URL}/calendar/sync?full=${full}`, {
    method: "POST",
    headers: {},
  });
  return handle<{ success: boolean; pushed?: number; imported?: number }>(res);
}


// ── Files ──────────────────────────────────────────────────────────────────

export interface FileDoc {
  id: string;
  original_name: string;
  title: string;
  description: string | null;
  subject: string | null;
  folder_id: string | null;
  file_type: string;
  file_size: number;
  status: string;
  needs_ocr: boolean;
  classification: string | null;
  processed_note_id: string | null;
  note_mode?: "summary" | "full_text";
  error_message?: string | null;
  uploaded_at: string;
  /** Course/subject association — null if uncategorized. */
  courseId?: string | null;
  subjectName?: string | null;
}

export interface FolderDoc {
  id: string;
  name: string;
  color: string;
  created_at: string;
}

export interface UploadResponse {
  id: string;
  filename: string;
  status: string;
}

export async function updateFile(id: string, input: { title?: string; description?: string; subject?: string }): Promise<FileDoc> {
  const res = await apiFetch(`${API_URL}/files/${id}`, { method: "PUT", headers: { "Content-Type": "application/json",  }, body: JSON.stringify(input) });
  return handle<FileDoc>(res);
}

export async function retryFileProcessing(id: string): Promise<void> {
  const res = await apiFetch(`${API_URL}/files/${id}/process`, { method: "POST", headers: {} });
  await handle<{ id: string; status: string }>(res);
}

export async function uploadFile(
  file: File,
  meta?: { title?: string; description?: string; subject?: string; folder_id?: string | null; note_mode?: "summary" | "full_text" },
): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  if (meta?.title) form.append("title", meta.title);
  if (meta?.description) form.append("description", meta.description);
  if (meta?.subject) form.append("subject", meta.subject);
  if (meta?.folder_id) form.append("folder_id", meta.folder_id);
  if (meta?.note_mode) form.append("note_mode", meta.note_mode);
  const res = await apiFetch(`${API_URL}/files/upload`, {
    method: "POST",
    headers: {},
    body: form,
  });
  return handle<UploadResponse>(res);
}

export async function listFiles(folderId?: string | null, limit = 100): Promise<FileDoc[]> {
  const params = new URLSearchParams();
  if (folderId) params.set("folder_id", folderId);
  params.set("limit", String(Math.max(1, Math.min(100, Math.floor(limit)))));
  const qs = params.toString();
  const res = await apiFetch(`${API_URL}/files/${qs ? `?${qs}` : ""}`, { headers: {} });
  const data = await handle<{ files: FileDoc[] }>(res);
  return data.files;
}

export async function deleteFile(id: string): Promise<void> {
  const res = await apiFetch(`${API_URL}/files/${id}`, {
    method: "DELETE",
    headers: {},
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const b = await res.json();
      if (b.detail) detail = typeof b.detail === "string" ? b.detail : JSON.stringify(b.detail);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
}

/**
 * Fetch file bytes through the existing authenticated download route.
 */
export async function downloadFileBlob(id: string, signal?: AbortSignal): Promise<Blob> {
  const res = await apiFetch(`${API_URL}/files/${id}/download`, {
    headers: {},
    signal,
  });
  if (!res.ok) throw new Error(`Download failed (${res.status})`);
  const blob = await res.blob();
  signal?.throwIfAborted();
  return blob;
}

/** Caller owns and must revoke the returned blob URL. */
export async function downloadFileUrl(id: string, signal?: AbortSignal): Promise<string> {
  return URL.createObjectURL(await downloadFileBlob(id, signal));
}

/**
 * Fetch a text file's content (with Bearer auth) as a string.
 */
export async function downloadFileText(id: string, signal?: AbortSignal): Promise<string> {
  const res = await apiFetch(`${API_URL}/files/${id}/download`, {
    headers: {},
    signal,
  });
  if (!res.ok) throw new Error(`Download failed (${res.status})`);
  return res.text();
}

// ── Folders ───────────────────────────────────────────────────────────────

export async function listFolders(): Promise<FolderDoc[]> {
  const res = await apiFetch(`${API_URL}/files/folders`, { headers: {} });
  const data = await handle<{ folders: FolderDoc[] }>(res);
  return data.folders;
}

export async function createFolder(name: string): Promise<FolderDoc> {
  const res = await apiFetch(`${API_URL}/files/folders`, {
    method: "POST",
    headers: { "Content-Type": "application/json",  },
    body: JSON.stringify({ name }),
  });
  return handle<FolderDoc>(res);
}

export async function renameFolder(id: string, name: string): Promise<FolderDoc> {
  const res = await apiFetch(`${API_URL}/files/folders/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json",  },
    body: JSON.stringify({ name }),
  });
  return handle<FolderDoc>(res);
}

export async function deleteFolder(id: string): Promise<void> {
  const res = await apiFetch(`${API_URL}/files/folders/${id}`, {
    method: "DELETE",
    headers: {},
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const b = await res.json();
      if (b.detail) detail = typeof b.detail === "string" ? b.detail : JSON.stringify(b.detail);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
}

export async function moveFiles(
  fileIds: string[],
  folderId: string | null,
): Promise<{ moved: number }> {
  const res = await apiFetch(`${API_URL}/files/move`, {
    method: "POST",
    headers: { "Content-Type": "application/json",  },
    body: JSON.stringify({ file_ids: fileIds, folder_id: folderId }),
  });
  return handle<{ moved: number }>(res);
}

// ── Chat Sessions ───────────────────────────────────────────────────────

export interface SessionSummary {
  id: string;
  subject: string | null;
  started_at: string | null;
  message_count: number;
  last_message: string | null;
  last_role: string | null;
}

export interface ChatMessage {
  id: string;
  role: string;
  content: string;
  created_at: string | null;
}

export interface SessionDetail {
  id: string;
  subject: string | null;
  started_at: string | null;
  messages: ChatMessage[];
}

export async function listSessions(): Promise<SessionSummary[]> {
  const res = await apiFetch(`${API_URL}/chat/sessions`, { headers: {} });
  const data = await handle<{ sessions: SessionSummary[] }>(res);
  return data.sessions;
}

export async function getSession(sessionId: string): Promise<SessionDetail> {
  const res = await apiFetch(`${API_URL}/chat/sessions/${sessionId}`, { headers: {} });
  return handle<SessionDetail>(res);
}

export async function deleteSession(sessionId: string): Promise<void> {
  const res = await apiFetch(`${API_URL}/chat/sessions/${sessionId}`, {
    method: "DELETE",
    headers: {},
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const b = await res.json();
      if (b.detail) detail = typeof b.detail === "string" ? b.detail : JSON.stringify(b.detail);
    } catch { /* ignore */ }
    throw new Error(detail);
  }
}

export async function* streamChat(
  message: string,
  signal?: AbortSignal,
  sessionId?: string,
  onSessionId?: (id: string) => void,
  learn?: boolean,
): AsyncGenerator<string> {
  const res = await apiFetch(`${API_URL}${learn ? "/teach/v2/message" : "/chat/message"}`, {
    method: "POST",
    headers: { "Content-Type": "application/json",  },
    body: JSON.stringify({ message, session_id: sessionId ?? null }),
    signal,
  });
  if (!res.ok || !res.body) {
    let detail = res.statusText;
    try {
      const b = await res.json();
      if (b.detail) detail = typeof b.detail === "string" ? b.detail : JSON.stringify(b.detail);
    } catch { /* ignore */ }
    throw new Error(detail);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("data:")) continue;
      const payload = trimmed.slice(5).trim();
      if (payload === "[DONE]") return;
      try {
        const obj = JSON.parse(payload);
        if (obj.session_id) onSessionId?.(obj.session_id);
        else if (obj.delta) yield obj.delta;
        else if (obj.error) throw new Error(obj.error);
      } catch (e) {
        if (e instanceof Error && e.message !== payload) throw e;
      }
    }
  }
}
