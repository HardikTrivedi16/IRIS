/**
 * Department / Government portal app shell.
 *
 * Provides a separate sidebar and header for the department operational
 * portal at /department/**. Uses the same IRIS design system as the
 * industry portal (oklch colors, Inter font, panel/label-meta classes)
 * but with distinct navigation items and a department-specific identity.
 */
import { Link, useRouterState } from "@tanstack/react-router";
import {
  Activity,
  AlertTriangle,
  Bell,
  Building2,
  ClipboardList,
  Clock,
  LayoutDashboard,
  LogOut,
  Search,
  Settings,
  Shield,
  Users,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth-context";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const deptNavSections = [
  {
    label: "Operations",
    items: [
      {
        label: "Dashboard",
        to: "/department",
        icon: LayoutDashboard,
        exact: true,
      },
      {
        label: "Applications",
        to: "/department/applications",
        icon: ClipboardList,
      },
      { label: "SLA Intelligence", to: "/department/sla", icon: Clock },
    ],
  },
  {
    label: "Analytics",
    items: [
      {
        label: "Bottlenecks",
        to: "/department/bottlenecks",
        icon: AlertTriangle,
      },
    ],
  },
  {
    label: "Management",
    items: [
      { label: "Officers & Users", to: "/department/officers", icon: Users },
    ],
  },
  {
    label: "System",
    items: [
      { label: "Audit Log", to: "/department/audit", icon: Activity },
      { label: "Settings", to: "/department/settings", icon: Settings },
    ],
  },
];

