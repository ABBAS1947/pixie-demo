"use client";

import { useState, useRef, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Eye, EyeOff, Loader2 } from "lucide-react";
import { fetchMe } from "@/lib/api";
import { postLoginPath, setCachedUser } from "@/lib/auth";
import { supabase } from "@/lib/supabase";
import type { AuthAudience, AuthMode } from "../page";

interface Props {
  mode: AuthMode;
  onModeChange: (m: AuthMode) => void;
  initialError?: string | null;
  audience?: AuthAudience;
}

type Step = "credentials" | "code";

const EMAIL_RE = /^\S+@\S+\.\S+$/;

export default function AuthForm({ mode, onModeChange, initialError, audience = "student" }: Props) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const isLogin = mode === "login";
  const isTeacherLogin = audience === "teacher";

  const [step, setStep] = useState<Step>("credentials");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [code, setCode] = useState(["", "", "", "", "", ""]);
  const [fieldErrors, setFieldErrors] = useState<{email?: string; password?: string}>({});
  const [authError, setAuthError] = useState<string | null>(initialError || null);
  const [busy, setBusy] = useState(false);
  const [resendTimer, setResendTimer] = useState(0);

  const codeRefs = [
    useRef<HTMLInputElement>(null),
    useRef<HTMLInputElement>(null),
    useRef<HTMLInputElement>(null),
    useRef<HTMLInputElement>(null),
    useRef<HTMLInputElement>(null),
    useRef<HTMLInputElement>(null),
  ];

  // Resend cooldown
  useEffect(() => {
    if (resendTimer <= 0) return;
    const t = setTimeout(() => setResendTimer(resendTimer - 1), 1000);
    return () => clearTimeout(t);
  }, [resendTimer]);

  useEffect(() => {
    if (initialError) setAuthError(initialError);
  }, [initialError]);

  // Focus first code input when step changes
  useEffect(() => {
    if (step === "code") codeRefs[0].current?.focus();
  }, [step]);

  const isEmailValid = EMAIL_RE.test(email.trim());
  const isCredentialsValid = isEmailValid && password.length > 0;
  const isCodeValid = code.every((d) => d.length === 1);

  // Step 1: Submit email + password, Supabase sends OTP code
  async function handleCredentials(e: React.FormEvent) {
    e.preventDefault();
    setAuthError(null);

    const errs: {email?: string; password?: string} = {};
    if (!isEmailValid) errs.email = "That email doesn't look right.";
    if (password.length < 6) errs.password = "Password needs at least 6 characters.";
    setFieldErrors(errs);
    if (Object.keys(errs).length > 0) return;

    setBusy(true);
    try {
      if (isLogin) {
        // Login: try password first, if email not confirmed, send OTP
        const { error } = await supabase.auth.signInWithPassword({
          email: email.trim(),
          password,
        });

        if (error) {
          // If email not confirmed, send OTP for verification
          if (error.message.includes("Email not confirmed")) {
            const { error: otpError } = await supabase.auth.signInWithOtp({
              email: email.trim(),
            });
            if (otpError) throw otpError;
            setStep("code");
            setResendTimer(60);
            return;
          }
          throw error;
        }

        // Password login succeeded — sync token
        const { data: { session } } = await supabase.auth.getSession();
        if (session?.access_token) {
          const me = await fetchMe();
          if (isTeacherLogin && !me.is_teacher) {
            await supabase.auth.signOut();
            throw new Error("This account does not have teacher access.");
          }
          setCachedUser(me.name);
          const fallback = isTeacherLogin || me.is_teacher ? "/school/dashboard" : me.grade_level ? "/app" : "/onboarding";
          router.replace(postLoginPath(searchParams.get("next"), fallback.startsWith("/school/") ? "teacher" : "student", fallback));
        }
      } else {
        // Signup: create account, Supabase sends verification code
        const { error } = await supabase.auth.signUp({
          email: email.trim(),
          password,
        });
        if (error) throw error;

        // Signup succeeded — show code input for email verification
        setStep("code");
        setResendTimer(60);
      }
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setBusy(false);
    }
  }

  // Step 2: Verify OTP code
  async function handleVerifyCode() {
    setAuthError(null);
    if (!isCodeValid) {
      setAuthError("Enter all 6 digits.");
      return;
    }

    setBusy(true);
    try {
      const { error } = await supabase.auth.verifyOtp({
        email: email.trim(),
        token: code.join(""),
        type: "email",
      });
      if (error) throw error;

      // Verification succeeded — sync token
      const { data: { session } } = await supabase.auth.getSession();
      if (session?.access_token) {
        const me = await fetchMe();
        if (isTeacherLogin && !me.is_teacher) {
          await supabase.auth.signOut();
          throw new Error("This account does not have teacher access.");
        }
        setCachedUser(me.name);
        const fallback = isTeacherLogin || me.is_teacher ? "/school/dashboard" : me.grade_level ? "/app" : "/onboarding";
        router.replace(postLoginPath(searchParams.get("next"), fallback.startsWith("/school/") ? "teacher" : "student", fallback));
      }
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : "Verification failed");
    } finally {
      setBusy(false);
    }
  }

  // Resend OTP
  async function handleResend() {
    if (resendTimer > 0) return;
    setAuthError(null);
    setBusy(true);
    try {
      const { error } = await supabase.auth.signInWithOtp({ email: email.trim() });
      if (error) throw error;
      setResendTimer(60);
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : "Failed to resend code");
    } finally {
      setBusy(false);
    }
  }

  function handleCodeInput(idx: number, value: string) {
    const pasted = value.replace(/\D/g, "");

    // iOS autofill / paste: multi-digit input goes across fields
    if (pasted.length > 1) {
      const newCode = [...code];
      for (let i = 0; i < Math.min(pasted.length, 6 - idx); i++) {
        newCode[idx + i] = pasted[i];
      }
      setCode(newCode);
      const lastIdx = Math.min(idx + pasted.length - 1, 5);
      codeRefs[lastIdx].current?.focus();
      if (newCode.every((d) => d.length === 1)) {
        setTimeout(() => handleVerifyCode(), 100);
      }
      return;
    }

    // Single digit
    const digit = pasted.slice(-1);
    const newCode = [...code];
    newCode[idx] = digit;
    setCode(newCode);

    if (digit && idx < 5) codeRefs[idx + 1].current?.focus();

    // Auto-submit when all 6 digits entered
    if (digit && idx === 5 && newCode.every((d) => d.length === 1)) {
      setTimeout(() => handleVerifyCode(), 100);
    }
  }

  function handleCodeKeyDown(idx: number, e: React.KeyboardEvent) {
    if (e.key === "Backspace" && !code[idx] && idx > 0) {
      codeRefs[idx - 1].current?.focus();
    }
  }

  function handlePaste(e: React.ClipboardEvent) {
    e.preventDefault();
    const pasted = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6);
    if (pasted.length === 6) {
      const newCode = pasted.split("");
      setCode(newCode);
      codeRefs[5].current?.focus();
      setTimeout(() => handleVerifyCode(), 100);
    }
  }

  return (
    <div className="mx-auto w-full max-w-sm">
      {/* 3D button CSS */}
      <style dangerouslySetInnerHTML={{ __html: authFormCSS }} />

      <div className="hidden lg:block">
        <h1 style={{ fontFamily: "'DM Sans', system-ui, sans-serif", fontSize: "28px", fontWeight: 700, lineHeight: 1.2, color: "var(--auth-ink)" }}>
          {step === "credentials"
            ? isLogin
              ? "Welcome back."
              : "Let's get you set up."
            : "Check your email."}
        </h1>
        {step === "code" && <p style={{ fontFamily: "'DM Sans', system-ui, sans-serif", fontSize: "14px", color: "var(--auth-muted)", marginTop: "8px" }}>We sent a 6-digit code to {email}</p>}
      </div>

      {step === "credentials" ? (
        <form className="mt-8 flex flex-col gap-5" onSubmit={handleCredentials} noValidate>
          <label className="flex flex-col gap-1.5">
            <span className="sr-only">Email</span>
            <input
              className="auth-input"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Email"
              autoComplete="email"
              autoFocus
            />
            {fieldErrors.email ? (
              <span style={{ fontFamily: "'DM Sans', system-ui, sans-serif", fontSize: "13px", color: "var(--auth-error)" }}>{fieldErrors.email}</span>
            ) : null}
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="sr-only">Password</span>
            <div className="relative">
              <input
                className="auth-input auth-password-input"
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Password"
                autoComplete={isLogin ? "current-password" : "new-password"}
              />
              <button
                type="button"
                onClick={() => setShowPassword((s) => !s)}
                className="auth-password-toggle"
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
            {fieldErrors.password ? (
              <span style={{ fontFamily: "'DM Sans', system-ui, sans-serif", fontSize: "13px", color: "var(--auth-error)" }}>{fieldErrors.password}</span>
            ) : null}
          </label>

          {authError ? (
            <p style={{ fontFamily: "'DM Sans', system-ui, sans-serif", fontSize: "13px", color: "var(--auth-error)" }}>{authError}</p>
          ) : null}

          <button
            type="submit"
            disabled={!isCredentialsValid || busy}
            className={`btn-3d ${!isCredentialsValid || busy ? "btn-disabled" : ""}`}
            style={{ width: "100%", marginTop: "4px" }}
          >
            <span className="bs"></span>
            <span className="be"></span>
            <span className="bf">
              {busy ? (
                <span style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "8px" }}>
                  <Loader2 size={16} style={{ animation: "spin 1s linear infinite" }} />
                  {isLogin ? "Logging in..." : "Creating account..."}
                </span>
              ) : isLogin ? (
                "Login"
              ) : (
                "Create account"
              )}
            </span>
          </button>

          {/* Divider */}
          <div style={{ display: "flex", alignItems: "center", gap: "12px", margin: "4px 0" }}>
            <div style={{ flex: 1, height: "1px", background: "var(--auth-border)" }} />
            <span style={{ fontFamily: "'DM Sans', system-ui, sans-serif", fontSize: "13px", color: "var(--auth-quiet)" }}>or</span>
            <div style={{ flex: 1, height: "1px", background: "var(--auth-border)" }} />
          </div>

          {/* Google Sign-In button */}
          <button
            type="button"
            disabled={busy}
            className="btn-3d btn-3d-google"
            onClick={async () => {
              setAuthError(null);
              setBusy(true);
              try {
                const { error } = await supabase.auth.signInWithOAuth({
                  provider: "google",
                  options: {
                    redirectTo: window.location.origin + (isTeacherLogin ? "/school/login" : "/login")
                      + (searchParams.get("next") ? `?next=${encodeURIComponent(searchParams.get("next")!)}` : ""),
                  },
                });
                if (error) throw error;
              } catch (err) {
                setAuthError(err instanceof Error ? err.message : "Google sign-in failed");
                setBusy(false);
              }
            }}
            style={{ width: "100%" }}
          >
            <span className="bs"></span>
            <span className="be"></span>
            <span className="bf">
              <span style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "10px" }}>
                {/* Google G logo */}
                <svg width="18" height="18" viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg">
                  <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
                  <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
                  <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
                  <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
                </svg>
                Continue with Google
              </span>
            </span>
          </button>
        </form>
      ) : (
        <div className="mt-8 flex flex-col gap-5">
          <div className="flex justify-center gap-3" onPaste={handlePaste}>
            {code.map((digit, idx) => (
              <input
                key={idx}
                ref={codeRefs[idx]}
                type="text"
                inputMode="numeric"
                maxLength={1}
                value={digit}
                onChange={(e) => handleCodeInput(idx, e.target.value)}
                onKeyDown={(e) => handleCodeKeyDown(idx, e)}
                style={{
                  fontFamily: "'DM Sans', system-ui, sans-serif",
                  fontSize: "22px",
                  fontWeight: 700,
                  color: "var(--auth-ink)",
                  background: "transparent",
                  border: "none",
                  borderBottom: "2px solid var(--auth-border)",
                  width: "40px",
                  height: "48px",
                  textAlign: "center",
                  outline: "none",
                }}
                onFocus={(e) => (e.currentTarget.style.borderBottomColor = "var(--auth-focus)")}
                onBlur={(e) => (e.currentTarget.style.borderBottomColor = "var(--auth-border)")}
              />
            ))}
          </div>

          {authError ? (
            <p style={{ fontFamily: "'DM Sans', system-ui, sans-serif", fontSize: "13px", color: "var(--auth-error)" }}>{authError}</p>
          ) : null}

          <button
            onClick={handleVerifyCode}
            disabled={!isCodeValid || busy}
            className={`btn-3d ${!isCodeValid || busy ? "btn-disabled" : ""}`}
            style={{ width: "100%" }}
          >
            <span className="bs"></span>
            <span className="be"></span>
            <span className="bf">
              {busy ? (
                <span style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "8px" }}>
                  <Loader2 size={16} style={{ animation: "spin 1s linear infinite" }} />
                  Verifying...
                </span>
              ) : (
                "Verify"
              )}
            </span>
          </button>

          <p style={{ fontFamily: "'DM Sans', system-ui, sans-serif", fontSize: "14px", color: "var(--auth-muted)", textAlign: "center" }}>
            {resendTimer > 0 ? (
              <span>Resend code in {resendTimer}s</span>
            ) : (
              <button
                type="button"
                onClick={handleResend}
                disabled={busy}
                style={{ color: "var(--color-orange)", background: "none", border: "none", cursor: "pointer", fontFamily: "inherit", fontSize: "inherit", textDecoration: "underline", textUnderlineOffset: "2px" }}
              >
                Resend code
              </button>
            )}
          </p>

          <p style={{ fontFamily: "'DM Sans', system-ui, sans-serif", fontSize: "14px", color: "var(--auth-muted)", textAlign: "center" }}>
            <button
              type="button"
              onClick={() => {
                setStep("credentials");
                setCode(["", "", "", "", "", ""]);
                setAuthError(null);
              }}
              style={{ color: "var(--color-orange)", background: "none", border: "none", cursor: "pointer", fontFamily: "inherit", fontSize: "inherit", textDecoration: "underline", textUnderlineOffset: "2px" }}
            >
              Change email
            </button>
          </p>
        </div>
      )}

      <p style={{ fontFamily: "'DM Sans', system-ui, sans-serif", fontSize: "14px", color: "var(--auth-muted)", textAlign: "center", marginTop: "16px" }}>
        {isTeacherLogin ? null : isLogin ? (
          <>
            Not a member?{" "}
            <button
              type="button"
              onClick={() => onModeChange("signup")}
              style={{ color: "var(--color-orange)", background: "none", border: "none", cursor: "pointer", fontFamily: "inherit", fontSize: "inherit", textDecoration: "underline", textUnderlineOffset: "2px" }}
            >
              Sign up
            </button>
          </>
        ) : (
          <>
            Already have an account?{" "}
            <button
              type="button"
              onClick={() => onModeChange("login")}
              style={{ color: "var(--color-orange)", background: "none", border: "none", cursor: "pointer", fontFamily: "inherit", fontSize: "inherit", textDecoration: "underline", textUnderlineOffset: "2px" }}
            >
              Sign in
            </button>
          </>
        )}
      </p>
    </div>
  );
}

