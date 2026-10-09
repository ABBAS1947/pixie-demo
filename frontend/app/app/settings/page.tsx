"use client";
import PrivacyDeletion from "@/components/PrivacyDeletion";

import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Check, LogOut } from "lucide-react";
import { useRouter } from "next/navigation";
import Dialog from "@/components/Dialog";
import { fetchMe, fetchPrivacyStatement, updateOnboarding, type PrivacyStatement } from "@/lib/api";
import { clearSession } from "@/lib/auth";
import { supabase } from "@/lib/supabase";
import type { Tone, User } from "@/lib/types";
import { getReviewConfig, updateReviewPreferences, type ReviewPreferences } from "@/lib/reviewApi";

const TONES: { value: Tone; label: string; description: string }[] = [
  { value: "calm_steady", label: "Calm and steady", description: "Patient explanations with no rush." },
  { value: "playful_sarcastic", label: "Playful and witty", description: "Light energy and a little teasing." },
  { value: "blunt", label: "Blunt and direct", description: "Clear feedback without sugarcoating." },
];

function LoadingProfile() {
  return <main className="account-area-main"><div className="profile-loading"><div className="profile-loading-orb">✦</div><p>Loading your settings…</p></div></main>;
}

export default function Settings() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [email, setEmail] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [grade, setGrade] = useState("");
  const [tone, setTone] = useState<Tone>("calm_steady");
  const [constraints, setConstraints] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dialog, setDialog] = useState<"logout" | null>(null);
  const [showPasswordForm, setShowPasswordForm] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordSaving, setPasswordSaving] = useState(false);
  const [passwordMessage, setPasswordMessage] = useState<string | null>(null);
  const [reviewPreferences, setReviewPreferences] = useState<ReviewPreferences | null>(null);
  const [savingReviewPreference, setSavingReviewPreference] = useState(false);
  const [reviewPreferencesError, setReviewPreferencesError] = useState<string | null>(null);
  const [privacyStatement, setPrivacyStatement] = useState<PrivacyStatement | null>(null);
  const [privacyOpen, setPrivacyOpen] = useState(false);
  const [privacyLoading, setPrivacyLoading] = useState(false);
  const [privacyError, setPrivacyError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetchMe()
      .then((me) => {
        if (!alive) return;
        setUser(me);
        setName(me.name || "");
        setGrade(me.grade_level || "");
        setTone((me as User & { tone?: Tone }).tone || "calm_steady");
        setConstraints((me as User & { resource_constraints?: string }).resource_constraints || "");
      })
      .catch((cause) => {
        if (alive) setError(cause instanceof Error ? cause.message : "Your profile could not be loaded.");
      });
    supabase.auth.getUser().then(({ data }) => {
      if (alive) setEmail(data.user?.email ?? null);
    }).catch(() => { if (alive) setEmail(null); });
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    let alive = true;
    getReviewConfig()
      .then((config) => { if (alive) setReviewPreferences(config.preferences); })
      .catch(() => { if (alive) setReviewPreferencesError("Learning settings couldn't be loaded."); });
    return () => { alive = false; };
  }, []);

  async function changeReviewPreference<K extends keyof ReviewPreferences>(key: K, value: ReviewPreferences[K]) {
    if (!reviewPreferences || savingReviewPreference) return;
    const previous = reviewPreferences;
    setReviewPreferences({ ...previous, [key]: value });
    setReviewPreferencesError(null);
    setSavingReviewPreference(true);
    try {
      const updated = await updateReviewPreferences({ [key]: value });
      setReviewPreferences(updated);
    } catch (cause) {
      setReviewPreferences(previous);
      setReviewPreferencesError(cause instanceof Error ? cause.message : "That preference couldn't be saved.");
    } finally {
      setSavingReviewPreference(false);
    }
  }

  async function togglePrivacyDetails() {
    if (privacyOpen) { setPrivacyOpen(false); return; }
    setPrivacyOpen(true);
    if (privacyStatement || privacyLoading) return;
    setPrivacyLoading(true);
    setPrivacyError(null);
    try { setPrivacyStatement(await fetchPrivacyStatement()); }
    catch (cause) { setPrivacyError(cause instanceof Error ? cause.message : "Privacy details couldn't be loaded."); }
    finally { setPrivacyLoading(false); }
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await updateOnboarding({
        name: name.trim(),
        grade_level: grade.trim(),
        tone,
        resource_constraints: constraints.trim() || null,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      });
      setUser((current) => current ? { ...current, name: name.trim(), grade_level: grade.trim() } : current);
      setSaved(true);
      window.setTimeout(() => setSaved(false), 2200);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Your changes could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  async function updatePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPasswordMessage(null);
    if (!email) {
      setPasswordMessage("We couldn't verify the email for this account. Sign in again and retry.");
      return;
    }
    if (newPassword.length < 6) {
      setPasswordMessage("Use at least 6 characters for your new password.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordMessage("The new passwords don't match.");
      return;
    }

    setPasswordSaving(true);
    try {
      const { error: reauthError } = await supabase.auth.signInWithPassword({ email, password: currentPassword });
      if (reauthError) throw new Error("Current password is incorrect.");
      const { error: updateError } = await supabase.auth.updateUser({ password: newPassword });
      if (updateError) throw updateError;
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setShowPasswordForm(false);
      setPasswordMessage("Password updated.");
    } catch (cause) {
      setPasswordMessage(cause instanceof Error ? cause.message : "Password could not be updated. Try again.");
    } finally {
      setPasswordSaving(false);
    }
  }

  async function logout() {
    setDialog(null);
    clearSession();
    try { await supabase.auth.signOut(); } catch { /* Local session still clears. */ }
    router.replace("/login");
  }

  if (!user) {
    return error ? <main className="account-area-main"><div className="profile-error"><h1>Settings unavailable</h1><p>{error}</p><button type="button" className="profile-primary" onClick={() => window.location.reload()}>Try again</button></div></main> : <LoadingProfile />;
  }

  return (
    <>
      <main className="account-area-main">
      <div className="profile-frame account-area-content">
        <header className="account-area-heading"><p className="profile-eyebrow">Make Pixie work for you</p><h1>Settings</h1></header>
        <nav className="account-settings-nav" aria-label="Settings sections">
          <a href="#account-profile">Account profile</a><a href="#preferences">Preferences</a><a href="#appearance">Appearance</a><a href="#data-privacy">Privacy &amp; data</a>
        </nav>
        {error && <div className="profile-alert" role="alert">{error}<button type="button" onClick={() => setError(null)} aria-label="Dismiss">×</button></div>}

        <div className="profile-content">
          <section className="profile-card" id="account-profile">
            <div className="profile-section-head"><div><p className="profile-eyebrow">Account</p><h2>Profile details</h2></div></div>
            <label className="profile-field"><span>Name</span><input value={name} onChange={(event) => setName(event.target.value)} placeholder="Your name" /></label>
            <label className="profile-field"><span>Grade level</span><input value={grade} onChange={(event) => setGrade(event.target.value)} placeholder="e.g. Grade 10" /></label>
            <label className="profile-field"><span>Learning preferences <small>Optional</small></span><textarea value={constraints} onChange={(event) => setConstraints(event.target.value)} placeholder="Tell Pixie what helps you learn best…" rows={3} /></label>
          </section>

          <section className="profile-card profile-account" id="account-security">
            <div className="profile-section-head"><h2>Account</h2></div>
            <div className="profile-row profile-row-static"><span className="profile-row-label">Email</span><span className="profile-row-value profile-email" title={email || undefined}>{email || "Not available"}</span></div>
            <div className="profile-row profile-row-static profile-password-row"><span className="profile-row-label">Password</span><button type="button" className="profile-text-action" onClick={() => { setShowPasswordForm((shown) => !shown); setPasswordMessage(null); }}>{showPasswordForm ? "Cancel" : "Update password"}</button></div>
            {showPasswordForm && <form className="profile-password-form" onSubmit={(event) => void updatePassword(event)}>
              <label className="profile-field"><span>Current password</span><input type="password" autoComplete="current-password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} required /></label>
              <label className="profile-field"><span>New password</span><input type="password" autoComplete="new-password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} minLength={6} required /></label>
              <label className="profile-field"><span>Confirm new password</span><input type="password" autoComplete="new-password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} minLength={6} required /></label>
              {passwordMessage && <p className="profile-password-message" role="status">{passwordMessage}</p>}
              <button type="submit" className="profile-password-submit" disabled={passwordSaving}>{passwordSaving ? "Updating…" : "Save password"}</button>
            </form>}
            {!showPasswordForm && passwordMessage && <p className="profile-password-message" role="status">{passwordMessage}</p>}
          </section>

          <section className="profile-card" id="preferences">
            <div className="profile-section-head"><div><p className="profile-eyebrow">Personalize Pixie</p><h2>Tutor tone</h2></div></div>
            <p className="profile-section-description">Choose how Pixie communicates with you.</p>
            <div className="profile-tone-list" role="group" aria-label="Tutor tone">
              {TONES.map((option) => <button key={option.value} type="button" className={`profile-tone ${tone === option.value ? "is-selected" : ""}`} aria-pressed={tone === option.value} onClick={() => setTone(option.value)}><span><b>{option.label}</b><small>{option.description}</small></span>{tone === option.value && <Check size={18} aria-label="Selected" />}</button>)}
            </div>
          </section>

          <section className="profile-card" id="learning-preferences">
            <div className="profile-section-head"><div><p className="profile-eyebrow">Your experience</p><h2>Learning preferences</h2></div></div>
            <p className="profile-section-description">These choices affect Review sessions and can be changed anytime.</p>
            {reviewPreferences ? <div className="profile-preference-list">
              <label className="profile-preference"><span><b>XP penalties</b><small>Allow XP to decrease for low quiz scores.</small></span><input type="checkbox" disabled={savingReviewPreference} checked={reviewPreferences.penalties_enabled} onChange={(event) => void changeReviewPreference("penalties_enabled", event.target.checked)} /></label>
              <label className="profile-preference"><span><b>Reduced motion</b><small>Limit movement and transition effects in Review.</small></span><input type="checkbox" disabled={savingReviewPreference} checked={reviewPreferences.reduced_motion} onChange={(event) => void changeReviewPreference("reduced_motion", event.target.checked)} /></label>
              <label className="profile-preference"><span><b>Shorter text</b><small>Prefer more concise text in Review.</small></span><input type="checkbox" disabled={savingReviewPreference} checked={reviewPreferences.reduced_text} onChange={(event) => void changeReviewPreference("reduced_text", event.target.checked)} /></label>
              <label className="profile-preference"><span><b>Allow AI processing of study material</b><small>When enabled, selected study text may be sent to Pixie&apos;s configured AI provider for summaries, file extraction and classification, and Review activities.</small></span><input type="checkbox" disabled={savingReviewPreference} checked={reviewPreferences.external_processing_consent} onChange={(event) => void changeReviewPreference("external_processing_consent", event.target.checked)} /></label>
              {reviewPreferencesError && <p className="profile-inline-message" role="status">{reviewPreferencesError}</p>}
            </div> : <p className="profile-inline-message" role="status">{reviewPreferencesError || "Loading learning preferences…"}</p>}
          </section>

          <section className="profile-card" id="data-privacy">
            <div className="profile-section-head"><div><p className="profile-eyebrow">Your information</p><h2>Data &amp; privacy</h2></div></div>
            <p className="profile-section-description">See what Pixie stores, where it is kept, and who may access it.</p>
            <button type="button" className="profile-text-action profile-privacy-toggle" aria-expanded={privacyOpen} onClick={() => void togglePrivacyDetails()}>{privacyOpen ? "Hide privacy details" : "View privacy details"}</button>
            {privacyOpen && <div className="profile-privacy-details" aria-live="polite">
              {privacyLoading && <p>Loading privacy details…</p>}
              {privacyError && <p className="profile-inline-message" role="alert">{privacyError}</p>}
              {privacyStatement && <>
                <h3>Information stored</h3><ul>{privacyStatement.stored.map((item) => <li key={item}>{item}</li>)}</ul>
                <h3>Storage</h3><p>{privacyStatement.location}</p>
                <h3>Who may access it</h3><ul>{privacyStatement.viewers.map((item) => <li key={item}>{item}</li>)}</ul>
                <h3>Commitments</h3><ul>{privacyStatement.commitments.map((item) => <li key={item}>{item}</li>)}</ul>
              </>}
            </div>}
          </section>

          <section className="profile-card" id="appearance">
            <div className="profile-section-head"><div><p className="profile-eyebrow">Display</p><h2>Appearance</h2></div></div>
            <p className="profile-section-description">Pixie currently uses its standard light appearance. Additional theme choices will be added when they can be applied consistently across the app.</p>
          </section>

          <button type="button" className="profile-save" onClick={() => void save()} disabled={saving}>{saving ? "Saving…" : saved ? <><Check size={17} /> Saved</> : "Save changes"}</button>
          <section className="profile-danger">
            <button type="button" className="profile-logout" onClick={() => setDialog("logout")}><LogOut size={17} aria-hidden="true" />Log out</button>
            <PrivacyDeletion />
          </section>
        </div>
      </div>
      </main>
      <Dialog open={dialog === "logout"} title="Log out of Pixie?" message="Your notes, streak, and learning progress stay safe. You can sign back in whenever you are ready." confirmLabel="Log out" cancelLabel="Stay signed in" onConfirm={() => void logout()} onCancel={() => setDialog(null)} />
    </>
  );
}
