import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  Outlet,
  Link,
  createRootRouteWithContext,
  useRouter,
  HeadContent,
  Scripts,
  useNavigate,
} from "@tanstack/react-router";
import { useEffect, useRef, type ReactNode } from "react";
import { useRouterState } from "@tanstack/react-router";

import appCss from "../styles.css?url";
import { reportLovableError } from "../lib/lovable-error-reporting";
import { AppShell } from "@/components/iris/app-shell";
import { AuthProvider, useAuth } from "@/lib/auth-context";
import { setAuthToken } from "@/lib/iris/api-client";
import { setDeptAuthToken } from "@/lib/iris/department-api";

function NotFoundComponent() {
  return (
    <div className="flex min-h-[70vh] items-center justify-center px-6">
      <div className="max-w-md">
        <p className="label-meta">Error 404</p>
        <h1 className="mt-2 text-[20px] font-semibold">Screen not found</h1>
        <p className="mt-2 text-[13.5px] leading-relaxed text-muted-foreground">
          The requested view is not part of this workspace. Return to the
          regulatory overview to continue.
        </p>
        <Link
          to="/"
          className="mt-5 inline-flex items-center rounded-sm bg-primary px-3 py-2 text-[13px] font-medium text-primary-foreground transition-opacity hover:opacity-90"
        >
          Go to Overview
        </Link>
      </div>
    </div>
  );
}

function ErrorComponent({ error, reset }: { error: Error; reset: () => void }) {
  console.error(error);
  const router = useRouter();
  useEffect(() => {
    reportLovableError(error, { boundary: "tanstack_root_error_component" });
  }, [error]);

  return (
    <div className="flex min-h-[70vh] items-center justify-center px-6">
      <div className="max-w-md">
        <p className="label-meta">Unexpected error</p>
        <h1 className="mt-2 text-[20px] font-semibold">
          This view didn't load
        </h1>
        <p className="mt-2 text-[13.5px] leading-relaxed text-muted-foreground">
          Something interrupted rendering. Retry the view or return to the
          overview.
        </p>
        <div className="mt-5 flex gap-2">
          <button
            onClick={() => {
              router.invalidate();
              reset();
            }}
            className="inline-flex items-center rounded-sm bg-primary px-3 py-2 text-[13px] font-medium text-primary-foreground transition-opacity hover:opacity-90"
          >
            Retry
          </button>
          <a
            href="/"
            className="inline-flex items-center rounded-sm border border-border px-3 py-2 text-[13px] font-medium transition-colors hover:bg-secondary"
          >
            Overview
          </a>
        </div>
      </div>
    </div>
  );
}

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()(
  {
    head: () => ({
      meta: [
        { charSet: "utf-8" },
        { name: "viewport", content: "width=device-width, initial-scale=1" },
        { title: "IRIS — Industrial Regulatory Intelligence System" },
        {
          name: "description",
          content:
            "IRIS is a project-level regulatory intelligence and orchestration layer for industrial approvals in Maharashtra.",
        },
        {
          property: "og:title",
          content: "IRIS — Industrial Regulatory Intelligence System",
        },
        {
          property: "og:description",
          content:
            "Track approvals, dependencies, documents and change impact across industrial regulatory processes.",
        },
        { property: "og:type", content: "website" },
        { name: "twitter:card", content: "summary_large_image" },
      ],
      links: [
        { rel: "preconnect", href: "https://fonts.googleapis.com" },
        {
          rel: "preconnect",
          href: "https://fonts.gstatic.com",
          crossOrigin: "anonymous",
        },
        {
          rel: "stylesheet",
          href: "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap",
        },
        { rel: "stylesheet", href: appCss },
        { rel: "icon", href: "/favicon.ico", type: "image/x-icon" },
      ],
    }),
    shellComponent: RootShell,
    component: RootComponent,
    notFoundComponent: NotFoundComponent,
    errorComponent: ErrorComponent,
  },
);

function RootShell({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        <HeadContent />
      </head>
      <body>
        {children}
        <Scripts />
      </body>
    </html>
  );
}

/**
 * Inner component: injects the auth token into both API clients when the
 * session changes, and handles industry/government portal routing.
 */
function AppInner() {
  const { queryClient } = Route.useRouteContext();
  const navigate = useNavigate();
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const { session, isDemoMode, isAuthenticated, isLoading } = useAuth();

  // Inject token into both API clients on session change
  useEffect(() => {
    const token = session?.access_token ?? null;
    setAuthToken(token);
    setDeptAuthToken(token);
  }, [session]);

  // Cross-account cache isolation: every useQuery cache in this app
  // (["projects"], project-requirements/documents/activity, grievances,
  // applications, schemes, renewals, department dashboards/applications/
  // officers, ...) lives in one QueryClient instance that survives sign-out
  // and sign-in in place (this is a client-rendered SPA, nothing reloads).
  // None of those query keys are scoped by user id, so without this, a
  // second account signing in in the same tab could see the previous
  // account's still-cached, not-yet-stale data rendered before its own
  // fetch resolves — a real cross-session data leak, not just stale UI.
  // Clearing the whole cache whenever the authenticated principal actually
  // changes (a different Supabase user, or a sign-out) is the standard
  // TanStack Query pattern for this and needs no per-query-key changes.
  // `undefined` (not yet observed) intentionally does not count as a
  // change, so the cache isn't wiped on first load.
  const identityRef = useRef<string | null | undefined>(undefined);
  const identity = isDemoMode ? "demo" : (session?.user?.id ?? null);
  useEffect(() => {
    if (identityRef.current !== undefined && identityRef.current !== identity) {
      queryClient.clear();
    }
    identityRef.current = identity;
  }, [identity, queryClient]);

  const isDepartmentRoute = pathname.startsWith("/department");
  const isLoginRoute =
    pathname.startsWith("/login") || pathname.startsWith("/auth/");

  // Auth guard: when the user is not authenticated (e.g. right after clicking
  // "Sign out", which clears the session in place without a page reload),
  // send them to the login page. Previously nothing navigated on sign-out, so
  // the industry portal just sat on the current screen until a manual refresh
  // re-ran the route load and 401'd. Skipped in demo mode (always
  // "authenticated") and while auth state is still resolving on first load.
  useEffect(() => {
    if (isDemoMode || isLoading) return;
    if (!isAuthenticated && !isLoginRoute) {
      void navigate({ to: "/login" });
    }
  }, [isAuthenticated, isDemoMode, isLoading, isLoginRoute, navigate]);

  return (
    <QueryClientProvider client={queryClient}>
      {isDepartmentRoute ? (
        /* Department routes handle their own shell (DepartmentShell) via
           the /department layout route — no AppShell wrapper needed here. */
        <Outlet />
      ) : isLoginRoute ? (
        /* Login and auth callback routes render without any shell */
        <Outlet />
      ) : (
        <AppShell>
          {/* Required: nested routes render here. Removing <Outlet /> breaks all child routes. */}
          <Outlet />
        </AppShell>
      )}
    </QueryClientProvider>
  );
}

function RootComponent() {
  return (
    <AuthProvider>
      <AppInner />
    </AuthProvider>
  );
}