const authFormCSS = `
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.auth-input {
  display: block;
  width: 100%;
  min-height: 62px;
  border: 2px solid #d8ccbf;
  border-radius: 16px;
  padding: 14px 18px;
  background: #f2eee8;
  color: var(--auth-ink);
  font: 600 18px 'DM Sans', system-ui, sans-serif;
  line-height: 1.3;
  transition: border-color 0.15s, background-color 0.15s;
}
.auth-input::placeholder { color: #806c5d; opacity: 1; font-weight: 500; }
.auth-input:hover { border-color: #bdab99; }
.auth-input:focus-visible { outline: 3px solid var(--auth-focus); outline-offset: 2px; border-color: #b95e18; background: #fffefa; }
.auth-password-input { padding-right: 56px; }
.auth-password-toggle {
  position: absolute;
  top: 50%;
  right: 8px;
  display: grid;
  width: 44px;
  height: 44px;
  transform: translateY(-50%);
  place-items: center;
  border: 0;
  border-radius: 10px;
  background: transparent;
  color: var(--auth-muted);
  cursor: pointer;
}
.auth-password-toggle:focus-visible { outline: 3px solid var(--auth-focus); outline-offset: 2px; }

.btn-3d {
  position: relative;
  border: none;
  background: transparent;
  padding: 0;
  cursor: pointer;
  outline-offset: 4px;
  transition: filter 0.25s;
  user-select: none;
  touch-action: manipulation;
  display: inline-block;
  font-family: 'DM Sans', system-ui, sans-serif;
}
.btn-3d .bs {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  border-radius: 12px;
  background: rgba(66, 25, 1, 0.2);
  will-change: transform;
  transform: translateY(3px);
  transition: transform 0.6s cubic-bezier(0.3, 0.7, 0.4, 1);
}
.btn-3d .be {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  border-radius: 12px;
  background: linear-gradient(to left, hsl(0 0% 0% / 0.15) 0%, hsl(0 0% 0% / 0.25) 8%, hsl(0 0% 0% / 0.25) 92%, hsl(0 0% 0% / 0.15) 100%);
}
.btn-3d .bf {
  display: block;
  position: relative;
  padding: 12px 27px;
  border-radius: 12px;
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--color-background);
  background: var(--color-dark);
  will-change: transform;
  transform: translateY(-4px);
  transition: transform 0.6s cubic-bezier(0.3, 0.7, 0.4, 1);
}
.btn-3d:hover {
  filter: brightness(110%);
}
.btn-3d:hover .bf {
  transform: translateY(-6px);
  transition: transform 0.25s cubic-bezier(0.3, 0.7, 0.4, 1.5);
}
.btn-3d:hover .bs {
  transform: translateY(4px);
  transition: transform 0.25s cubic-bezier(0.3, 0.7, 0.4, 1.5);
}
.btn-3d:active .bf {
  transform: translateY(-2px);
  transition: transform 34ms;
}
.btn-3d:active .bs {
  transform: translateY(1px);
  transition: transform 34ms;
}
.btn-3d.btn-disabled {
  opacity: 0.4;
  cursor: not-allowed;
  pointer-events: none;
}

/* White 3D button variant — for Google sign-in */
.btn-3d-google .bs {
  background: rgba(66, 25, 1, 0.15);
}
.btn-3d-google .be {
  background: linear-gradient(to left, #b8b8b8 0%, #c8c8c8 8%, #c8c8c8 92%, #b8b8b8 100%);
}
.btn-3d-google .bf {
  background: var(--color-background);
  color: var(--color-dark);
  border: 1.5px solid var(--auth-border);
}
.btn-3d-google:hover .bf {
  border-color: #cdbba8;
}
`;
