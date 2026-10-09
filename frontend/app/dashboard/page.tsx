"use client";

import { useEffect, useRef, useState, type CSSProperties } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, Plus, RotateCcw, X } from "lucide-react";
import { fetchDashboard, type DashboardData } from "@/lib/dashboard";
import { fetchMe, listFiles, listNotes, type FileDoc } from "@/lib/api";
import type { Note } from "@/lib/types";
import { useLearnerIdentity } from "@/components/LearnerIdentityContext";
import QuickCapturePanel from "@/components/QuickCapturePanel";
import styles from "./dashboard.module.css";

type RecentMaterial = {
  id: string;
  title: string;
  kind: "note" | "file";
  href: string;
  timestamp: string | null;
  status: string | null;
};

const MAX_RECENT_MATERIALS = 3;

export default function DashboardPage() {
  const router = useRouter();
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const { sessionUserId, sessionResolved, updateFromDashboard, updateUserId, markIdentityUnavailable } = useLearnerIdentity();
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);
  const [streakPinned, setStreakPinned] = useState(false);
  const [streakArrowRight, setStreakArrowRight] = useState(64);
  const headerStatsRef = useRef<HTMLDivElement>(null);
  const streakTriggerRef = useRef<HTMLButtonElement>(null);
  const [dismissedNotice, setDismissedNotice] = useState<string | null>(null);
  const [snapshotTime, setSnapshotTime] = useState(0);
  const [recentMaterials, setRecentMaterials] = useState<RecentMaterial[]>([]);
  const [recentOwnerId, setRecentOwnerId] = useState<string | null>(null);
  const [recentLoading, setRecentLoading] = useState(true);
  const [recentError, setRecentError] = useState(false);
  const [recentPartialError, setRecentPartialError] = useState(false);
  const [recentAttempt, setRecentAttempt] = useState(0);

  useEffect(() => {
    if (!sessionResolved) return;
    if (!sessionUserId) { router.replace("/login"); return; }
    let alive = true;
    let pending = false;
    const load = async () => {
      if (pending) return;
      pending = true;
      try {
        const data = await fetchDashboard();
        if (alive) {
          setDashboard(data);
          updateFromDashboard(data, sessionUserId);
          setSnapshotTime(Date.now());
          setError(false);
          if (!(typeof data.user_id === "string" && data.user_id.trim())) {
            void fetchMe().then((user) => { if (alive) updateUserId(user.user_id, sessionUserId, user.name); }).catch(() => {});
          }
        }
      } catch {
        if (alive) {
          setError(true);
          markIdentityUnavailable(sessionUserId);
        }
      } finally {
        pending = false;
        if (alive) setLoading(false);
      }
    };
    void load();
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void load();
    }, 60000);
    return () => { alive = false; window.clearInterval(timer); };
  }, [router, attempt, sessionResolved, sessionUserId, updateFromDashboard, updateUserId, markIdentityUnavailable]);

  useEffect(() => {
    if (!sessionResolved || !sessionUserId) return;
    let alive = true;
    setRecentLoading(true);
    setRecentError(false);
    setRecentPartialError(false);
    const loadRecent = async () => {
      const [notesResult, filesResult] = await Promise.allSettled([listNotes(8), listFiles(null, 8)]);
      if (!alive) return;
      const materials: RecentMaterial[] = [];
      const processedNoteIds = filesResult.status === "fulfilled"
        ? new Set(filesResult.value.map((file) => file.processed_note_id).filter((id): id is string => Boolean(id)))
        : new Set<string>();
      if (notesResult.status === "fulfilled") materials.push(...notesResult.value
        .filter((note) => !processedNoteIds.has(note.id) && (note.title.trim() || Boolean(note.content?.trim())))
        .map((note: Note) => ({ id: note.id, title: note.title.trim() || "Untitled note", kind: "note" as const, href: `/app/notebook?noteId=${encodeURIComponent(note.id)}`, timestamp: note.updatedAt || note.createdAt || null, status: null })));
      if (filesResult.status === "fulfilled") materials.push(...filesResult.value
        .map((file: FileDoc) => ({ id: file.id, title: file.title?.trim() || file.original_name || "Untitled file", kind: "file" as const, href: `/app/library?view=files&fileId=${encodeURIComponent(file.id)}`, timestamp: file.uploaded_at || null, status: file.status })));
      materials.sort((a, b) => (Date.parse(b.timestamp || "") || 0) - (Date.parse(a.timestamp || "") || 0));
      setRecentMaterials(materials.slice(0, MAX_RECENT_MATERIALS));
      setRecentOwnerId(sessionUserId);
      const notesFailed = notesResult.status === "rejected";
      const filesFailed = filesResult.status === "rejected";
      setRecentError(notesFailed && filesFailed);
      setRecentPartialError(notesFailed !== filesFailed);
      setRecentLoading(false);
    };
    void loadRecent();
    return () => { alive = false; };
  }, [sessionResolved, sessionUserId, recentAttempt]);

  function retry() { setLoading(true); setAttempt((value) => value + 1); }
  function retryRecent() { setRecentAttempt((value) => value + 1); }
  const notice = dashboard?.announcement;
  const showNotice = notice && notice.id !== dismissedNotice && (!notice.expires_at || Date.parse(notice.expires_at) > snapshotTime);
  const noticeHref = notice?.href && /^\/(?![/\\])(?:app\/|dashboard(?:[?#]|$))/.test(notice.href) ? notice.href : null;
  const materialsForCurrentUser = recentOwnerId === sessionUserId ? recentMaterials : [];
  const materialsLoadingForCurrentUser = recentOwnerId !== sessionUserId || recentLoading;
  const streakWeekdays = dashboard ? orderedWeekdays(dashboard.timezone) : [];
  const alignStreakArrow = () => {
    const stats = headerStatsRef.current?.getBoundingClientRect();
    const trigger = streakTriggerRef.current?.getBoundingClientRect();
    if (stats && trigger) setStreakArrowRight(stats.right - trigger.left - trigger.width / 2);
  };

  return (
    <div className={styles.page}>
      <a className={styles.skipLink} href="#study-home">Skip to your study dashboard</a>
      <main id="study-home" className={styles.main} tabIndex={-1}>
        <header className={styles.header}>
          <h1>{dashboard ? `Hi, ${dashboard.student_name}.` : "Home"}</h1>
          {dashboard && <div ref={headerStatsRef} className={styles.headerStats} role="group" aria-label="Learning progress">
            <div className={`${styles.streakPopover}${streakPinned ? ` ${styles.streakPinned}` : ""}`} onPointerEnter={alignStreakArrow} onFocus={alignStreakArrow}>
              <button ref={streakTriggerRef} type="button" className={`${styles.headerStat}${dashboard.streak_days === 0 ? ` ${styles.statZero}` : ""}`} aria-describedby="streak-details" aria-label={`${dashboard.streak_days}-day streak`} onClick={() => {
                if (window.matchMedia("(hover: none)").matches) setStreakPinned((open) => !open);
              }}>
                <span className={`${styles.headerStatIcon} ${styles.headerStreakIcon}`} aria-hidden="true" />
                <strong>{dashboard.streak_days}</strong>
              </button>
              <div id="streak-details" className={styles.streakDetails} style={{ "--streak-arrow-right": `${streakArrowRight}px` } as CSSProperties} role="tooltip">
                <div className={styles.streakDetailHeading}>
                  <span className={`${styles.headerStatIcon} ${styles.headerStreakIcon}`} aria-hidden="true" />
                  <div><strong>{dashboard.streak_days} day streak</strong><p>{dashboard.streak_days === 0 ? "Do a study exchange today to start a streak." : "Keep studying on consecutive days to grow your streak."}</p></div>
                </div>
                <div className={styles.streakWeek} role="list" aria-label={`Weekdays starting with ${streakWeekdays[0].name}`}>
                  {streakWeekdays.map((day) => <span key={day.offset} role="listitem" aria-label={`${day.name}${day.isToday ? ", today" : ""}`} aria-current={day.isToday ? "date" : undefined} className={day.isToday ? styles.streakToday : undefined}>{day.initial}</span>)}
                </div>
              </div>
            </div>
            <div className={`${styles.headerStat}${dashboard.xp === 0 ? ` ${styles.statZero}` : ""}`} role="img" aria-label={`${dashboard.xp.toLocaleString("en")} XP`}>
              <span className={`${styles.headerStatIcon} ${styles.headerXpIcon}`} aria-hidden="true" />
              <strong aria-hidden="true">{dashboard.xp.toLocaleString("en")}</strong>
            </div>
          </div>}
        </header>
        {showNotice && <div className={styles.announcement} role="status">
          <div><strong>{notice.title}</strong><p>{notice.message}</p>{noticeHref && notice.action_label && <Link href={noticeHref}>{notice.action_label}<ArrowRight size={15} aria-hidden="true" /></Link>}</div>
          <button type="button" aria-label="Dismiss announcement" onClick={() => setDismissedNotice(notice.id)}><X size={18} aria-hidden="true" /></button>
        </div>}
        {error && (
          <div className={styles.error} role="alert">
            <p>{dashboard ? "Your latest updates couldn't load. These details may be out of date." : "We couldn't load your study space. Please try again."}</p>
            <button type="button" onClick={retry} disabled={loading}><RotateCcw size={16} aria-hidden="true" /> {loading ? "Trying again…" : "Try again"}</button>
          </div>
        )}
        {!dashboard ? (
          loading ? <LoadingDashboard /> : (
            <div className={styles.recovery}>
              <h2>Your study space is still here.</h2>
              <p>Try opening your notes or starting a conversation.</p>
              <div className={styles.actions}>
                <Link className={styles.primaryButton} href="/app/library">Open Library <ArrowRight size={18} aria-hidden="true" /></Link>
                <Link className={styles.textLink} href="/app/chat?new=1&mode=chat">Ask Pixie</Link>
              </div>
            </div>
          )
        ) : <DashboardContent
          dashboard={dashboard}
          recentMaterials={materialsForCurrentUser}
          recentLoading={materialsLoadingForCurrentUser}
          recentError={recentError && recentOwnerId === sessionUserId}
          recentPartialError={recentPartialError && recentOwnerId === sessionUserId}
          onRetryRecent={retryRecent}
        />}
      </main>
    </div>
  );
}

function DashboardContent({ dashboard, recentMaterials, recentLoading, recentError, recentPartialError, onRetryRecent }: {
  dashboard: DashboardData;
  recentMaterials: RecentMaterial[];
  recentLoading: boolean;
  recentError: boolean;
  recentPartialError: boolean;
  onRetryRecent: () => void;
}) {
  const resume = Boolean(dashboard.continue_session_id);
  const primaryHref = resume ? `/app/chat?id=${encodeURIComponent(dashboard.continue_session_id!)}&mode=learn` : "/app/chat?new=1&mode=chat";

  return (
    <div className={styles.contentGrid}>
      <div className={styles.studyColumn}>
        <section className={`${styles.hero} ${resume ? styles.heroWithMascot : ""}`} aria-labelledby="next-step-title">
          <div className={styles.heroCopy}>
            {!resume && <p className={styles.heroLabel}>Ready when you are</p>}
            <h2 id="next-step-title">{resume ? "Continue learning" : "What would you like to study?"}</h2>
            <p>{resume && dashboard.continue_topic ? dashboard.continue_topic : resume ? "Open your saved lesson and continue at your own pace." : "Ask Pixie a question, or choose a topic from your own notes and files."}</p>
          </div>
          {resume && <div className={styles.heroMascot} aria-hidden="true"><span className={styles.heroMascotSparkle}>✦</span><img src="/icons/fox-logo.svg" width={651} height={666} alt="" /></div>}
          <div className={styles.actions}>
            <Link href={primaryHref} className={styles.primaryButton}>{resume ? "Continue lesson" : "Ask Pixie a question"}<ArrowRight size={19} aria-hidden="true" /></Link>
            <Link href="/app/library" className={styles.textLink}>{resume ? "Choose another topic" : "Browse study materials"}</Link>
          </div>
        </section>
        <RecentMaterials materials={recentMaterials} loading={recentLoading} error={recentError} partialError={recentPartialError} onRetry={onRetryRecent} />
      </div>

      <aside className={styles.supportColumn} aria-label="Your dates and quick notes">
        <UpcomingPanel dashboard={dashboard} />
        <QuickCapturePanel key={dashboard.user_id || "current-user"} ownerId={dashboard.user_id || "current-user"} />
      </aside>
    </div>
  );
}

function UpcomingPanel({ dashboard }: { dashboard: DashboardData }) {
  return <section className={`${styles.panel} ${styles.upcoming}`} aria-labelledby="upcoming-title">
    <div className={styles.panelHeading}><h2 id="upcoming-title">Upcoming dates</h2></div>
    {dashboard.due_tomorrow.length > 0 ? (
      <>
        <p className={styles.panelHint}>{dashboard.due_label.replace(/:$/, "") || "Your next dates"}</p>
        <ul className={styles.deadlines}>
          {dashboard.due_tomorrow.slice(0, 3).map((item, index) => (
            <li key={item.id || `${item.label}-${index}`}>
              <Link href="/app/calendar" aria-label={`Open planner: ${item.label}`}>
                <span><strong>{item.label}</strong><span className={styles.deadlineDetail}>{item.due_at ? <time dateTime={item.due_at}>{formatDate(item.due_at, dashboard.timezone)}</time> : item.detail || "View in planner"}</span></span>
                <ArrowRight size={16} aria-hidden="true" />
              </Link>
            </li>
          ))}
        </ul>
      </>
    ) : <div className={styles.emptyDates}><p>Nothing coming up</p><Link href="/app/calendar" className={styles.addDateButton} aria-label="Add a date" title="Add a date"><Plus size={17} aria-hidden="true" /></Link></div>}
    {dashboard.due_tomorrow.length > 0 && <Link href="/app/calendar" className={styles.panelLink}>Open planner<ArrowRight size={16} aria-hidden="true" /></Link>}
  </section>;
}

function RecentMaterials({ materials, loading, error, partialError, onRetry }: { materials: RecentMaterial[]; loading: boolean; error: boolean; partialError: boolean; onRetry: () => void }) {
  return <section className={styles.materials} aria-labelledby="materials-title">
    <div className={styles.sectionHeading}>
      <h2 id="materials-title">Recent materials</h2>
      <Link href="/app/library?view=files" className={styles.addLink}><Plus size={17} aria-hidden="true" /> Add material</Link>
    </div>
    {loading ? <div className={styles.materialSkeleton} role="status" aria-label="Loading recent materials">{Array.from({ length: MAX_RECENT_MATERIALS }, (_, index) => <span key={index} />)}</div>
      : error ? <div className={styles.materialMessage} role="status"><span>Recent materials aren&apos;t available right now.</span><button type="button" onClick={onRetry}>Try again</button></div>
        : <>
          {partialError && <p className={styles.partialNotice} role="status">Some recent materials couldn&apos;t load.</p>}
          {materials.length ? <ul className={styles.materialList}>
            {materials.map((material) => <li key={`${material.kind}-${material.id}`}>
              <Link href={material.href} aria-label={`Open ${material.kind}: ${material.title}`}>
                <strong className={styles.materialTitle} title={material.title}>{material.title}</strong>
                <span className={styles.materialFooter}>{material.timestamp && <time dateTime={material.timestamp}>{formatDate(material.timestamp)}</time>}<span className={styles.materialKind}>{material.kind === "note" ? "Note" : "File"}</span></span>
              </Link>
            </li>)}
          </ul> : <div className={styles.materialEmpty}><p>Your notes and files will appear here.</p><div><Link href="/app/library">Open Library</Link><Link href="/app/library?view=files">Add material</Link></div></div>}
        </>}
  </section>;
}

function formatDate(value: string, timeZone?: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Date unavailable";
  try {
    return new Intl.DateTimeFormat("en", { day: "numeric", month: "short", ...(timeZone ? { timeZone } : {}) }).format(date);
  } catch { return new Intl.DateTimeFormat("en", { day: "numeric", month: "short" }).format(date); }
}

function LoadingDashboard() {
  return <div className={styles.loading} role="status" aria-label="Loading your study dashboard">
    <div className={styles.contentGrid}>
      <div className={styles.studyColumn}>
        <div className={styles.skeletonHero} />
        <div className={styles.skeletonMaterials}>
          <span className={styles.skeletonHeading} />
          <div className={styles.materialSkeleton}>{Array.from({ length: MAX_RECENT_MATERIALS }, (_, index) => <span key={index} />)}</div>
        </div>
      </div>
      <div className={styles.supportColumn} aria-hidden="true">
        <div className={styles.skeletonUpcoming} />
        <div className={styles.skeletonQuickNote} />
      </div>
    </div>
    <span className={styles.loadingLabel}>Getting your study space ready…</span>
  </div>;
}

const WEEKDAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const WEEKDAY_INITIALS = ["S", "M", "T", "W", "T", "F", "S"];

function orderedWeekdays(timeZone?: string) {
  let todayIndex = new Date().getDay();
  if (timeZone) {
    try {
      const todayName = new Intl.DateTimeFormat("en-US", { weekday: "long", timeZone }).format(new Date());
      const accountDayIndex = WEEKDAY_NAMES.indexOf(todayName);
      if (accountDayIndex >= 0) todayIndex = accountDayIndex;
    } catch { /* Fall back to the device's local weekday for an invalid timezone. */ }
  }
  return Array.from({ length: 7 }, (_, offset) => {
    const weekdayIndex = (todayIndex + offset) % 7;
    return { offset, name: WEEKDAY_NAMES[weekdayIndex], initial: WEEKDAY_INITIALS[weekdayIndex], isToday: offset === 0 };
  });
}
