import { createFileRoute } from "@tanstack/react-router";
import { PageShell, PageHeader, EmptyState } from "@/components/iris/page";

export const Route = createFileRoute("/department/settings")({
  head: () => ({ meta: [{ title: "Settings — IRIS Gov" }] }),
  component: SettingsPage,
});

function SettingsPage() {
  return (
    <PageShell>
      <PageHeader
        trail={[
          { label: "Department", to: "/department" },
          { label: "Settings" },
        ]}
        title="Settings"
        description="Department portal configuration."
      />
      <div className="mt-8">
        <EmptyState
          title="Department settings — coming soon"
          description="Configure department details, notification preferences, and Supabase Auth integration."
        />
      </div>
    </PageShell>
  );
}
