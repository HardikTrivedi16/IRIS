/**
 * Auth context — provides authentication state and operations to the app.
 *
 * What this context provides:
 *   - session: Supabase Auth session (JWT + user metadata)
 *   - irisUser: IRIS profile (role, department) from GET /api/v1/auth/me
 *   - isLoading: true until auth state is determined
 *   - isAuthenticated: session exists and irisUser resolved
 *   - signIn(email, password): email/password sign-in
 *   - signUp(email, password): new account creation
 *   - signOut(): clear session
 *   - signInWithGoogle(): Google OAuth (redirects to Google, then /auth/callback)
 *
 * Auth flow (Supabase configured):
 *   1. Supabase SDK manages session in localStorage (automatic persistence)
 *   2. On session change → fetch IRIS profile from GET /api/v1/auth/me
 *   3. IRIS profile has role: INDUSTRY_USER or DEPARTMENT_*
 *   4. Protected routes check role and redirect appropriately
 *
 * Demo mode (Supabase not configured):
 *   - session: null
 *   - irisUser: a demo government user (for local development)
 *   - isAuthenticated: true (demo mode bypasses auth checks)
 *   - Auth operations (signIn, signOut, etc.) are no-ops
 *   - A visible "Demo Mode" badge is shown in the UI
 *
 * Security:
 *   - The JWT is passed as Authorization: Bearer to ALL backend API calls
 *   - The backend verifies the JWT independently (JWKS/RS256)
 *   - Frontend route guards are defence-in-depth only; backend enforcement is primary
 *   - The service-role key is NEVER in this file or any frontend code
 *
 * Industry project isolation note:
 *   The projects table currently lacks a user_id column, so industry users
 *   can read all projects via the current RLS policy. This is a known
 *   prerequisite for full isolation — documented in migration 0003.
 */

import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from "react";
import type { Session } from "@supabase/supabase-js";
import { supabase, isSupabaseConfigured } from "@/lib/supabase";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface IrisUser {
  user_id: string;
  email: string | null;
  role:
    | "INDUSTRY_USER"
    | "DEPARTMENT_OFFICER"
    | "DEPARTMENT_MANAGER"
    | "DEPARTMENT_ADMIN";
  department_id: string | null;
  /** Human-readable department name, resolved server-side from the
   * department store — null for industry users or if unresolved. Never
   * hardcode a department name in the frontend; always read this field. */
  department_name: string | null;
  name: string;
  is_demo: boolean;
}

interface AuthContextValue {
  session: Session | null;
  irisUser: IrisUser | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  isDemoMode: boolean;
  signIn: (
    email: string,
    password: string,
  ) => Promise<{ error: string | null }>;
  signUp: (
    email: string,
    password: string,
    name?: string,
  ) => Promise<{ error: string | null }>;
  signOut: () => Promise<void>;
  signInWithGoogle: () => Promise<{ error: string | null }>;
}

// ---------------------------------------------------------------------------
// Demo user (used when Supabase is not configured)
// ---------------------------------------------------------------------------

// Matches the backend's own fixed demo persona exactly (app/security.py
// _DEMO_USER: dept-mpcb) and the real seeded department name
// (app/store/department_store.py _SEED_DEPARTMENTS) — not invented here.
const DEMO_IRIS_USER: IrisUser = {
  user_id: "demo-officer-001",
  email: "demo@iris.local",
  role: "DEPARTMENT_ADMIN",
  department_id: "dept-mpcb",
  department_name: "Maharashtra Pollution Control Board",
  name: "Demo Officer",
  is_demo: true,
};

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

const AuthContext = createContext<AuthContextValue | null>(null);

// ---------------------------------------------------------------------------
// Fetch IRIS profile from backend
// ---------------------------------------------------------------------------

