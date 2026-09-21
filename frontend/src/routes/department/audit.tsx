import { createFileRoute } from "@tanstack/react-router";
import { PageShell, PageHeader, EmptyState } from "@/components/iris/page";

export const Route = createFileRoute("/department/audit")({
  head: () => ({ meta: [{ title: "Audit Log — IRIS Gov" }] }),
  component: AuditPage,
});

function AuditPage() {
  return (
    <PageShell>
      <PageHeader
        trail={[
          { label: "Department", to: "/department" },
          { label: "Audit Log" },
        ]}
        title="Audit Log"
        description="Department-wide operational audit trail."
      />
      <div className="mt-8">
        <EmptyState
          title="Cross-application audit log — coming soon"
          description="This section will display a paginated, filterable audit trail of all operational events across all applications, with actor attribution and event type breakdown."
        />
      </div>
    </PageShell>
  );
}
