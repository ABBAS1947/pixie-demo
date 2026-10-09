import { redirect } from "next/navigation";

// Canonical teacher entry point. Keep the old route as a compatibility redirect.
export default function TeacherOverviewRedirect() {
  redirect("/school/dashboard");
}
