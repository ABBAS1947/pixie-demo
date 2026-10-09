"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import ComposerCard, { type ComposerMode } from "@/components/chat/ComposerCard";
import { fetchDashboard } from "@/lib/dashboard";

/**
 * Legacy new-session landing retained for its existing callers.
 */
export default function NewChatLanding() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const d = await fetchDashboard();
        setName(d.student_name);
      } catch (e) {
        console.error(e);
      } finally {
        setReady(true);
      }
    })();
  }, [router]);

  function greeting(): string {
    const h = new Date().getHours();
    if (h < 12) return "Morning";
    if (h < 17) return "Afternoon";
    return "Evening";
  }

  function handleSend(text: string, mode: ComposerMode) {
    router.push(`/app/chat?compose=${encodeURIComponent(text)}&mode=${mode}`);
  }

  if (!ready) return null;

  return (
    <div
      className="w-full flex justify-center"
      style={{ backgroundColor: "var(--color-background)", minHeight: "100dvh" }}
    >
      <div
        className="w-full flex flex-col"
        style={{
          maxWidth: 1440,
          minHeight: "100dvh",
          padding: "var(--gutter-y) var(--gutter-x)",
        }}
      >
        <div
          className="w-full flex flex-col items-center"
          style={{
            width: "min(100%, var(--content-chat))",
            marginInline: "auto",
            flex: 1,
            justifyContent: "center",
            gap: 19,
            paddingBottom: 26,
          }}
        >
          <h1 className="font-greeting text-center">
            {greeting()}{name ? `, ${name}` : ""}
          </h1>
          <ComposerCard onSend={handleSend} />
        </div>
      </div>
    </div>
  );
}
