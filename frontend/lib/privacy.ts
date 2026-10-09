import { apiFetch } from "./apiRequest";
import { API_URL } from "./apiOrigin";

async function result<T>(response: Response): Promise<T> {
  const body = await response.json();
  if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "The request could not be completed.");
  return body as T;
}

export interface DeletionReceipt { request_id: string; receipt: string; state: string; access_revoked: boolean }

export function prepareDeletionReceipt(): DeletionReceipt {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  const receipt = btoa(Array.from(bytes, byte => String.fromCharCode(byte)).join(""))
    .replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
  return { request_id: crypto.randomUUID(), receipt, state: "prepared", access_revoked: false };
}

export async function deletePrivateAccount(password: string, prepared: DeletionReceipt): Promise<DeletionReceipt> {
  const proof = await result<{ reauthentication: string }>(await apiFetch(`${API_URL}/privacy/reauthenticate`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(password ? { password } : {}),
  }));
  return result(await apiFetch(`${API_URL}/privacy/deletions`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ request_id: prepared.request_id, receipt: prepared.receipt,
      confirmation: "DELETE MY ACCOUNT", reauthentication: proof.reauthentication }),
  }));
}

export async function checkDeletion(requestId: string, receipt: string): Promise<{ state: string; complete: boolean }> {
  // Anonymous receipt lookup must not refresh or restore a deleted auth session.
  return result(await fetch(`${API_URL}/privacy/deletions/${encodeURIComponent(requestId)}`, {
    headers: { "X-Deletion-Receipt": receipt }, cache: "no-store", credentials: "omit",
  }));
}
