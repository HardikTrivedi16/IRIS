/**
 * Single source of truth for the backend API base URL.
 *
 * - VITE_API_URL explicitly set -> use it, trailing slash removed.
 * - Not set, local dev (`vite dev`) -> http://localhost:8000 (the backend's
 *   local uvicorn port), since dev serves frontend and backend separately.
 * - Not set, production build -> "" (empty), so every request is same-origin
 *   (`/api/v1/...`) — correct for the single Vercel Services deployment,
 *   where the platform rewrites `/api/v1/*`, `/health`, `/docs` and
 *   `/openapi.json` to the backend service on the same public domain.
 */
export const API_BASE: string = (() => {
  const raw = import.meta.env["VITE_API_URL"] as string | undefined;
  if (raw) return raw.replace(/\/+$/, "");
  return import.meta.env.DEV ? "http://localhost:8000" : "";
})();
