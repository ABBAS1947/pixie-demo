"use client";

import Link from "next/link";
import { createPortal } from "react-dom";
import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent, MouseEvent as ReactMouseEvent } from "react";
import { Suspense } from "react";
import { usePathname, useRouter } from "next/navigation";
import { CalendarDays, FolderOpen, House, LogOut, MessageCircle, Settings, Target, UserRound } from "lucide-react";
import UserAvatar from "@/components/UserAvatar";
import ChatHistorySidebar from "@/components/chat/ChatHistorySidebar";
import { useLearnerIdentity } from "@/components/LearnerIdentityContext";
import { clearSession } from "@/lib/auth";
import { supabase } from "@/lib/supabase";

const primary = [
  { label: "Home", href: "/dashboard", Icon: House },
  { label: "Chat", href: "/app/chat?new=1&mode=chat", Icon: MessageCircle },
  { label: "Library", href: "/app/library", Icon: FolderOpen },
  { label: "Practice", href: "/app/quiz", Icon: Target },
  { label: "Planner", href: "/app/calendar", Icon: CalendarDays },
];

export default function LearnerSidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { identity, loading: identityLoading, sessionUserId } = useLearnerIdentity();
  const name = identity?.name;
  const userId = identity?.userId;
  const rank = identity?.rank;
  const [accountOpen, setAccountOpen] = useState(false);
  const [accountPosition, setAccountPosition] = useState<{ left: number; bottom: number; width: number } | null>(null);
  const accountTrigger = useRef<HTMLButtonElement | null>(null);
  const accountPanel = useRef<HTMLDivElement | null>(null);

  function positionAccountPanel(trigger = accountTrigger.current) {
    if (!trigger) return;
    const bounds = trigger.getBoundingClientRect();
    const desktop = window.innerWidth > 800;
    const panelWidth = desktop ? bounds.width : 248;
    const edge = 12;
    const preferredLeft = desktop ? bounds.left : bounds.right - panelWidth;
    const left = Math.max(edge, Math.min(preferredLeft, window.innerWidth - panelWidth - edge));
    setAccountPosition({ left, bottom: window.innerHeight - bounds.top + 8, width: panelWidth });
  }

  function toggleAccountMenu(event: ReactMouseEvent<HTMLButtonElement>) {
    if (accountOpen) {
      setAccountOpen(false);
      return;
    }
    accountTrigger.current = event.currentTarget;
    positionAccountPanel(event.currentTarget);
    setAccountOpen(true);
  }

  async function logOut() {
    setAccountOpen(false);
    try { await supabase.auth.signOut({ scope: "local" }); } catch { /* Local sign-out still clears the app session. */ }
    clearSession();
    router.replace("/login");
  }

  useEffect(() => {
    if (!accountOpen) return;
    const firstMenuItem = accountPanel.current?.querySelector<HTMLElement>('[role="menuitem"]');
    firstMenuItem?.focus();
    const dismissOutside = (event: PointerEvent) => {
      const target = event.target;
      if (target instanceof Node && !accountPanel.current?.contains(target) && !accountTrigger.current?.contains(target)) {
        setAccountOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setAccountOpen(false);
        accountTrigger.current?.focus();
      }
    };
    const dismissWhenFocusLeaves = (event: FocusEvent) => {
      const target = event.target;
      if (target instanceof Node && !accountPanel.current?.contains(target) && !accountTrigger.current?.contains(target)) {
        setAccountOpen(false);
      }
    };
    const reposition = () => positionAccountPanel();
    document.addEventListener("pointerdown", dismissOutside);
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("focusin", dismissWhenFocusLeaves);
    window.addEventListener("resize", reposition);
    window.addEventListener("scroll", reposition, true);
    return () => {
      document.removeEventListener("pointerdown", dismissOutside);
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("focusin", dismissWhenFocusLeaves);
      window.removeEventListener("resize", reposition);
      window.removeEventListener("scroll", reposition, true);
    };
  }, [accountOpen]);

  function handleAccountMenuKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    const items = Array.from(accountPanel.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? []);
    const current = items.indexOf(document.activeElement as HTMLElement);
    if (event.key === "ArrowDown" || event.key === "ArrowUp" || event.key === "Home" || event.key === "End") {
      event.preventDefault();
      const next = event.key === "Home" ? 0 : event.key === "End" ? items.length - 1
        : (current + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
      items[next]?.focus();
    } else if (event.key === " " && event.target instanceof HTMLAnchorElement) {
      event.preventDefault();
      event.target.click();
    }
  }

  function isActive(href: string) {
    if (href === "/dashboard") return pathname === href;
    if (href === "/app/library") return ["/app/library", "/app/notebook"].some((route) => pathname === route || pathname.startsWith(`${route}/`));
    const route = href.split(/[?#]/, 1)[0];
    return pathname === route || pathname.startsWith(`${route}/`);
  }

  return (
    <aside className="account-area-rail learner-sidebar" aria-label="Pixie navigation">
      <Link href="/dashboard" className="account-area-brand" aria-label="Pixie home" title="Pixie home">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/icons/PixieLogo(silhouette)-06.svg" width={44} height={45} alt="" />
      </Link>
      <nav className="account-area-links" aria-label="Main navigation">
        {primary.map(({ label, href, Icon }) => {
          const selected = isActive(href);
          return <Link key={href} href={href} aria-label={label} title={label} aria-current={selected ? "page" : undefined} className={selected ? "is-active" : ""}><Icon size={20} aria-hidden="true" /><span>{label}</span></Link>;
        })}
      </nav>
      {pathname === "/app/chat" && <Suspense fallback={<div className="chat-history-loading" aria-hidden="true"><i /><i /><i /></div>}><ChatHistorySidebar key={sessionUserId ?? "signed-out"} /></Suspense>}
      <div className="account-area-rail-footer learner-sidebar-account">
        <button type="button" id="learner-account-trigger" ref={accountTrigger} className={`learner-sidebar-identity${accountOpen ? " is-open" : ""}`} aria-label={identityLoading ? "Open account options" : `Open account options for ${name || "Learner"}`} aria-haspopup="menu" aria-expanded={accountOpen} aria-controls={accountOpen ? "learner-account-panel" : undefined} aria-busy={identityLoading} title={name || undefined} onClick={toggleAccountMenu}>
          <span className={`learner-sidebar-avatar${identityLoading && !userId ? " is-loading" : ""}`}>{userId ? <UserAvatar userId={userId} width={44} height={44} fallbackSrc="/icons/fox-logo.svg" /> : !identityLoading && <UserRound size={20} aria-hidden="true" />}</span>
          {identityLoading ? <span className="learner-sidebar-skeleton" aria-hidden="true"><i /><i /></span> : (name || rank) ? <span className="learner-sidebar-name"><strong>{name || "Learner"}</strong>{rank && <small>{rank}</small>}</span> : <span className="learner-sidebar-name"><strong>Learner</strong></span>}
        </button>
      </div>
      <nav className="learner-sidebar-mobile" aria-label="Main navigation">
        {primary.map(({ label, href, Icon }) => {
          const selected = isActive(href);
          return <Link key={href} href={href} aria-label={label} title={label} aria-current={selected ? "page" : undefined} className={selected ? "is-active" : ""}><Icon size={20} aria-hidden="true" /><span>{label}</span></Link>;
        })}
        <button type="button" id="learner-account-trigger-mobile" ref={accountTrigger} aria-label="Open account options" aria-haspopup="menu" aria-expanded={accountOpen} aria-controls={accountOpen ? "learner-account-panel" : undefined} aria-busy={identityLoading} title={name || undefined} className={accountOpen ? "is-active" : ""} onClick={toggleAccountMenu}>
          <span className={`learner-sidebar-mobile-avatar${identityLoading && !userId ? " is-loading" : ""}`}>{userId ? <UserAvatar userId={userId} width={24} height={24} fallbackSrc="/icons/fox-logo.svg" /> : !identityLoading && <UserRound size={20} aria-hidden="true" />}</span>
          {identityLoading ? <span className="learner-sidebar-mobile-skeleton" aria-hidden="true" /> : <span>{name || "Profile"}</span>}
        </button>
      </nav>
      {accountOpen && accountPosition && typeof document !== "undefined" && createPortal(
        <div id="learner-account-panel" ref={accountPanel} className="learner-account-panel" style={{ left: accountPosition.left, bottom: accountPosition.bottom, width: accountPosition.width }} role="menu" aria-label="Account options" onKeyDown={handleAccountMenuKeyDown}>
          <Link href="/app/profile" role="menuitem" tabIndex={-1} onClick={() => setAccountOpen(false)}><UserRound size={17} aria-hidden="true" /><span>Profile</span></Link>
          <Link href="/app/settings" role="menuitem" tabIndex={-1} onClick={() => setAccountOpen(false)}><Settings size={17} aria-hidden="true" /><span>Settings</span></Link>
          <button type="button" role="menuitem" tabIndex={-1} onClick={() => void logOut()}><LogOut size={17} aria-hidden="true" /><span>Log out</span></button>
        </div>,
        document.body,
      )}
    </aside>
  );
}
