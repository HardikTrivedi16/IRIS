import { Link } from "@tanstack/react-router";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

export function PageShell({
  children,
  className,
  wide,
}: {
  children: React.ReactNode;
  className?: string;
  wide?: boolean;
}) {
  return (
    <div className={cn("animate-page-in px-5 py-6 md:px-8 md:py-8", className)}>
      <div
        className={cn(
          "mx-auto w-full",
          wide ? "max-w-[1560px]" : "max-w-[1280px]",
        )}
      >
        {children}
      </div>
    </div>
  );
}

export function Breadcrumbs({
  trail,
}: {
  trail: { label: string; to?: string }[];
}) {
  return (
    <nav
      aria-label="Breadcrumb"
      className="flex items-center gap-1.5 text-[11.5px] text-muted-foreground"
    >
      {trail.map((item, i) => (
        <span key={item.label} className="flex items-center gap-1.5">
          {i > 0 && <ChevronRight className="h-3 w-3 opacity-60" />}
          {item.to ? (
            <Link
              to={item.to}
              className="transition-colors hover:text-foreground"
            >
              {item.label}
            </Link>
          ) : (
            <span className="text-foreground/70">{item.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}

export function PageHeader({
  title,
  description,
  trail,
  actions,
  meta,
  className,
}: {
  title: string;
  description?: string;
  trail?: { label: string; to?: string }[];
  actions?: React.ReactNode;
  meta?: React.ReactNode;
  className?: string;
}) {
  return (
    <header className={cn("border-b border-border pb-5", className)}>
      {trail && <Breadcrumbs trail={trail} />}
      <div className="mt-2.5 flex flex-wrap items-end justify-between gap-x-8 gap-y-3">
        <div className="min-w-0">
          <h1 className="text-[23px] font-semibold leading-tight tracking-[-0.02em]">
            {title}
          </h1>
          {description && (
            <p className="mt-1.5 max-w-[62ch] text-[13px] leading-relaxed text-muted-foreground">
              {description}
            </p>
          )}
        </div>
        {actions && (
          <div className="flex flex-wrap items-center gap-2">{actions}</div>
        )}
      </div>
      {meta && <div className="mt-4">{meta}</div>}
    </header>
  );
}

export function SectionHeading({
  title,
  hint,
  actions,
  className,
}: {
  title: string;
  hint?: string;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-baseline justify-between gap-3",
        className,
      )}
    >
      <div>
        <h2 className="text-[13.5px] font-semibold tracking-tight">{title}</h2>
        {hint && (
          <p className="mt-1 text-[12.5px] leading-relaxed text-muted-foreground">
            {hint}
          </p>
        )}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

/**
 * Compact, scannable metric line — e.g. "18 Applicable · 2 Blocked · 2 Need info".
 * Prefer this over a prose sentence whenever a status/count summary is being communicated.
 */
export function StatLine({
  items,
  className,
}: {
  items: {
    value: React.ReactNode;
    label: string;
    tone?: "success" | "warning" | "danger" | "info" | "neutral";
  }[];
  className?: string;
}) {
  const toneClass: Record<string, string> = {
    success: "text-success",
    warning: "text-warning",
    danger: "text-destructive",
    info: "text-info",
    neutral: "text-foreground",
  };
  return (
    <div className={cn("stat-line", className)}>
      {items.map((item, i) => (
        <span key={i} className="flex items-baseline gap-1.5">
          <b className={item.tone ? toneClass[item.tone] : undefined}>
            {item.value}
          </b>
          {item.label}
        </span>
      ))}
    </div>
  );
}

export function DataField({
  label,
  value,
  className,
}: {
  label: string;
  value: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={className}>
      <div className="label-meta">{label}</div>
      <div className="mt-1 text-[13px] font-medium leading-snug">{value}</div>
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-start gap-2 border border-dashed border-border bg-surface px-6 py-10">
      <p className="text-[13.5px] font-medium">{title}</p>
      <p className="max-w-[52ch] text-[12.5px] leading-relaxed text-muted-foreground">
        {description}
      </p>
      {action}
    </div>
  );
}

export function Drawer({
  open,
  onClose,
  eyebrow,
  title,
  subtitle,
  children,
  footer,
  wide = false,
}: {
  open: boolean;
  onClose: () => void;
  eyebrow: string;
  title: string;
  subtitle?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  /** Wider panel for dense content (e.g. a Decision Proof). */
  wide?: boolean;
}) {
  if (!open) return null;
  return (
    <>
      <div
        className="fixed inset-0 z-40 bg-foreground/10 lg:bg-transparent"
        onClick={onClose}
        aria-hidden
      />
      <aside
        className={cn(
          "animate-drawer-in fixed right-0 top-0 z-50 flex h-screen w-full flex-col border-l border-border bg-surface shadow-drawer",
          wide ? "max-w-[600px]" : "max-w-[420px]",
        )}
      >
        <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
          <div className="min-w-0">
            <div className="label-meta">{eyebrow}</div>
            <h2 className="mt-1.5 text-[15px] font-semibold leading-snug">
              {title}
            </h2>
            {subtitle && <div className="mt-2">{subtitle}</div>}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close panel"
            className="focus-ring -mr-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          >
            <span aria-hidden className="text-[16px] leading-none">
              ×
            </span>
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
        {footer && (
          <div className="border-t border-border px-5 py-4">{footer}</div>
        )}
      </aside>
    </>
  );
}

export function DrawerSection({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cn(
        "border-b border-border px-5 py-4 last:border-b-0",
        className,
      )}
    >
      <div className="label-meta">{label}</div>
      <div className="mt-2 text-[13px] leading-relaxed">{children}</div>
    </section>
  );
}
