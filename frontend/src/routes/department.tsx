import {
  createFileRoute,
  Outlet,
  useNavigate,
  Link,
} from "@tanstack/react-router";
import { useEffect } from "react";
import { DepartmentShell } from "@/components/iris/department-shell";
import { useAuth } from "@/lib/auth-context";

export const Route = createFileRoute("/department")({
  head: () => ({
    meta: [
      { title: "IRIS Government Portal" },
      {
        name: "description",
        content:
          "Government department operational portal for processing industrial regulatory applications.",
      },
    ],
  }),
  component: DepartmentLayout,
});

function DepartmentLayout() {
  const { irisUser, isLoading, isDemoMode, isAuthenticated, signOut } =
    useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (!isLoading && !isDemoMode && !isAuthenticated) {
      void navigate({ to: "/login" });
    }
  }, [isLoading, isDemoMode, isAuthenticated, navigate]);

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-muted-foreground text-[13.5px]">
          Verifying authorization…
        </div>
      </div>
    );
  }

  // Not authenticated in production
  if (!isDemoMode && !isAuthenticated) {
    return null;
  }

  // Authenticated, but not a government role
  if (!isDemoMode && irisUser && !irisUser.role.startsWith("DEPARTMENT_")) {
    return (
      <div className="flex min-h-screen items-center justify-center px-4 bg-background">
        <div className="max-w-md text-center p-6 rounded-lg border border-border bg-card shadow-sm">
          <div className="mb-3 inline-flex h-10 w-10 items-center justify-center rounded-md bg-warning/20 text-warning text-[18px] font-bold">
            !
          </div>
          <h2 className="text-[18px] font-semibold text-foreground">
            Government Access Required
          </h2>
          <p className="mt-2 text-[13px] text-muted-foreground leading-relaxed">
            Your account ({irisUser.email}) is currently assigned the{" "}
            <strong>{irisUser.role}</strong> role. Government department portal
            access requires a <strong>DEPARTMENT_*</strong> role assigned by an
            administrator.
          </p>
          <div className="mt-6 flex flex-col gap-2 sm:flex-row sm:justify-center">
            <Link
              to="/"
              className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-[13px] font-medium text-primary-foreground transition-opacity hover:opacity-90"
            >
              Go to Industry Portal
            </Link>
            <button
              onClick={() => void signOut()}
              className="inline-flex items-center justify-center rounded-md border border-border px-4 py-2 text-[13px] font-medium text-foreground transition-colors hover:bg-secondary"
            >
              Sign Out
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <DepartmentShell>
      <Outlet />
    </DepartmentShell>
  );
}
