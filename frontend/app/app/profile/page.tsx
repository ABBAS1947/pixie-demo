"use client";

import { Fragment, useEffect, useState } from "react";
import { Award, Flame } from "lucide-react";
import UserAvatar from "@/components/UserAvatar";
import { fetchMe } from "@/lib/api";
import { fetchDashboard, type DashboardData } from "@/lib/dashboard";
import { supabase } from "@/lib/supabase";
import type { User } from "@/lib/types";

const FIRST_STREAK_GOAL = 3;
const FIRST_RANK_NAME = "Apprentice";
const FIRST_RANK_XP = 40;
const STREAK_MILESTONES = [3, 7, 14, 20, 30, 60, 100];

function joinedMonth(createdAt: string | null): string | null {
  if (!createdAt) return null;
  const date = new Date(createdAt);
  if (!Number.isFinite(date.getTime())) return null;
  return new Intl.DateTimeFormat(undefined, { month: "long", year: "numeric" }).format(date);
}

export default function PublicProfilePage() {
  const [user, setUser] = useState<User | null>(null);
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [joined, setJoined] = useState<string | null>(null);
  const [avatarBackground, setAvatarBackground] = useState<string | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let alive = true;
    Promise.all([fetchMe(), fetchDashboard(), supabase.auth.getUser()]).then(([me, data, auth]) => {
      if (!alive) return;
      setUser(me);
      setDashboard(data);
      setJoined(joinedMonth(auth.data.user?.created_at ?? null));
    }).catch(() => { if (alive) setError(true); });
    return () => { alive = false; };
  }, []);

  const streakEarned = Boolean(dashboard?.streak_milestones?.includes(FIRST_STREAK_GOAL));
  const rankEarned = Boolean(dashboard && dashboard.rank_name !== "Novice");
  const streakProgress = streakEarned ? FIRST_STREAK_GOAL : Math.min(dashboard?.streak_days ?? 0, FIRST_STREAK_GOAL);
  const rankProgress = rankEarned ? FIRST_RANK_XP : Math.min(dashboard?.xp ?? 0, FIRST_RANK_XP);
  const nextStreakGoal = dashboard
    ? dashboard.next_streak_goal !== undefined
      ? dashboard.next_streak_goal
      : STREAK_MILESTONES.find((goal) => dashboard.streak_days < goal) ?? null
    : null;
  const displayStreakGoal = nextStreakGoal ?? 100;
  const previousStreakGoal = nextStreakGoal === null
    ? 60
    : dashboard?.previous_streak_goal ?? Math.max(...STREAK_MILESTONES.filter((goal) => goal < nextStreakGoal), 0);
  const milestoneProgress = nextStreakGoal
    ? Math.min(Math.max(0, (dashboard?.streak_days ?? 0) - previousStreakGoal), nextStreakGoal - previousStreakGoal)
    : displayStreakGoal - previousStreakGoal;
  const milestoneSpan = displayStreakGoal - previousStreakGoal;
  const milestoneRows = Array.from({ length: Math.ceil(milestoneSpan / 10) }, (_, row) => {
    const firstDay = previousStreakGoal + row * 10 + 1;
    const lastDay = Math.min(firstDay + 9, displayStreakGoal);
    return { firstDay, lastDay };
  });

  return (
    <main className="account-area-main">
        <div className="pixie-profile-page account-area-content">
          {error ? <section className="profile-card" role="alert"><h1>Profile unavailable</h1><p>We couldn’t load your profile. Please refresh and try again.</p></section>
            : !user || !dashboard ? <ProfileLoadingSkeleton />
              : <>
                <section className="pixie-profile-identity" aria-label="Your profile">
                  <div className="pixie-profile-avatar" style={avatarBackground ? { backgroundColor: avatarBackground } : undefined}>
                    <UserAvatar userId={user.user_id} alt="" width={348} height={348} onBackgroundColor={setAvatarBackground} />
                  </div>
                  <h1>{user.name || "Your name"}</h1>
                  {joined && <p>Joined {joined}</p>}
                </section>

                <section className="pixie-profile-stats" aria-label="Learning statistics">
                  <article><span className="pixie-profile-stat-icon streak" aria-hidden="true" /><div><strong>{dashboard.streak_days}</strong><span>Day streak</span></div></article>
                  <article><span className="pixie-profile-stat-icon xp" aria-hidden="true" /><div><strong>{dashboard.xp.toLocaleString()}</strong><span>Total XP</span></div></article>
                  <article><span className="pixie-profile-stat-icon rank" aria-hidden="true" /><div><strong>{dashboard.rank_name}</strong><span>Current rank</span></div></article>
                </section>

                <section className={`pixie-next-streak${milestoneSpan <= 7 ? " is-short" : ""}${milestoneSpan <= 4 ? " is-few" : ""}`} aria-labelledby="next-streak-title">
                  <div className="pixie-next-streak-summary">
                    <Flame size={38} fill="currentColor" aria-hidden="true" />
                    <div>
                      <span>{nextStreakGoal === null ? "Milestone reached" : "Next milestone"}</span>
                      <h2 id="next-streak-title">{displayStreakGoal}-day streak</h2>
                      <p>{nextStreakGoal === null ? "Completed" : <><strong>{milestoneProgress}</strong> of {milestoneSpan} days</>}</p>
                      {dashboard.streak_days === 0 && <span className="pixie-next-streak-hint">Learn with Pixie today to begin.</span>}
                    </div>
                  </div>
                  <div className="pixie-next-streak-days" role="img" aria-label={nextStreakGoal === null ? `${displayStreakGoal}-day streak milestone reached` : `${milestoneProgress} of ${milestoneSpan} days completed toward the ${displayStreakGoal}-day streak milestone`}>
                    {milestoneRows.map(({ firstDay, lastDay }) => (
                      <div className="pixie-next-streak-row" key={firstDay}>
                        {milestoneSpan > 7 && <span>Days {firstDay}–{lastDay}</span>}
                        <div className="pixie-next-streak-track" aria-hidden="true">
                          {Array.from({ length: lastDay - firstDay + 1 }, (_, index) => {
                            const day = firstDay + index;
                            return <Fragment key={day}>
                              <span className={`pixie-next-streak-dot${day <= dashboard.streak_days ? " is-complete" : nextStreakGoal !== null && day === dashboard.streak_days + 1 ? " is-next" : ""}`}>{milestoneSpan <= 7 ? day : null}</span>
                              {day < lastDay && <span className={`pixie-next-streak-link${day < dashboard.streak_days ? " is-complete" : ""}`} />}
                            </Fragment>;
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                </section>

                <section className="pixie-profile-achievements" aria-labelledby="profile-achievements-title">
                  <h2 id="profile-achievements-title">Achievements</h2>
                  <div className="pixie-achievement-list">
                    <article className={`pixie-achievement ${streakEarned ? "is-earned" : ""}`}>
                      <span className="pixie-achievement-art flame"><Flame size={27} fill="currentColor" aria-hidden="true" /></span>
                      <div className="pixie-achievement-copy"><div className="pixie-achievement-heading"><h3>Steady Start</h3><span>{streakEarned ? "Earned" : `${streakProgress}/${FIRST_STREAK_GOAL}`}</span></div><progress value={streakProgress} max={FIRST_STREAK_GOAL} aria-label={`Steady Start: ${streakEarned ? "earned" : `${streakProgress} of ${FIRST_STREAK_GOAL} streak days`}`} /><p>{streakEarned ? "Reached your first 3-day streak" : "Reach your first 3-day streak"}</p></div>
                    </article>
                    <article className={`pixie-achievement ${rankEarned ? "is-earned" : ""}`}>
                      <span className="pixie-achievement-art promotion"><Award size={26} aria-hidden="true" /></span>
                      <div className="pixie-achievement-copy"><div className="pixie-achievement-heading"><h3>First Promotion</h3><span>{rankEarned ? "Earned" : `${rankProgress}/${FIRST_RANK_XP} XP`}</span></div><progress value={rankProgress} max={FIRST_RANK_XP} aria-label={`First Promotion: ${rankProgress} of ${FIRST_RANK_XP} XP`} /><p>Reach {FIRST_RANK_NAME} rank</p></div>
                    </article>
                  </div>
                </section>
              </>}
        </div>
    </main>
  );
}

function ProfileLoadingSkeleton() {
  return (
    <div className="pixie-profile-skeleton" role="status" aria-label="Loading your profile" aria-busy="true">
      <span className="sr-only">Loading your profile…</span>
      <div className="pixie-profile-skeleton-avatar" aria-hidden="true" />
      <div className="pixie-profile-skeleton-name" aria-hidden="true" />
      <div className="pixie-profile-skeleton-date" aria-hidden="true" />
      <div className="pixie-profile-skeleton-stats" aria-hidden="true">
        {[0, 1, 2].map((item) => (
          <div className="pixie-profile-skeleton-stat" key={item}>
            <span />
            <div><i /><i /></div>
          </div>
        ))}
      </div>
      <div className="pixie-profile-skeleton-milestone" aria-hidden="true">
        <div className="pixie-profile-skeleton-milestone-summary"><i /><div><span /><span /><span /></div></div>
        <div className="pixie-profile-skeleton-milestone-dots"><i /><i /><i /></div>
      </div>
      <div className="pixie-profile-skeleton-heading" aria-hidden="true" />
      <div className="pixie-profile-skeleton-achievements" aria-hidden="true">
        {[0, 1].map((item) => (
          <div className="pixie-profile-skeleton-achievement" key={item}>
            <span />
            <div><i /><i /><i /></div>
          </div>
        ))}
      </div>
    </div>
  );
}