async function fetchIrisUser(accessToken: string): Promise<IrisUser | null> {
  const apiUrl =
    (import.meta.env["VITE_API_URL"] as string) || "http://localhost:8000";
  try {
    const res = await fetch(`${apiUrl}/api/v1/auth/me`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    if (!res.ok) return null;
    return (await res.json()) as IrisUser;
  } catch {
    return null;
  }
}

/**
 * Ensure a user_profiles row exists for this session (POST /api/v1/auth/profile
 * is idempotent — create on first login, update on subsequent ones).
 *
 * Previously this only ran on the Google OAuth callback page
 * (routes/auth/callback.tsx), so an email/password sign-up never got a
 * user_profiles row created — meaning a DEPARTMENT_ADMIN could never find
 * that user in "pending government link" (list_user_profiles) to grant them
 * a government role. GET /api/v1/auth/me still worked for them either way
 * (it falls back to INDUSTRY_USER from the JWT alone), which is why this
 * went unnoticed — the bug only blocked the *government onboarding* path,
 * not industry login. Non-fatal on failure, exactly like callback.tsx.
 */
async function ensureIrisProfile(session: Session): Promise<void> {
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
        provider: session.user?.app_metadata?.provider ?? "email",
        full_name:
          session.user?.user_metadata?.["full_name"] ??
          session.user?.user_metadata?.["name"] ??
          null,
        avatar_url: session.user?.user_metadata?.["avatar_url"] ?? null,
      }),
    });
  } catch {
    // Non-fatal — GET /api/v1/auth/me still resolves a role from the JWT
    // alone, so a transient failure here doesn't block sign-in.
  }
}

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [irisUser, setIrisUser] = useState<IrisUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Demo mode: Supabase not configured
  const isDemoMode = !isSupabaseConfigured;

  useEffect(() => {
    if (isDemoMode) {
      // In demo mode, immediately resolve with demo user
      setIrisUser(DEMO_IRIS_USER);
      setIsLoading(false);
      return;
    }

    if (!supabase) {
      setIsLoading(false);
      return;
    }

    // Initialize from existing session (e.g. page refresh)
    supabase.auth.getSession().then(async ({ data: { session: s } }) => {
      setSession(s);
      if (s?.access_token) {
        const user = await fetchIrisUser(s.access_token);
        setIrisUser(user);
      }
      setIsLoading(false);
    });

    // Subscribe to auth state changes
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange(async (event, s) => {
      setSession(s);
      if (s?.access_token) {
        if (event === "SIGNED_IN") {
          // Ensure a user_profiles row exists regardless of provider (see
          // ensureIrisProfile docstring) — only on the actual sign-in
          // transition, not on every token refresh.
          await ensureIrisProfile(s);
        }
        const user = await fetchIrisUser(s.access_token);
        setIrisUser(user);
      } else {
        setIrisUser(null);
      }
      setIsLoading(false);
    });

    return () => subscription.unsubscribe();
  }, [isDemoMode]);

  const signIn = useCallback(
    async (email: string, password: string) => {
      if (isDemoMode || !supabase)
        return { error: "Auth not configured (demo mode)" };
      const { error } = await supabase.auth.signInWithPassword({
        email,
        password,
      });
      return { error: error?.message ?? null };
    },
    [isDemoMode],
  );

  const signUp = useCallback(
    async (email: string, password: string, name?: string) => {
      if (isDemoMode || !supabase)
        return { error: "Auth not configured (demo mode)" };
      const { error } = await supabase.auth.signUp({
        email,
        password,
        options: { data: { full_name: name } },
      });
      return { error: error?.message ?? null };
    },
    [isDemoMode],
  );

  const signOut = useCallback(async () => {
    if (isDemoMode || !supabase) return;
    await supabase.auth.signOut();
    setSession(null);
    setIrisUser(null);
  }, [isDemoMode]);

  const signInWithGoogle = useCallback(async () => {
    if (isDemoMode || !supabase)
      return { error: "Auth not configured (demo mode)" };
    const redirectTo = `${window.location.origin}/auth/callback`;
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo },
    });
    return { error: error?.message ?? null };
  }, [isDemoMode]);

  const isAuthenticated = isDemoMode ? true : Boolean(session && irisUser);

  const value: AuthContextValue = {
    session,
    irisUser,
    isLoading,
    isAuthenticated,
    isDemoMode,
    signIn,
    signUp,
    signOut,
    signInWithGoogle,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

/**
 * Returns the Bearer token for authenticated backend API calls.
 * Returns null in demo mode (backend handles demo mode transparently).
 */
export function useAuthToken(): string | null {
  const { session, isDemoMode } = useAuth();
  if (isDemoMode) return null;
  return session?.access_token ?? null;
}
