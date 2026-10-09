import { redirect } from "next/navigation";

/**
 * Old app route — redirects to new dashboard.
 */
export default function AppPage() {
  redirect("/dashboard");
}
