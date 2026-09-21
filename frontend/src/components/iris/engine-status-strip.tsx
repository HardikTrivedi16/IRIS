import { Tag } from "@/components/iris/status";
import { useEngineInfo } from "@/lib/iris/use-engine-decision";
import { BackendUnavailableError } from "@/lib/iris/api-client";

/**
 * Compact strip that tells the truth about the connected regulatory
 * engine: whether the backend is reachable, and — since it's the single
 * most important thing not to hide — that every Rule Version in the
 * dataset is currently DRAFT, so no requirement below is production-active
 * yet even when the engine is live.
 */
export function EngineStatusStrip() {
  const { data, isLoading, isError, error } = useEngineInfo();

  if (isLoading) return null;

  if (isError) {
    const unreachable = error instanceof BackendUnavailableError;
    return (
      <div className="mt-5 flex items-center gap-2 border border-dashed border-border bg-surface px-4 py-2.5">
        <Tag tone="neutral">Engine offline</Tag>
        <p className="text-[12px] text-muted-foreground">
          {unreachable
            ? "Regulatory engine backend not reachable — showing prototype data only."
            : "Regulatory engine returned an error."}
        </p>
      </div>
    );
  }

  if (!data) return null;

  const activeCount = data.counts.rule_versions_by_status["ACTIVE"] ?? 0;
  const draftCount = data.counts.rule_versions_by_status["DRAFT"] ?? 0;

  return (
    <div className="mt-5 flex flex-wrap items-center gap-3 border border-border bg-surface px-4 py-2.5">
      <Tag tone={activeCount > 0 ? "success" : "warning"}>
        Engine {data.current_engine_version} · {activeCount} active /{" "}
        {draftCount} draft rule version
        {draftCount === 1 ? "" : "s"}
      </Tag>
      {activeCount === 0 && (
        <p className="text-[12px] text-muted-foreground">
          No Rule Version is ACTIVE yet — production evaluations are correctly
          blocked until one is promoted.
        </p>
      )}
    </div>
  );
}
