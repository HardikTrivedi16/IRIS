import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState, useEffect } from "react";
import { useAuth } from "@/lib/auth-context";

export const Route = createFileRoute("/login")({
  head: () => ({
    meta: [
      { title: "Sign In — IRIS" },
      {
        name: "description",
        content: "Sign in to IRIS — Industrial Regulatory Intelligence System",
      },
    ],
  }),
  component: LoginPage,
});

function LoginPage() {
  const navigate = useNavigate();
  const { signIn, signUp, irisUser, isLoading, isDemoMode } = useAuth();

  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Redirect if already authenticated
  useEffect(() => {
    if (!isLoading && irisUser) {
      const isGovernment = irisUser.role.startsWith("DEPARTMENT_");
      void navigate({ to: isGovernment ? "/department" : "/" });
    }
  }, [irisUser, isLoading, navigate]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setInfo(null);
    setSubmitting(true);

    if (mode === "signup") {
      const { error: err } = await signUp(email, password, name);
      if (err) {
        setError(err);
      } else {
        setInfo(
          "Account created! Check your email to confirm your address, then sign in. " +
            "If you need Government portal access, contact your department administrator after signing in.",
        );
        setMode("signin");
      }
    } else {
      const { error: err } = await signIn(email, password);
      if (err) {
        setError(err);
      }
      // Redirect handled by useEffect above after irisUser resolves
    }

    setSubmitting(false);
  }

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-muted-foreground text-[13.5px]">Loading…</div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm">
        {/* Logo / heading */}
        <div className="mb-8 text-center">
          <div className="mb-3 inline-flex h-10 w-10 items-center justify-center rounded-md bg-primary text-primary-foreground text-[18px] font-bold">
            I
          </div>
          <h1 className="text-[18px] font-semibold tracking-tight">IRIS</h1>
          <p className="mt-1 text-[13px] text-muted-foreground">
            Industrial Regulatory Intelligence System
          </p>
        </div>

        {/* Demo mode notice */}
        {isDemoMode && (
          <div className="mb-4 rounded-md border border-warning/30 bg-warning-surface px-3.5 py-3 text-[12.5px] text-warning">
            <strong>Demo Mode</strong> — Supabase not configured. Auth is
            disabled.{" "}
            <a href="/department" className="underline hover:no-underline">
              Enter Government Portal →
            </a>{" "}
            or{" "}
            <a href="/" className="underline hover:no-underline">
              Industry Portal →
            </a>
          </div>
        )}

        {/* Tab switcher */}
        {!isDemoMode && (
          <>
            <div className="mb-5 flex rounded-md border border-border bg-secondary/30 p-0.5">
              <button
                onClick={() => {
                  setMode("signin");
                  setError(null);
                }}
                className={`flex-1 rounded py-1.5 text-[13px] font-medium transition-colors ${
                  mode === "signin"
                    ? "bg-background shadow-sm text-foreground"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                Sign In
              </button>
              <button
                onClick={() => {
                  setMode("signup");
                  setError(null);
                }}
                className={`flex-1 rounded py-1.5 text-[13px] font-medium transition-colors ${
                  mode === "signup"
                    ? "bg-background shadow-sm text-foreground"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                Create Account
              </button>
            </div>

            {/* Alerts */}
            {error && (
              <div className="mb-4 rounded-md border border-destructive/25 bg-danger-surface px-3.5 py-2.5 text-[12.5px] text-destructive">
                {error}
              </div>
            )}
            {info && (
              <div className="mb-4 rounded-md border border-success/25 bg-success-surface px-3.5 py-2.5 text-[12.5px] text-success">
                {info}
              </div>
            )}

            {/* Form */}
            <form onSubmit={handleSubmit} className="space-y-3">
              {mode === "signup" && (
                <div>
                  <label
                    className="mb-1 block text-[12.5px] font-medium text-foreground"
                    htmlFor="name"
                  >
                    Full name
                  </label>
                  <input
                    id="name"
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Your name"
                    className="w-full rounded-md border border-border bg-background px-3 py-2 text-[13px] outline-none focus:border-primary focus:ring-1 focus:ring-primary/30"
                  />
                </div>
              )}
              <div>
                <label
                  className="mb-1 block text-[12.5px] font-medium text-foreground"
                  htmlFor="email"
                >
                  Email
                </label>
                <input
                  id="email"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-[13px] outline-none focus:border-primary focus:ring-1 focus:ring-primary/30"
                />
              </div>
              <div>
                <label
                  className="mb-1 block text-[12.5px] font-medium text-foreground"
                  htmlFor="password"
                >
                  Password
                </label>
                <input
                  id="password"
                  type="password"
                  required
                  minLength={6}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-[13px] outline-none focus:border-primary focus:ring-1 focus:ring-primary/30"
                />
              </div>
              <button
                type="submit"
                disabled={submitting}
                className="w-full rounded-md bg-primary px-4 py-2.5 text-[13px] font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
              >
                {submitting
                  ? "…"
                  : mode === "signup"
                    ? "Create Account"
                    : "Sign In"}
              </button>
            </form>

            {/* Government access note */}
            <p className="mt-5 text-center text-[11.5px] text-muted-foreground leading-relaxed">
              Government portal access requires your account to be linked to a
              department by an administrator after sign-in.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
