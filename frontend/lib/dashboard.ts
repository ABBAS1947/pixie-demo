// Dashboard API client — fetches all data for the student home screen.

import { apiFetch } from "./apiRequest";

import { API_URL } from "./apiOrigin";

export interface BehindTopic {
  name: string;
  topic: string;
  score: number;
}

export interface DeadlineItem {
  label: string;
  detail: string;
  id?: string;
  due_at?: string;
}

export interface RecentActivityItem {
  title: string;
  subtitle: string;
}

export interface DashboardData {
  // Optional until an announcement delivery service is connected.
  announcement?: { id: string; title: string; message: string; href?: string; action_label?: string; expires_at?: string } | null;
  user_id: string;
  student_name: string;
  day: number;
  rank_name: string;
  xp: number;
  streak_days: number;
  next_streak_goal?: number | null;
  previous_streak_goal?: number;
  streak_earned: number[];
  streak_milestones?: number[];
  behind_topics: BehindTopic[];
  continue_topic: string | null;
  continue_session_id?: string | null;
  timezone?: string;
  catch_up_detail: string | null;
  due_label: string;
  due_tomorrow: DeadlineItem[];
  recent_activity: RecentActivityItem;
}

export async function fetchDashboard(): Promise<DashboardData> {
  const res = await apiFetch(`${API_URL}/api/dashboard`, {
  });
  if (!res.ok) {
    throw new Error(`Dashboard fetch failed: ${res.statusText}`);
  }
  return res.json();
}
