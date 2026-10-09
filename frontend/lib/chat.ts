// Chat API client — sessions + streaming messages.

import { apiFetch } from "./apiRequest";

export const CHAT_SESSIONS_UPDATED_EVENT = "pixie:chat-sessions-updated";

export function notifyChatSessionsUpdated(sessions: ChatSession[]) {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(CHAT_SESSIONS_UPDATED_EVENT, { detail: sessions }));
  }
}

import { API_URL } from "./apiOrigin";

export interface ChatSession {
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

export async function listSessions(): Promise<ChatSession[]> {
  const res = await apiFetch(`${API_URL}/chat/sessions`, {
  });
  if (!res.ok) throw new Error(`Sessions fetch failed: ${res.statusText}`);
  return (await res.json()).sessions as ChatSession[];
}

export async function getSession(sessionId: string): Promise<SessionDetail> {
  const res = await apiFetch(`${API_URL}/chat/sessions/${sessionId}`, {
  });
  if (!res.ok) throw new Error(`Session fetch failed: ${res.statusText}`);
  return (await res.json()) as SessionDetail;
}

export async function renameSession(sessionId: string, title: string): Promise<string> {
  const res = await apiFetch(`${API_URL}/chat/sessions/${encodeURIComponent(sessionId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!res.ok) throw new Error(`Rename failed: ${res.statusText}`);
  const updated = (await res.json()) as { subject: string };
  return updated.subject;
}

export async function deleteSession(sessionId: string): Promise<void> {
  const res = await apiFetch(`${API_URL}/chat/sessions/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(`Delete failed: ${res.statusText}`);
}

/**
 * Send a message and stream the reply. onDelta receives text chunks as they
 * arrive; onSessionId fires once with the (possibly new) session id.
 * Resolves when the stream closes.
 */
export async function sendMessage(
  message: string,
  sessionId: string | null,
  onDelta: (text: string) => void,
  onSessionId: (id: string) => void,
): Promise<void> {
  const res = await apiFetch(`${API_URL}/chat/message`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId }),
  });
  if (!res.ok || !res.body) {
    throw new Error(`Send failed: ${res.statusText}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split("\n");
    buf = lines.pop() ?? "";
    for (const line of lines) {
      const t = line.trim();
      if (!t.startsWith("data:")) continue;
      const payload = t.slice(5).trim();
      if (payload === "[DONE]") return;
      try {
        const ev = JSON.parse(payload);
        if (typeof ev.session_id === "string") onSessionId(ev.session_id);
        if (typeof ev.delta === "string") onDelta(ev.delta);
      } catch {
        /* partial JSON, wait for more */
      }
    }
  }
}
