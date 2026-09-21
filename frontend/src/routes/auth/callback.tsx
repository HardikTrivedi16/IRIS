/**
 * OAuth callback handler.
 *
 * Supabase redirects here after Google OAuth completes.
 * URL contains the session as a hash fragment (#access_token=...) or
 * query params (depends on Supabase config).
 *
 * Flow:
 *   1. Supabase SDK automatically picks up the session from the URL
 *      (via onAuthStateChange in auth-context.tsx)
 *   2. AuthProvider fetches IRIS profile from GET /api/v1/auth/me
 *   3. This page waits for the session, then creates the IRIS profile
 *      (POST /api/v1/auth/profile) to ensure the profile record exists
 *   4. Redirects to the appropriate portal based on IRIS role
 *
 * If the user is new (no department_users link), they are redirected
 * to a "pending access" screen — the admin must link their profile.
 *
 * No secrets are present on this page.
 */

import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";

export const Route = createFileRoute("/auth/callback")({
  head: () => ({ meta: [{ title: "Signing in… — IRIS" }] }),
  component: AuthCallbackPage,
});

function AuthCallbackPage() {
  const navigate = useNavigate();
  const { irisUser, isLoading, session } = useAuth();
  const [status, setStatus] = useState<
    "waiting" | "linking" | "done" | "error"
  >("waiting");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (isLoading) return;

    async function handleCallback() {
      if (!session) {
        // No session — possible error from Google, redirect to login
        setStatus("error");
        setErrorMsg("Authentication did not complete. Please try again.");
        return;
      }

      // Create/update IRIS profile on every login
      setStatus("linking");
      const apiUrl =
        (import.meta.env["VITE_API_URL"] as string) || "http://localhost:8000";
      try {
        await fetch(`${apiUrl}/api/v1/auth/profile`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${session.access_token}`,
          },
          body: JSON.stringify({
            provider: session.user?.app_metadata?.provider ?? "google",
            full_name:
              session.user?.user_metadata?.["full_name"] ??
              session.user?.user_metadata?.["name"] ??
              null,
            avatar_url: session.user?.user_metadata?.["avatar_url"] ?? null,
          }),
        });
      } catch {
        // Profile creation failure is non-fatal — continue
      }

      setStatus("done");

      if (irisUser) {
        const isGovernment = irisUser.role.startsWith("DEPARTMENT_");
        void navigate({ to: isGovernment ? "/department" : "/" });
      } else {
        // irisUser not yet resolved — fallback redirect to login
        void navigate({ to: "/login" });
      }
    }

    void handleCallback();
  }, [isLoading, session, irisUser, navigate]);

  if (status === "error") {
    return (
      <div className="flex min-h-screen items-center justify-center px-4">
        <div className="max-w-sm text-center">
          <p className="text-[18px] font-semibold text-destructive">
            Sign-in failed
          </p>
          <p className="mt-2 text-[13.5px] text-muted-foreground">{errorMsg}</p>
          <a
            href="/login"
            className="mt-5 inline-flex items-center rounded-md bg-primary px-4 py-2 text-[13px] font-medium text-primary-foreground"
          >
            Back to sign in
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="max-w-sm text-center">
        <div className="mb-3 inline-flex h-10 w-10 items-center justify-center rounded-md bg-primary text-primary-foreground text-[18px] font-bold">
          I
        </div>
        <p className="mt-3 text-[14px] font-medium">
          {status === "linking"
            ? "Setting up your account…"
            : "Signing you in…"}
        </p>
        <p className="mt-1 text-[12.5px] text-muted-foreground">
          {status === "done" ? "Redirecting…" : "Please wait"}
        </p>
      </div>
    </div>
  );
}
