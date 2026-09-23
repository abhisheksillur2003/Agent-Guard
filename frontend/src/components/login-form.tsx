"use client";

import {
  ArrowRight,
  CheckCircle2,
  Eye,
  EyeOff,
  LockKeyhole,
  Radar,
  ShieldCheck,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import { Brand } from "@/components/brand";
import { demoMode } from "@/lib/api-client";

export function LoginForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setLoading(true);
    if (demoMode) {
      router.push("/dashboard");
      return;
    }
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const body = (await response.json()) as { message?: string };
      if (!response.ok) throw new Error(body.message ?? "Unable to sign in");
      router.push("/dashboard");
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to sign in");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="login-page">
      <section className="login-story">
        <div className="login-story-inner">
          <Brand />
          <div className="login-copy">
            <p className="eyebrow">AI operations control plane</p>
            <h1>
              Every agent action,
              <br />
              <span>under control.</span>
            </h1>
            <p>
              Observe decisions, enforce deterministic policy, and keep a human
              in the loop for high-impact actions.
            </p>
          </div>
          <div className="login-features">
            <div>
              <ShieldCheck />
              <span>
                <strong>Deny by default</strong>
                <small>Permissions and policy remain authoritative</small>
              </span>
            </div>
            <div>
              <Radar />
              <span>
                <strong>Live visibility</strong>
                <small>Trace every decision and execution attempt</small>
              </span>
            </div>
            <div>
              <CheckCircle2 />
              <span>
                <strong>Human approval</strong>
                <small>Review sensitive operations before execution</small>
              </span>
            </div>
          </div>
          <div className="login-signal">
            <span />
            <span />
            <span />
            <span />
            <span />
          </div>
        </div>
      </section>
      <section className="login-panel">
        <div className="login-card">
          <div className="mobile-brand">
            <Brand />
          </div>
          <span className="login-lock">
            <LockKeyhole size={22} />
          </span>
          <h2>Welcome back</h2>
          <p>Sign in to your AgentGuard workspace</p>
          {demoMode && (
            <div className="demo-notice">
              Demo mode is active. Any credentials will open the sample
              workspace.
            </div>
          )}
          <form onSubmit={submit}>
            <label>
              Email address
              <input
                type="email"
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="admin@example.com"
                required={!demoMode}
              />
            </label>
            <label>
              Password
              <span className="password-field">
                <input
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="Enter your password"
                  required={!demoMode}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((visible) => !visible)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </span>
            </label>
            {error && (
              <div className="form-error" role="alert">
                {error}
              </div>
            )}
            <button className="primary-button login-button" disabled={loading}>
              {loading ? "Signing in…" : "Sign in securely"}
              <ArrowRight size={17} />
            </button>
          </form>
          <div className="login-footer">
            <ShieldCheck size={15} /> Credentials are sent only to your local
            AgentGuard API.
          </div>
        </div>
      </section>
    </main>
  );
}
