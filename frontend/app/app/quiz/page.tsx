"use client";

import { useRouter, useSearchParams } from "next/navigation";
import ReviewFlow from "./components/ReviewFlow";

/** Static-export compatible route: session identity is safe to restore from the URL. */
export default function ReviewPage() {
  const router = useRouter();
  const params = useSearchParams();
  const sessionId = params.get("session");

  function changeSession(id: string | null, complete = false) {
    router.replace(id ? `/app/quiz?session=${id}${complete ? "&summary=1" : ""}` : "/app/quiz");
  }

  return <ReviewFlow initialSessionId={sessionId} onSessionChange={changeSession}/>;
}
