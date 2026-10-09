"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Clock3, Plus, Search, X } from "lucide-react";
import { CHAT_SESSIONS_UPDATED_EVENT, listSessions, type ChatSession } from "@/lib/chat";

function sessionTitle(session: ChatSession) {
  const title = (session.subject?.trim() || session.last_message?.trim() || "Untitled conversation")
    .replace(/\*\*/g, "");
  return title.length > 52 ? `${title.slice(0, 52).trimEnd()}…` : title;
}

export default function ChatHistorySidebar() {
  const searchParams = useSearchParams();
  const activeId = searchParams.get("id");
  const mode = searchParams.get("mode") === "learn" ? "learn" : "chat";
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [query, setQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const mountedRef = useRef(false);
  const mobileTriggerRef = useRef<HTMLButtonElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const refreshSessions = useCallback(async () => {
    try {
      const next = await listSessions();
      if (mountedRef.current) setSessions(next);
    } catch {
      if (mountedRef.current) setFailed(true);
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (searchOpen) searchInputRef.current?.focus();
  }, [searchOpen]);

  useEffect(() => {
    let active = true;
    mountedRef.current = true;
    void listSessions().then((next) => {
      if (active) setSessions(next);
    }).catch(() => {
      if (active) setFailed(true);
    }).finally(() => {
      if (active) setLoading(false);
    });
    const handleUpdate = (event: Event) => {
      const updated = (event as CustomEvent<ChatSession[]>).detail;
      if (Array.isArray(updated)) {
        setSessions(updated);
        setFailed(false);
        setLoading(false);
      }
    };
    window.addEventListener(CHAT_SESSIONS_UPDATED_EVENT, handleUpdate);
    return () => {
      active = false;
      mountedRef.current = false;
      window.removeEventListener(CHAT_SESSIONS_UPDATED_EVENT, handleUpdate);
    };
  }, [refreshSessions]);

  useEffect(() => {
    if (!mobileOpen) return;
    const trigger = mobileTriggerRef.current;
    closeButtonRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMobileOpen(false);
      if (event.key === "Tab") {
        const dialog = document.querySelector<HTMLElement>(".chat-history-mobile-dialog");
        const focusable = dialog?.querySelectorAll<HTMLElement>('a[href],button:not([disabled]),input:not([disabled])');
        if (!focusable?.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      trigger?.focus();
    };
  }, [mobileOpen]);

  const term = query.trim().toLocaleLowerCase();
  const visibleSessions = term
    ? sessions.filter((session) => `${session.subject ?? ""} ${session.last_message ?? ""}`.toLocaleLowerCase().includes(term))
    : sessions;

  function newChatHref() {
    return "/app/chat?new=1&mode=chat";
  }

  function toggleSearch() {
    if (searchOpen) setQuery("");
    setSearchOpen(!searchOpen);
  }

  function renderSearch() {
    return searchOpen && <label className="chat-history-search">
      <Search size={15} aria-hidden="true" />
      <input ref={searchInputRef} value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Escape") toggleSearch(); }} aria-label="Search chats" placeholder="Search chats" />
    </label>;
  }

  function renderSessionList() {
    if (loading) return <div className="chat-history-message" role="status">Loading conversations…</div>;
    if (failed) return <div className="chat-history-message"><span>Chat history couldn’t load.</span><button type="button" onClick={() => { setFailed(false); setLoading(true); void refreshSessions(); }}>Try again</button></div>;
    if (visibleSessions.length === 0) {
      return <div className="chat-history-message">{term ? "No conversations match that search." : "Your conversations will appear here."}</div>;
    }

    return <ul className="chat-history-list">
      {visibleSessions.map((session) => {
        const selected = session.id === activeId;
        return <li key={session.id}>
          <Link
            href={`/app/chat?id=${encodeURIComponent(session.id)}&mode=${mode}`}
            aria-current={selected ? "page" : undefined}
            title={sessionTitle(session)}
            onClick={() => setMobileOpen(false)}
            className={selected ? "is-active" : ""}
          >
            <span>{sessionTitle(session)}</span>
          </Link>
        </li>;
      })}
    </ul>;
  }

  return <>
    <section className="chat-history-section" aria-labelledby="chat-history-heading">
      <div className="chat-history-heading">
        <h2 id="chat-history-heading">Chats</h2>
        <div className="chat-history-actions">
          <Link href={newChatHref()} title="New chat"><Plus size={17} aria-hidden="true" /> New</Link>
          <button type="button" onClick={toggleSearch} aria-label={searchOpen ? "Close chat search" : "Search chats"} aria-expanded={searchOpen} title="Search chats"><Search size={17} aria-hidden="true" /></button>
        </div>
      </div>
      {renderSearch()}
      <nav className="chat-history-scroll" aria-label="Chat history">{renderSessionList()}</nav>
    </section>

    <button ref={mobileTriggerRef} type="button" className="chat-history-mobile-trigger" onClick={() => setMobileOpen(true)}>
      <Clock3 size={17} aria-hidden="true" /> History
    </button>
    {mobileOpen && <div className="chat-history-mobile-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setMobileOpen(false); }}>
      <section className="chat-history-mobile-dialog" role="dialog" aria-modal="true" aria-labelledby="chat-history-mobile-heading">
        <div className="chat-history-heading">
          <h2 id="chat-history-mobile-heading">Chat history</h2>
          <button ref={closeButtonRef} type="button" onClick={() => setMobileOpen(false)} aria-label="Close chat history"><X size={19} /></button>
        </div>
        <div className="chat-history-mobile-actions">
          <Link className="chat-history-mobile-new" href={newChatHref()} onClick={() => setMobileOpen(false)}><Plus size={17} aria-hidden="true" /> New</Link>
          <button type="button" onClick={toggleSearch} aria-label={searchOpen ? "Close chat search" : "Search chats"} aria-expanded={searchOpen} title="Search chats"><Search size={17} aria-hidden="true" /></button>
        </div>
        {renderSearch()}
        <nav className="chat-history-mobile-scroll" aria-label="Chat history">{renderSessionList()}</nav>
      </section>
    </div>}
  </>;
}
