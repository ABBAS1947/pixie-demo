/** Public build setting only. No secret or dynamic third-party token destination. */
function configuredOrigin(): string {
  const value = process.env.NEXT_PUBLIC_API_URL?.trim()
    || (typeof window !== "undefined" ? window.location.origin : "http://127.0.0.1:9000");
  const url = new URL(value);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
    throw new Error("The backend URL configuration is invalid.");
  }
  if (typeof window !== "undefined" && window.location.protocol === "https:" && url.protocol !== "https:") {
    throw new Error("A secure frontend requires a secure backend URL.");
  }
  return value.replace(/\/$/, "");
}
export const API_URL = configuredOrigin();
