import { cn } from "@/lib/utils";
import type { Status } from "@/lib/iris/types";

type Tone = "success" | "warning" | "danger" | "info" | "neutral";

export const statusMeta: Record<Status, { label: string; tone: Tone }> = {
  ready: { label: "Completed", tone: "success" },
  attention: { label: "Action required", tone: "warning" },
  blocked: { label: "Blocked", tone: "danger" },
  "not-ready": { label: "Not started", tone: "neutral" },
  "not-applicable": { label: "Not applicable", tone: "neutral" },
};

const toneClasses: Record<Tone, string> = {
  success: "border-success/25 bg-success-surface text-success",
  warning: "border-warning/30 bg-warning-surface text-warning",
  danger: "border-destructive/25 bg-danger-surface text-destructive",
  info: "border-info/25 bg-info-surface text-info",
  neutral: "border-border bg-neutral-surface text-muted-foreground",
};

const dotClasses: Record<Tone, string> = {
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-destructive",
  info: "bg-info",
  neutral: "bg-border-strong",
};

export function toneFor(status: Status): Tone {
  return statusMeta[status].tone;
}

export function StatusDot({
  status,
  className,
}: {
  status: Status;
  className?: string;
}) {
  return (
    <span
      aria-hidden
      className={cn(
        "inline-block h-[6px] w-[6px] shrink-0 rounded-full",
        dotClasses[toneFor(status)],
        className,
      )}
    />
  );
}

export function StatusBadge({
  status,
  label,
  className,
}: {
  status: Status;
  label?: string;
  className?: string;
}) {
  const meta = statusMeta[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-sm border px-2 py-[3px] text-[11px] font-medium leading-none",
        toneClasses[meta.tone],
        className,
      )}
    >
      <StatusDot status={status} />
      {label ?? meta.label}
    </span>
  );
}

export function Tag({
  children,
  tone = "neutral",
  className,
}: {
  children: React.ReactNode;
  tone?: Tone;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-sm border px-2 py-[3px] text-[11px] font-medium leading-none",
        toneClasses[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Meter({
  value,
  total,
  tone = "info",
  className,
}: {
  value: number;
  total: number;
  tone?: Tone;
  className?: string;
}) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0;
  return (
    <div
      className={cn(
        "h-[3px] w-full overflow-hidden rounded-full bg-border",
        className,
      )}
    >
      <div
        className={cn(
          "h-full transition-[width] duration-500 ease-out",
          dotClasses[tone],
        )}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
