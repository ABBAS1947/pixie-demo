"use client";
import { useState, type FormEvent } from "react";
import { checkDeletion } from "@/lib/privacy";

export default function DeletionStatus() {
  const [id, setId] = useState(""); const [receipt, setReceipt] = useState("");
  const [message, setMessage] = useState(""); const [busy, setBusy] = useState(false);
  async function check(event: FormEvent) {
    event.preventDefault(); setBusy(true); setMessage("");
    try { const status = await checkDeletion(id, receipt); setMessage(status.complete ? "Cleanup is complete." : "Account access is revoked. Cleanup is still in progress."); }
    catch (cause) { setMessage(cause instanceof Error ? cause.message : "Status is temporarily unavailable."); }
    finally { setBusy(false); }
  }
  return <main style={{ maxWidth: 600, margin: "60px auto", padding: 24 }}><h1>Deletion status</h1>
    <p>Use the request ID and receipt from your downloaded deletion receipt. You do not need to sign in.</p>
    <form onSubmit={event => void check(event)}>
      <label className="profile-field"><span>Request ID</span><input required value={id} onChange={event => setId(event.target.value)} /></label>
      <label className="profile-field"><span>Receipt</span><input required type="password" autoComplete="off" value={receipt} onChange={event => setReceipt(event.target.value)} /></label>
      <button disabled={busy}>{busy ? "Checking…" : "Check status"}</button>
    </form><p role="status">{message}</p><a href="/login">Back to login</a></main>;
}
