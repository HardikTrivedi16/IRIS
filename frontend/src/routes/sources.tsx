import { createFileRoute } from "@tanstack/react-router";
import { Library, ShieldCheck } from "lucide-react";
import { regulatorySources } from "@/lib/iris/mock-data";
import { PageHeader, PageShell, DataField } from "@/components/iris/page";
import { Tag } from "@/components/iris/status";

export const Route = createFileRoute("/sources")({
  head: () => ({
    meta: [
      { title: "Regulatory Sources — IRIS" },
      {
        name: "description",
        content:
          "Official regulatory authorities and source registers underpinning IRIS requirement intelligence.",
      },
      { property: "og:title", content: "Regulatory Sources — IRIS" },
      {
        property: "og:description",
        content:
          "The authorities and official source registers IRIS references for requirement determinations.",
      },
    ],
  }),
  component: SourcesPage,
});

function SourcesPage() {
  return (
    <PageShell wide>
      <PageHeader
        trail={[{ label: "Oversight" }, { label: "Sources" }]}
        title="Regulatory Sources"
        description="Official authorities backing every requirement in this workspace"
        meta={
          <div className="flex items-baseline gap-2">
            <span className="tabular text-[15px] font-semibold">
              {regulatorySources.length}
            </span>
            <span className="text-[12.5px] text-muted-foreground">
              tracked authorities
            </span>
          </div>
        }
      />

      <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {regulatorySources.map((source) => (
          <div
            key={source.id}
            className="row-hover flex flex-col border border-border bg-surface px-5 py-4 hover:bg-surface-sunken"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-2.5">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-sm border border-border bg-surface-sunken text-[11px] font-semibold">
                  {source.name.slice(0, 3)}
                </span>
                <div>
                  <h3 className="text-[13.5px] font-semibold leading-snug">
                    {source.name}
                  </h3>
                  <p className="text-[11.5px] text-muted-foreground">
                    {source.fullName}
                  </p>
                </div>
              </div>
            </div>
            <p className="mt-3 text-[12.5px] leading-relaxed text-muted-foreground">
              {source.description}
            </p>
            <div className="mt-4 grid grid-cols-2 gap-3 border-t border-border pt-3">
              <DataField
                label="Source type"
                value={<span className="text-[12px]">{source.sourceType}</span>}
              />
              <DataField
                label="Last verified"
                value={
                  <span className="tabular text-[12px]">
                    {source.lastVerified}
                  </span>
                }
              />
            </div>
            <div className="mt-3 flex items-center gap-1.5 text-[11px] text-muted-foreground">
              <ShieldCheck className="h-3 w-3" />
              {source.documentCount}
            </div>
          </div>
        ))}
      </div>

      <section className="mt-8 flex items-start gap-3 border border-border bg-surface px-5 py-4">
        <Library className="mt-[2px] h-4 w-4 shrink-0 text-muted-foreground" />
        <div>
          <p className="text-[13px] font-medium">
            Source verification status
          </p>
          <p className="mt-1.5 max-w-[80ch] text-[12.5px] leading-relaxed text-muted-foreground">
            This is a directory of the authorities IRIS's project data refers
            to. The underlying source records (instruments, sections, clauses)
            are not yet loaded — regulatory research is in progress — so every
            engine decision currently shows its source as unresolved rather
            than an unverified citation. IRIS does not monitor these sources
            for changes.
          </p>
          <div className="mt-3">
            <Tag>Prototype dataset</Tag>
          </div>
        </div>
      </section>
    </PageShell>
  );
}
