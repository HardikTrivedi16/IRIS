import { Link, useRouterState, useNavigate } from "@tanstack/react-router";
import {
  Bell,
  Building2,
  ChevronDown,
  FileText,
  GitCompare,
  LayoutGrid,
  Library,
  ListChecks,
  LogOut,
  MessagesSquare,
  Network,
  Search,
  ShieldCheck,
  FolderClosed,
  Scale,
  Plus,
  MessageSquareWarning,
  Landmark,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { ProjectProvider, useProject } from "@/lib/iris/project-context";
import { useAuth } from "@/lib/auth-context";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const navSections: {
  label: string;
  items: { label: string; to: string; icon: typeof LayoutGrid }[];
}[] = [
  {
    label: "Workspace",
    items: [
      { label: "Overview", to: "/", icon: LayoutGrid },
      { label: "Projects", to: "/projects", icon: FolderClosed },
    ],
  },
  {
    label: "Regulatory intelligence",
    items: [
      { label: "Evaluation", to: "/evaluation", icon: Scale },
      { label: "Regulatory Map", to: "/regulatory-map", icon: Network },
      { label: "Requirements", to: "/requirements", icon: ListChecks },
      { label: "Documents", to: "/documents", icon: FileText },
      { label: "Change Impact", to: "/change-impact", icon: GitCompare },
    ],
  },
  {
    label: "Oversight",
    items: [
      { label: "Compliance", to: "/compliance", icon: ShieldCheck },
      { label: "Grievances", to: "/grievances", icon: MessageSquareWarning },
      { label: "Schemes", to: "/schemes", icon: Landmark },
      { label: "Sources", to: "/sources", icon: Library },
      { label: "Ask IRIS", to: "/assistant", icon: MessagesSquare },
    ],
  },
];

function Sidebar() {
  const pathname = useRouterState({ select: (s) => s.location.pathname });

  return (
    <aside className="sticky top-0 hidden h-screen w-[228px] shrink-0 flex-col border-r border-nav-border bg-nav lg:flex">
      <div className="flex h-14 items-center gap-2.5 border-b border-nav-border px-5">
        <span className="flex h-7 w-7 items-center justify-center rounded-md bg-gradient-to-br from-[oklch(0.56_0.16_280)] to-[oklch(0.4_0.15_282)] text-[12px] font-semibold tracking-tight text-white shadow-[0_1px_2px_rgba(30,20,70,0.4)]">
          IR
        </span>
        <div className="leading-none">
          <div className="text-[14.5px] font-semibold tracking-tight text-nav-foreground">
            IRIS
          </div>
          <div className="mt-1 text-[9px] font-medium uppercase tracking-[0.1em] text-nav-muted">
            Regulatory Intelligence
          </div>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-4">
        {navSections.map((section, i) => (
          <div key={section.label} className={cn(i > 0 && "mt-5")}>
            <p className="px-2.5 pb-1.5 text-[9.5px] font-semibold uppercase tracking-[0.1em] text-nav-muted/70">
              {section.label}
            </p>
            <ul className="space-y-px">
              {section.items.map((item) => {
                const Icon = item.icon;
                const active =
                  item.to === "/"
                    ? pathname === "/"
                    : pathname.startsWith(item.to);
                return (
                  <li key={item.to}>
                    <Link
                      to={item.to}
                      className={cn(
                        "focus-ring group relative flex items-center gap-2.5 rounded-md px-2.5 py-[7px] text-[13px] transition-colors duration-150",
                        active
                          ? "bg-nav-active font-medium text-nav-foreground"
                          : "text-nav-muted hover:bg-white/[0.05] hover:text-nav-foreground",
                      )}
                    >
                      {active && (
                        <span className="absolute -left-3 top-1/2 h-4 w-[3px] -translate-y-1/2 rounded-full bg-[oklch(0.68_0.16_282)]" />
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

      <div className="border-t border-nav-border px-3 py-2.5">
        <Link
          to="/department"
          className="flex items-center gap-2 rounded-md px-2.5 py-[7px] text-[11.5px] text-nav-muted transition-colors hover:bg-white/[0.05] hover:text-nav-foreground"
        >
          <span className="flex h-4 w-4 items-center justify-center rounded-sm bg-gradient-to-br from-[oklch(0.42_0.14_155)] to-[oklch(0.32_0.12_155)] text-[8px] font-bold text-white">
            G
          </span>
          Switch to Gov Portal
        </Link>
      </div>
      <div className="border-t border-nav-border px-5 py-4">
        <p className="text-[10.5px] leading-relaxed text-nav-muted">
          A project-level intelligence layer around NSWS and MAITRI approvals.
        </p>
        <p className="mt-2 text-[9.5px] uppercase tracking-[0.09em] text-nav-muted/60">
          Prototype build 0.9
        </p>
      </div>
    </aside>
  );
}

function ProjectSwitcher() {
  const { activeProject, projects, setActiveProjectId } = useProject();
  const navigate = useNavigate();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="focus-ring flex items-center gap-2.5 rounded-md border border-border bg-surface px-2.5 py-[7px] text-left transition-colors duration-150 hover:border-border-strong hover:bg-secondary">
        <Building2 className="h-[15px] w-[15px] text-muted-foreground" />
        <span className="max-w-[220px] truncate text-[13px] font-medium">
          {activeProject.name}
        </span>
        <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-[300px] rounded-md">
        <DropdownMenuLabel className="label-meta px-2 py-1.5">
          Active project
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {projects.map((p) => (
          <DropdownMenuItem
            key={p.id}
            onSelect={() => setActiveProjectId(p.id)}
            className="flex flex-col items-start gap-0.5 rounded-sm py-2"
          >
            <span className="text-[13px] font-medium">{p.name}</span>
            <span className="text-[11.5px] text-muted-foreground">
              {p.activity} · {p.location}
            </span>
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={() => void navigate({ to: "/projects", search: { new: true } })}
          className="flex items-center gap-2 rounded-sm py-2 text-[13px]"
        >
          <Plus className="h-3.5 w-3.5 text-muted-foreground" />
          New project…
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function Header() {
  const { irisUser, isDemoMode, signOut } = useAuth();
  const userName = irisUser?.name || "Industry User";
  const userRole = irisUser?.role?.replace("_", " ") || "Applicant";
  const initials =
    userName
      .split(" ")
      .map((n) => n[0])
      .join("")
      .slice(0, 2)
      .toUpperCase() || "IU";

  return (
    <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center gap-4 border-b border-border bg-surface/90 px-5 backdrop-blur-md [box-shadow:var(--shadow-header)]">
      <div className="flex items-center gap-2.5 lg:hidden">
        <span className="flex h-7 w-7 items-center justify-center rounded-md bg-gradient-to-br from-[oklch(0.56_0.16_280)] to-[oklch(0.4_0.15_282)] text-[11px] font-semibold text-white">
          IR
        </span>
        <span className="text-[14px] font-semibold">IRIS</span>
      </div>

      <ProjectSwitcher />

      <div className="hidden items-center gap-2 border-l border-border pl-4 md:flex">
        <span className="label-meta">Jurisdiction</span>
        <span className="text-[12.5px] font-medium">Maharashtra, India</span>
      </div>

      <div className="ml-auto flex items-center gap-1.5">
        <Link
          to="/requirements"
          className="focus-ring hidden items-center gap-2 rounded-md border border-border px-2.5 py-[7px] text-[12.5px] text-muted-foreground transition-colors duration-150 hover:border-border-strong hover:bg-secondary md:flex"
        >
          <Search className="h-[14px] w-[14px]" />
          Search requirements
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
            <div className="text-[11px] capitalize text-muted-foreground">
              {userRole.toLowerCase()} {isDemoMode && "· Demo"}
            </div>
          </div>
          <span className="flex h-8 w-8 items-center justify-center rounded-md bg-gradient-to-br from-[oklch(0.56_0.16_280)] to-[oklch(0.4_0.15_282)] text-[11.5px] font-semibold text-white">
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

function MobileNav() {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const items = navSections.flatMap((s) => s.items);
  return (
    <div className="flex gap-1 overflow-x-auto border-b border-border bg-surface px-3 py-2 lg:hidden">
      {items.map((item) => {
        const active =
          item.to === "/" ? pathname === "/" : pathname.startsWith(item.to);
        return (
          <Link
            key={item.to}
            to={item.to}
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

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <ProjectProvider>
      <div className="flex min-h-screen bg-background">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <Header />
          <MobileNav />
          <main className="min-w-0 flex-1">{children}</main>
        </div>
      </div>
    </ProjectProvider>
  );
}