function DeptSidebar() {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const { irisUser, isDemoMode } = useAuth();

  return (
    <aside className="sticky top-0 hidden h-screen w-[228px] shrink-0 flex-col border-r border-nav-border bg-nav lg:flex">
      <div className="flex h-14 items-center gap-2.5 border-b border-nav-border px-5">
        <span className="flex h-7 w-7 items-center justify-center rounded-md bg-gradient-to-br from-[oklch(0.42_0.14_155)] to-[oklch(0.32_0.12_155)] text-[11px] font-semibold text-white shadow-[0_1px_2px_rgba(0,60,40,0.4)]">
          GO
        </span>
        <div className="leading-none">
          <div className="text-[14.5px] font-semibold tracking-tight text-nav-foreground">
            IRIS Gov
          </div>
          <div className="mt-1 text-[9px] font-medium uppercase tracking-[0.1em] text-nav-muted">
            Department Portal
          </div>
        </div>
      </div>

      {/* Switch to Industry portal */}
      <div className="px-3 py-2.5 border-b border-nav-border">
        <Link
          to="/"
          className="flex items-center gap-2 rounded-md px-2.5 py-[7px] text-[11.5px] text-nav-muted transition-colors hover:bg-white/[0.05] hover:text-nav-foreground"
        >
          <Shield className="h-3.5 w-3.5 opacity-60" />
          Switch to Industry Portal
        </Link>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-4">
        {deptNavSections.map((section, i) => (
          <div key={section.label} className={cn(i > 0 && "mt-5")}>
            <p className="px-2.5 pb-1.5 text-[9.5px] font-semibold uppercase tracking-[0.1em] text-nav-muted/70">
              {section.label}
            </p>
            <ul className="space-y-px">
              {section.items.map((item) => {
                const Icon = item.icon;
                const active = item.exact
                  ? pathname === item.to
                  : pathname.startsWith(item.to);
                return (
                  <li key={item.to}>
                    <Link
                      to={item.to as "/department"}
                      className={cn(
                        "focus-ring group relative flex items-center gap-2.5 rounded-md px-2.5 py-[7px] text-[13px] transition-colors duration-150",
                        active
                          ? "bg-nav-active font-medium text-nav-foreground"
                          : "text-nav-muted hover:bg-white/[0.05] hover:text-nav-foreground",
                      )}
                    >
                      {active && (
                        <span className="absolute -left-3 top-1/2 h-4 w-[3px] -translate-y-1/2 rounded-full bg-[oklch(0.55_0.14_155)]" />
                      )}
                      <Icon
                        className={cn(
                          "h-[15px] w-[15px] shrink-0 transition-opacity",
                          active
                            ? "opacity-100"
                            : "opacity-60 group-hover:opacity-90",
                        )}
                      />
                      {item.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div className="border-t border-nav-border px-5 py-4">
        <p className="text-[10.5px] leading-relaxed text-nav-muted">
          Government operational portal for processing industrial applications.
        </p>
        <div className="mt-2 flex items-center justify-between">
          <p className="text-[9.5px] uppercase tracking-[0.09em] text-nav-muted/60">
            {isDemoMode
              ? "Auth: Demo mode"
              : `Auth: ${irisUser?.role ?? "Active"}`}
          </p>
          {isDemoMode && (
            <span className="rounded bg-warning/20 px-1.5 py-0.5 text-[9px] font-medium text-warning">
              DEMO
            </span>
          )}
        </div>
      </div>
    </aside>
  );
}

function DeptHeader() {
  const { irisUser, isDemoMode, signOut } = useAuth();
  const userName = irisUser?.name || "Government Officer";
  const userRole = irisUser?.role?.replace("_", " ") || "Officer";
  const initials =
    userName
      .split(" ")
      .map((n) => n[0])
      .join("")
      .slice(0, 2)
      .toUpperCase() || "GO";

  return (
    <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center gap-4 border-b border-border bg-surface/90 px-5 backdrop-blur-md [box-shadow:var(--shadow-header)]">
      <div className="flex items-center gap-2.5 lg:hidden">
        <span className="flex h-7 w-7 items-center justify-center rounded-md bg-gradient-to-br from-[oklch(0.42_0.14_155)] to-[oklch(0.32_0.12_155)] text-[11px] font-semibold text-white">
          GO
        </span>
        <span className="text-[14px] font-semibold">IRIS Gov</span>
      </div>

      <div className="hidden items-center gap-2 border-l border-border pl-4 md:flex">
        <Building2 className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="label-meta">Department</span>
        <span className="text-[12.5px] font-medium">
          {irisUser?.department_name || "Government Portal"}
        </span>
      </div>

      <div className="ml-auto flex items-center gap-2">
        <Link
          to="/department/applications"
          className="focus-ring hidden items-center gap-2 rounded-md border border-border px-2.5 py-[7px] text-[12.5px] text-muted-foreground transition-colors duration-150 hover:border-border-strong hover:bg-secondary md:flex"
        >
          <Search className="h-[14px] w-[14px]" />
          Search applications
        </Link>
        <DropdownMenu>
          <DropdownMenuTrigger
            aria-label="Notifications"
            className="focus-ring flex h-8 w-8 items-center justify-center rounded-md border border-transparent text-muted-foreground transition-colors duration-150 hover:border-border hover:bg-secondary"
          >
            <Bell className="h-[16px] w-[16px]" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-[260px] rounded-md">
            <DropdownMenuLabel className="label-meta px-2 py-1.5">
              Notifications
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <p className="px-2 py-3 text-[12px] leading-relaxed text-muted-foreground">
              No notifications. This prototype does not yet generate
              notification events.
            </p>
          </DropdownMenuContent>
        </DropdownMenu>

        <div className="ml-1.5 flex items-center gap-2.5 border-l border-border pl-3">
          <div className="hidden text-right leading-tight sm:block">
            <div className="text-[12.5px] font-medium">{userName}</div>
            <div className="text-[11px] text-muted-foreground">
              {userRole} {isDemoMode && "· Demo"}
            </div>
          </div>
          <span className="flex h-8 w-8 items-center justify-center rounded-md bg-gradient-to-br from-[oklch(0.42_0.14_155)] to-[oklch(0.32_0.12_155)] text-[11.5px] font-semibold text-white">
            {initials}
          </span>
          {!isDemoMode && (
            <button
              onClick={() => void signOut()}
              title="Sign out"
              className="flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            >
              <LogOut className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>
    </header>
  );
}

function DeptMobileNav() {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const items = deptNavSections.flatMap((s) => s.items);
  return (
    <div className="flex gap-1 overflow-x-auto border-b border-border bg-surface px-3 py-2 lg:hidden">
      {items.map((item) => {
        const active = item.exact
          ? pathname === item.to
          : pathname.startsWith(item.to);
        return (
          <Link
            key={item.to}
            to={item.to as "/department"}
            className={cn(
              "whitespace-nowrap rounded-sm px-2.5 py-1.5 text-[12.5px] transition-colors",
              active
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-secondary",
            )}
          >
            {item.label}
          </Link>
        );
      })}
    </div>
  );
}

export function DepartmentShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen bg-background">
      <DeptSidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <DeptHeader />
        <DeptMobileNav />
        <main className="min-w-0 flex-1">{children}</main>
      </div>
    </div>
  );
}
