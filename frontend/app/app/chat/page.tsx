"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import ChatBubble from "@/components/chat/ChatBubble";
import ComposerCard from "@/components/chat/ComposerCard";
import ChatSessionHeader from "@/components/chat/ChatSessionHeader";
import ThinkingIndicator from "@/components/chat/ThinkingIndicator";
import { deleteSession, getSession, listSessions, notifyChatSessionsUpdated, renameSession, sendMessage, type ChatMessage, type ChatSession } from "@/lib/chat";
import { streamChat } from "@/lib/api";
import { fetchDashboard } from "@/lib/dashboard";

function ChatInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [index, setIndex] = useState(0);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState("");
  const [thinking, setThinking] = useState(false);
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [learn, setLearn] = useState(() => searchParams.get("mode") === "learn");
  const [draft, setDraft] = useState("");
  const [started, setStarted] = useState(false);
  const [studentName, setStudentName] = useState("");
  const [ready, setReady] = useState(false);
  const [scrollEdges, setScrollEdges] = useState({ top: false, bottom: false });
  const scrollRef = useRef<HTMLDivElement>(null);
  const shouldFollowRef = useRef(true);
  const composedRef = useRef(false);
  const activeId = sessions[index]?.id ?? null;

  const loadSession = useCallback(async (id: string | null, isCurrent: () => boolean) => {
    if (!isCurrent()) return;
    if (!id) {
      setMessages([]);
      return;
    }
    try {
      const detail = await getSession(id);
      if (isCurrent()) setMessages(detail.messages);
    } catch (error) {
      if (isCurrent()) {
        console.error(error);
        setMessages([]);
      }
    }
  }, []);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const [list, dashboard] = await Promise.all([listSessions(), fetchDashboard()]);
        if (!active) return;
        setStudentName(dashboard.student_name);
        setSessions(list);
        const requestedId = searchParams.get("id");
        const requestedContinue = searchParams.get("continue") === "1";
        // A route without an explicit id is a fresh session by default. The
        // dashboard's Continue action opts into the latest session explicitly.
        if (!requestedId && !requestedContinue) {
          setIndex(-1);
          setStarted(false);
          await loadSession(null, () => active);
          setLearn(searchParams.get("mode") === "learn");
          return;
        }
        const requestedIndex = requestedId ? list.findIndex((session) => session.id === requestedId) : -1;
        const selectedIndex = requestedIndex >= 0 ? requestedIndex : 0;
        setIndex(selectedIndex);
        setStarted(false);
        await loadSession(list[selectedIndex]?.id ?? null, () => active);
      } catch (error) {
        if (active) console.error(error);
      } finally {
        if (active) setReady(true);
      }
    })();
    return () => { active = false; };
  }, [router, searchParams, loadSession]);

  useEffect(() => {
    const element = scrollRef.current;
    if (!element) return;

    const updateScrollEdges = () => {
      const next = {
        top: element.scrollTop > 4,
        bottom: element.scrollHeight - element.clientHeight - element.scrollTop > 4,
      };
      shouldFollowRef.current = element.scrollHeight - element.clientHeight - element.scrollTop < 88;
      setScrollEdges((previous) => (
        previous.top === next.top && previous.bottom === next.bottom ? previous : next
      ));
    };

    if (shouldFollowRef.current) element.scrollTop = element.scrollHeight;
    updateScrollEdges();
    element.addEventListener("scroll", updateScrollEdges, { passive: true });
    const resizeObserver = new ResizeObserver(updateScrollEdges);
    resizeObserver.observe(element);
    return () => {
      element.removeEventListener("scroll", updateScrollEdges);
      resizeObserver.disconnect();
    };
  }, [activeId, started]);

  useEffect(() => {
    const element = scrollRef.current;
    if (!element || !shouldFollowRef.current) return;
    element.scrollTop = element.scrollHeight;
  }, [messages, streaming]);

  const sendChat = useCallback(async (
    text: string,
    sessionId: string | null,
    useLearn: boolean,
  ) => {
    const optimistic: ChatMessage = { id: `local-${Date.now()}`, role: "user", content: text, created_at: null };
    setMessages((previous) => [...previous, optimistic]);
    setStreaming("");
    setThinking(true);
    setSendError(null);
    let full = "";
    let newSessionId: string | null = null;

    try {
      if (useLearn) {
        for await (const delta of streamChat(text, undefined, sessionId ?? undefined, (id) => { newSessionId = id; }, true)) {
          full += delta;
          setStreaming(full);
        }
      } else {
        await sendMessage(text, sessionId, (delta) => {
          full += delta;
          setStreaming(full);
        }, (id) => { newSessionId = id; });
      }

      if (full) setMessages((previous) => [...previous, { id: `assistant-${Date.now()}`, role: "assistant", content: full, created_at: null }]);
      setStreaming("");
      setThinking(false);

      const refreshed = await listSessions();
      setSessions(refreshed);
      notifyChatSessionsUpdated(refreshed);
      if (!sessionId && newSessionId) {
        const createdSessionId = newSessionId;
        const nextIndex = refreshed.findIndex((session) => session.id === createdSessionId);
        setIndex(nextIndex >= 0 ? nextIndex : 0);
        router.replace(`/app/chat?id=${encodeURIComponent(createdSessionId)}&mode=${useLearn ? "learn" : "chat"}`);
      }
    } catch (error) {
      console.error(error);
      setSendError(error instanceof Error ? error.message : "The response could not be completed. Please try again.");
      setStreaming("");
      setThinking(false);
    }
  }, [router]);

  useEffect(() => {
    if (!ready || composedRef.current || sending) return;
    const firstMessage = searchParams.get("compose");
    if (!firstMessage) return;
    composedRef.current = true;
    const useLearn = searchParams.get("mode") === "learn";
    // This effect intentionally starts the one-shot deep-link send.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setStarted(true);
    sendChat(firstMessage, null, useLearn).finally(() => setSending(false));
  }, [ready, searchParams, sendChat, sending]);

  if (!ready) return null;

  const hasThread = Boolean(activeId) || started;
  const currentSession = sessions[index];
  const title = currentSession?.subject || messages.find((message) => message.role === "user")?.content || "New chat";

  const composer = <ComposerCard
    value={draft}
    onValueChange={setDraft}
    mode={learn ? "learn" : "chat"}
    onModeChange={(mode) => {
      setLearn(mode === "learn");
      const params = new URLSearchParams(searchParams.toString());
      params.set("mode", mode);
      router.replace(`/app/chat?${params.toString()}`);
    }}
    compact={hasThread}
    disabled={sending}
    onSend={(text, mode) => {
      if (sending) return;
      setDraft("");
      if (!hasThread) setStarted(true);
      setLearn(mode === "learn");
      setSending(true);
      sendChat(text, activeId, mode === "learn").finally(() => setSending(false));
    }}
  />;

  return (
    <div className="chat-page">
      {hasThread ? <>
        {activeId && <ChatSessionHeader
          key={activeId ?? "pending"}
          title={title}
          onRename={async (next) => {
            if (!activeId) return;
            const updatedTitle = await renameSession(activeId, next);
            const updated = sessions.map((session) => session.id === activeId ? { ...session, subject: updatedTitle } : session);
            setSessions(updated);
            notifyChatSessionsUpdated(updated);
          }}
          onDelete={async () => {
            if (!activeId) return;
            await deleteSession(activeId);
            const remaining = sessions.filter((session) => session.id !== activeId);
            setSessions(remaining);
            notifyChatSessionsUpdated(remaining);
            setMessages([]);
            setIndex(-1);
            setStarted(false);
            router.replace("/app/chat?new=1&mode=chat");
          }}
        />}
        <div className="chat-thread-stage">
          <div ref={scrollRef} className="chat-message-scroll scrollbar-subtle">
            <div className="chat-message-column">
              {messages.map((message) => <ChatBubble key={message.id} role={message.role} content={message.content} />)}
              {streaming && <ChatBubble role="assistant" content={streaming} />}
              {sendError && <p role="alert" className="font-body text-sm">{sendError}</p>}
              {thinking && !streaming && <ThinkingIndicator />}
              {!messages.length && !streaming && <p className="font-body text-center" style={{ color: "var(--color-dark)", fontSize: 13, opacity: 0.6 }}>Ask Pixie anything to start this session.</p>}
            </div>
          </div>
          {scrollEdges.top && <div className="chat-top-fade" aria-hidden="true" />}
          <div className="chat-composer-dock"><div>{composer}</div></div>
        </div>
      </> : <div className="chat-empty-stage">
        <AnimatePresence initial={false}>
          <motion.div
            key="welcome"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -28, scale: 0.96, transition: { duration: 0.28 } }}
            className="flex flex-col items-center gap-6 pb-8 sm:gap-8"
          >
            <div className="flex h-28 w-28 items-center justify-center sm:h-36 sm:w-36" aria-hidden="true">
              <img src="/icons/fox-logo.svg" alt="" className="max-h-full max-w-full object-contain" />
            </div>
            <h1 className="font-greeting text-center" style={{ fontSize: "clamp(2rem, 5vw, 3.5rem)" }}>
              {new Date().getHours() < 12 ? "Morning" : new Date().getHours() < 17 ? "Afternoon" : "Evening"}{studentName ? `, ${studentName}` : ""}
            </h1>
          </motion.div>
        </AnimatePresence>
        <div className="chat-empty-composer">{composer}</div>
      </div>}
    </div>
  );
}

export default function ChatPage() {
  return <Suspense><ChatInner /></Suspense>;
}
