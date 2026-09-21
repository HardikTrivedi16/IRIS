/**
 * Supabase client — auth-only wrapper.
 *
 * This client is used EXCLUSIVELY for Supabase Auth operations:
 *   - Email/password sign-in and sign-up
 *   - Google OAuth sign-in (signInWithOAuth)
 *   - Session management (onAuthStateChange, getSession)
 *   - Sign-out
 *
 * It is NOT used for direct Supabase data access. All data (projects,
 * applications, decisions, SLA, bottlenecks) flows through the IRIS
 * FastAPI backend, which uses the server-only service-role key.
 *
 * Auth flow:
 *   User signs in → Supabase issues JWT → stored in localStorage by @supabase/supabase-js
 *   Frontend passes JWT as Authorization: Bearer to IRIS backend API
 *   Backend verifies JWT via JWKS → resolves user identity and IRIS role
 *
 * The anon key (VITE_SUPABASE_ANON_KEY) is intentionally public — it enables
 * auth operations only (no data read/write without an RLS-appropriate role).
 * The service-role key is NEVER present in frontend code.
 *
 * If VITE_SUPABASE_URL or VITE_SUPABASE_ANON_KEY are not set, `supabase` is
 * null and auth features are hidden (demo mode).
 */

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const url = import.meta.env["VITE_SUPABASE_URL"] as string | undefined;
const anonKey = import.meta.env["VITE_SUPABASE_ANON_KEY"] as string | undefined;

/**
 * The Supabase auth client. Null when Supabase is not configured (demo mode).
 * Use the `useAuth()` hook from auth-context.tsx — don't use this directly.
 */
export const supabase: SupabaseClient | null =
  url && anonKey ? createClient(url, anonKey) : null;

export const isSupabaseConfigured = Boolean(url && anonKey);
