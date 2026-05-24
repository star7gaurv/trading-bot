import { useState } from "react";
import { Activity, KeyRound } from "lucide-react";
import { login } from "../api/client";

/**
 * Password gate. Renders before App can mount the actual dashboard.
 */
export default function LoginGate({ onAuthed }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit(e) {
    e.preventDefault();
    if (!password) return;
    setSubmitting(true);
    setError(null);
    try {
      await login(password);
      onAuthed();
    } catch (err) {
      setError(err.message || "Login failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-canvas flex items-center justify-center p-6">
      <form
        onSubmit={submit}
        className="w-full max-w-sm bg-surface border border-border rounded-lg p-6 shadow-lifted"
      >
        <div className="flex items-center gap-3 mb-5">
          <div className="w-9 h-9 rounded bg-accent/10 border border-accent/30 flex items-center justify-center">
            <Activity className="w-4.5 h-4.5 text-accent" />
          </div>
          <div className="leading-tight">
            <div className="text-sm font-semibold">FinBuddy Console</div>
            <div className="text-xxs text-text-tertiary">v2 · sign in to continue</div>
          </div>
        </div>

        <label className="block text-xxs uppercase tracking-wider text-text-tertiary mb-1.5">
          Password
        </label>
        <div className="relative">
          <KeyRound className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-text-muted pointer-events-none" />
          <input
            type="password"
            autoFocus
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            className="w-full !pl-9"
            disabled={submitting}
          />
        </div>

        {error && (
          <div className="mt-3 text-xs text-loss bg-loss/10 border border-loss/30 rounded px-3 py-2">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={submitting || !password}
          className="mt-4 w-full h-9 rounded bg-accent text-white text-sm font-medium hover:bg-accent-dim transition disabled:opacity-50"
        >
          {submitting ? "Signing in…" : "Sign in"}
        </button>

        <p className="mt-4 text-xxs text-text-muted">
          Single-user dashboard. Token valid for 7 days, stored in browser.
        </p>
      </form>
    </div>
  );
}
