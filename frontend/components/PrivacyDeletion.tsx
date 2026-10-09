"use client";
import { useState } from "react";
import { deletePrivateAccount, prepareDeletionReceipt } from "@/lib/privacy";
import { clearSession } from "@/lib/auth";
import { supabase } from "@/lib/supabase";

export default function PrivacyDeletion() {
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function remove() {
    setBusy(true); setError(null);
    try {
      // Save the receipt before submission so a lost response cannot make the
      // subsequent anonymous status lookup inaccessible to the learner.
      const receipt = prepareDeletionReceipt();
      const url = URL.createObjectURL(new Blob([JSON.stringify(receipt, null, 2)], { type: "application/json" }));
      const link = document.createElement("a");
      link.href = url; link.download = "pixie-deletion-receipt.json"; link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      await deletePrivateAccount(password, receipt);
      setPassword("");
      // Accepted deletion always ends this UI session.
      try { clearSession(); } finally {
        await supabase.auth.signOut({ scope: "local" }).catch(() => undefined);
        window.location.replace("/login?reason=account-deleted");
      }
    } catch (cause) {
      setPassword(""); setError(cause instanceof Error ? cause.message : "Deletion could not be requested.");
      setBusy(false);
    }
  }
  if (!open) return <button type="button" className="profile-text-action" onClick={() => setOpen(true)}>Delete account</button>;
  return <section aria-labelledby="delete-account-title">
    <h3 id="delete-account-title">Permanently delete your private account</h3>
    <p>Access ends immediately. This cannot be undone. Private backup copies have a seven-day deletion target; provider cleanup may take longer. Authorized school records follow your school’s retention policy.</p>
    <p>Your receipt is downloaded before the request. It confirms deletion only when status shows the request was accepted. Keep it to check cleanup at <a href="/deletion-status">Deletion status</a>.</p>
    <label className="profile-field"><span>Current password</span><input type="password" autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} disabled={busy} /></label>
    <p>If you use Google, sign in again immediately before requesting deletion.</p>
    <label className="profile-field"><span>Type DELETE MY ACCOUNT</span><input value={confirmation} onChange={event => setConfirmation(event.target.value)} disabled={busy} /></label>
    {error && <p role="alert">{error}</p>}
    <button type="button" onClick={() => void remove()} disabled={busy || confirmation !== "DELETE MY ACCOUNT"}>{busy ? "Requesting deletion…" : "Delete and save receipt"}</button>
    <button type="button" disabled={busy} onClick={() => { setOpen(false); setPassword(""); setConfirmation(""); }}>Cancel</button>
  </section>;
}
