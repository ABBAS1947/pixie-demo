"use client";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="account-area-shell learner-app-shell">
      <div className="learner-app-main scrollbar-subtle">{children}</div>
    </div>
  );
}
