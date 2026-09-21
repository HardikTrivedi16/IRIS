import { createFileRoute, Link } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import {
  PreSubmissionCheck,
  observationsFromExtraction,
  type CheckSource,
} from "@/components/iris/pre-submission-check";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, Sparkles, Upload } from "lucide-react";
import { useProject } from "@/lib/iris/project-context";
import {
  useProjectDocuments,
  useProjectRequirements,
} from "@/lib/iris/use-project-data";
import {
  ApiError,
  BackendUnavailableError,
  irisApi,
  type ExtractedDocumentFields,
} from "@/lib/iris/api-client";
import {
  PageHeader,
  PageShell,
  Drawer,
  DrawerSection,
  DataField,
  EmptyState,
  SectionHeading,
  StatLine,
} from "@/components/iris/page";
import { StatusBadge, StatusDot, Tag } from "@/components/iris/status";
import type { DocumentItem, Status } from "@/lib/iris/types";
import { cn } from "@/lib/utils";

// Extracted-field keys the "Live document extraction" panel below lets a
// human review and selectively confirm. Order matches the schema in
// backend/app/modules/ai/schemas.py::ApplicantDocumentExtraction — this
// list is display-only, it does not change what the AI module returns.
const EXTRACTED_FIELD_LABELS: { key: keyof ExtractedDocumentFields; label: string }[] = [
  { key: "business_name", label: "Business / applicant name" },
  { key: "project_name", label: "Project name" },
  { key: "registration_number", label: "Registration / licence number" },
  { key: "location", label: "Location" },
  { key: "state", label: "State" },
  { key: "district", label: "District" },
  { key: "capacity_value", label: "Capacity (value)" },
  { key: "capacity_unit", label: "Capacity (unit)" },
  { key: "investment_crore_inr", label: "Investment (₹ crore)" },
  { key: "worker_count", label: "Worker count" },
  { key: "authorised_person", label: "Authorised person" },
  { key: "issue_date", label: "Issue date" },
  { key: "valid_until", label: "Valid until" },
];

/**
 * Confirmed values are written to Project Facts under a `document.<field>`
 * namespace — deliberately NOT asserted to be an engine-recognized
 * `project.*` regulatory fact (no such mapping exists between free-form
 * applicant-document fields and the Phase 9 dataset's specific required
 * facts; inventing one would be fabricating a regulatory equivalence).
 * This keeps the confirmation honest: it persists exactly what the human
 * reviewed and approved, nothing more.
 */
function factKeyFor(field: string): string {
  return `document.${field}`;
}

export const Route = createFileRoute("/documents")({
  head: () => ({
    meta: [
      { title: "Document Register — IRIS" },
      {
        name: "description",
        content:
          "Register of uploaded evidence and documentation, with extraction status, mismatches and missing information for the active project.",
      },
      { property: "og:title", content: "Document Register — IRIS" },
      {
        property: "og:description",
        content:
          "Track document extraction, mismatches and outstanding information requests.",
      },
    ],
  }),
  component: DocumentsPage,
});

function LiveExtractionPanel({
  projectId,
  onAddToCheck,
}: {
  projectId: string;
  onAddToCheck: (source: CheckSource) => void;
}) {
  const queryClient = useQueryClient();
  const [text, setText] = useState("");
  const [checkDocName, setCheckDocName] = useState("");
  const [addedToCheck, setAddedToCheck] = useState<string | null>(null);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [confirmedCount, setConfirmedCount] = useState<number | null>(null);
  const [ocrNotice, setOcrNotice] = useState<string | null>(null);

  const aiStatus = useQuery({
    queryKey: ["ai-status"],
    queryFn: irisApi.getAiStatus,
    staleTime: 30_000,
    retry: false,
  });

  const ocrMutation = useMutation({
    mutationFn: (file: File) => irisApi.ocrExtract(projectId, file),
    onSuccess: (result) => {
      // OCR only fills the text box for review/editing — it does NOT run
      // extraction or touch Project Facts by itself. The human still
      // presses "Extract" below, exactly like a pasted-text flow.
      setText(result.text);
      setOcrNotice(
        result.warnings.length > 0
          ? result.warnings.join(" ")
          : result.pages
            ? `Read ${result.page_count} page(s): ${result.pages
                .map((pg) => `p.${pg.page} ${pg.method === "EMBEDDED_TEXT" ? "embedded text" : pg.method === "OCR" ? "OCR" : pg.method.replace(/_/g, " ").toLowerCase()}`)
                .join(", ")}. Review/edit below, then Extract.`
            : `Recognized ${result.char_count} characters with ${result.engine}. Review/edit below, then Extract.`,
      );
    },
  });

  const extractMutation = useMutation({
    mutationFn: () => irisApi.extractDocument(projectId, { text }),
    onSuccess: () => {
      setSelected({});
      setConfirmedCount(null);
      setAddedToCheck(null);
    },
  });

  const confirmMutation = useMutation({
    mutationFn: async (fields: Record<string, unknown>) => {
      await irisApi.mergeProjectFacts(projectId, fields);
      await irisApi.createDocument(projectId, {
        name: `Pasted document — ${new Date().toLocaleString()}`,
        status: "extracted",
      });
      return fields;
    },
    onSuccess: (fields) => {
      setConfirmedCount(Object.keys(fields).length);
      queryClient.invalidateQueries({ queryKey: ["real-documents", projectId] });
      // Also refresh the main register (useProjectDocuments) so a newly
      // recorded document appears there without a page reload.
      queryClient.invalidateQueries({ queryKey: ["project-documents", projectId] });
    },
  });

  const realDocuments = useQuery({
    queryKey: ["real-documents", projectId],
    queryFn: () => irisApi.listDocuments(projectId),
    staleTime: 10_000,
  });

  const data = extractMutation.data?.data;

  function toggle(key: string) {
    setSelected((s) => ({ ...s, [key]: !s[key] }));
  }

  function confirmSelected() {
    if (!data) return;
    const fields: Record<string, unknown> = {};
    for (const { key } of EXTRACTED_FIELD_LABELS) {
      const value = data[key];
      if (selected[key] && value !== null && value !== undefined) {
        fields[factKeyFor(key)] = value;
      }
    }
    if (Object.keys(fields).length === 0) return;
    confirmMutation.mutate(fields);
  }

  let errorMessage: string | null = null;
  if (extractMutation.isError) {
    const err = extractMutation.error;
    if (err instanceof BackendUnavailableError) {
      errorMessage = "The IRIS backend is unreachable right now.";
    } else if (err instanceof ApiError && err.status === 503) {
      errorMessage =
        "The AI extraction service (Ollama) is currently unreachable. Try again once it's back up.";
    } else if (err instanceof ApiError && err.status === 422) {
      errorMessage = "This text could not be processed for extraction.";
    } else {
      errorMessage = "Extraction failed. Please try again.";
    }
  }

  let ocrErrorMessage: string | null = null;
  if (ocrMutation.isError) {
    const err = ocrMutation.error;
    if (err instanceof BackendUnavailableError) {
      ocrErrorMessage = "The IRIS backend is unreachable right now.";
    } else if (err instanceof ApiError && err.status === 503) {
      ocrErrorMessage =
        "The local Tesseract OCR engine is unreachable. Confirm it's installed and on PATH, or paste text directly.";
    } else if (err instanceof ApiError && err.status === 422) {
      ocrErrorMessage = err.message || "This file could not be read for OCR.";
    } else {
      ocrErrorMessage = "OCR failed. Please try again, or paste text directly.";
    }
  }

  const ocrAvailable = aiStatus.data?.ocr_available ?? true; // optimistic until known

  const populatedFields = data
    ? EXTRACTED_FIELD_LABELS.filter(
        ({ key }) => data[key] !== null && data[key] !== undefined,
      )
    : [];

  return (
    <section id="live-extraction" className="mt-8">
      <SectionHeading
        title="Live document extraction"
        hint="Calls the real IRIS AI extraction API — separate from the prototype register below."
      />
      <div className="mt-3 border border-border bg-surface px-5 py-5">
        <Tag tone="info">
          <Sparkles className="h-3 w-3" />
          Live — OCR + AI extraction + human confirmation
        </Tag>
        <p className="mt-2 text-[11.5px] leading-relaxed text-muted-foreground">
          Upload a scanned image to run local OCR (Tesseract), or paste
          document text directly — either way, review the text below before
          extracting. The AI then extracts candidate fields with confidence
          and evidence; nothing is saved until you review and confirm
          specific fields. Confirmed values are stored as this project's
          Project Facts under the <code className="font-mono">document.*</code>{" "}
          namespace — confirming does not assert that a value satisfies any
          specific Phase 9 regulatory requirement. This is local OCR, not a
          cloud document pipeline. PDFs are read from their embedded
          text; only pages without usable text are OCR'd, and each page's
          method is shown.
        </p>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <label
            className={cn(
              "focus-ring inline-flex cursor-pointer items-center gap-1.5 rounded-sm border border-border px-3 py-[7px] text-[12.5px] font-medium transition-colors hover:bg-secondary",
              (!ocrAvailable || ocrMutation.isPending) &&
                "cursor-not-allowed opacity-40",
            )}
          >
            <Upload className="h-[13px] w-[13px]" />
            {ocrMutation.isPending ? "Reading document…" : "Upload image or PDF"}
            <input
              type="file"
              accept="image/png,image/jpeg,image/webp,image/bmp,image/tiff,application/pdf"
              className="hidden"
              disabled={!ocrAvailable || ocrMutation.isPending}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) ocrMutation.mutate(file);
                e.target.value = "";
              }}
            />
          </label>
          {!ocrAvailable && (
            <span className="text-[11.5px] text-warning">
              OCR engine not detected on the backend host.
            </span>
          )}
        </div>

        {ocrErrorMessage && (
          <p className="mt-2 border-l-2 border-destructive pl-3 text-[12.5px] text-destructive">
            {ocrErrorMessage}
          </p>
        )}
        {!ocrErrorMessage && ocrNotice && (
          <p className="mt-2 border-l-2 border-info pl-3 text-[12.5px] text-muted-foreground">
            {ocrNotice}
          </p>
        )}

        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={5}
          placeholder="Paste applicant document text here, or upload an image above to OCR it…"
          className="focus-ring mt-3 w-full rounded-sm border border-border bg-surface px-3 py-2 text-[12.5px]"
        />
        <div className="mt-2 flex items-center gap-2">
          <button
            type="button"
            onClick={() => extractMutation.mutate()}
            disabled={!text.trim() || extractMutation.isPending}
            className="focus-ring inline-flex items-center gap-1.5 rounded-sm bg-primary px-3 py-[7px] text-[12.5px] font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-40"
          >
            {extractMutation.isPending ? "Extracting…" : "Extract"}
          </button>
          {extractMutation.isPending && (
            <span className="text-[11.5px] text-muted-foreground">
              Calling the AI extraction API…
            </span>
          )}
        </div>

        {errorMessage && (
          <p className="mt-3 border-l-2 border-destructive pl-3 text-[12.5px] text-destructive">
            {errorMessage}
          </p>
        )}

        {data && (
          <div className="mt-4 space-y-2 border-t border-border pt-4">
            <p className="text-[11.5px] font-semibold uppercase tracking-[0.06em] text-muted-foreground">
              Extracted fields — review and select what to confirm
            </p>
            {populatedFields.length === 0 ? (
              <p className="text-[12.5px] text-muted-foreground">
                No fields were extracted from this text.
              </p>
            ) : (
              <ul className="divide-y divide-border">
                {populatedFields.map(({ key, label }) => {
                  const value = data[key];
                  const confidence = data.field_confidence[key];
                  const evidence = data.field_evidence[key];
                  return (
                    <li key={key} className="flex items-start gap-3 py-2.5">
                      <input
                        type="checkbox"
                        checked={!!selected[key]}
                        onChange={() => toggle(key)}
                        className="mt-1"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-[12.5px] font-medium">
                            {label}
                          </span>
                          <span className="text-[12.5px]">{String(value)}</span>
                          {confidence !== undefined && (
                            <Tag tone={confidence >= 0.75 ? "success" : "warning"}>
                              {(confidence * 100).toFixed(0)}% confidence
                            </Tag>
                          )}
                        </div>
                        {evidence && (
                          <p className="mt-1 text-[11px] italic text-muted-foreground">
                            Evidence: "{evidence}"
                          </p>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}

            {extractMutation.data?.requires_human_review && (
              <Tag tone="warning">Flagged for human review</Tag>
            )}
            {(extractMutation.data?.warnings.length ?? 0) > 0 && (
              <ul className="space-y-0.5 text-[11px] text-muted-foreground">
                {extractMutation.data!.warnings.map((w, i) => (
                  <li key={i}>⚠ {w}</li>
                ))}
              </ul>
            )}

            <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-border pt-3">
              <input
                value={checkDocName}
                onChange={(e) => setCheckDocName(e.target.value)}
                placeholder="Document name (e.g. GST certificate)"
                className="focus-ring w-[260px] rounded-sm border border-border bg-surface px-2 py-[6px] text-[12.5px]"
              />
              <button
                type="button"
                onClick={() => {
                  const name = checkDocName.trim() || `Extracted document ${new Date().toLocaleTimeString()}`;
                  const id = `doc-${Date.now()}`;
                  onAddToCheck({
                    id,
                    name,
                    kind: "DOCUMENT",
                    observations: observationsFromExtraction(data, name, id),
                  });
                  setAddedToCheck(name);
                  setCheckDocName("");
                }}
                className="focus-ring inline-flex items-center gap-1.5 rounded-sm border border-border px-3 py-[7px] text-[12.5px] font-medium hover:bg-secondary"
              >
                Add to pre-submission check
              </button>
              {addedToCheck && (
                <span className="text-[11.5px] text-muted-foreground">
                  Added “{addedToCheck}” — values were not saved.
                </span>
              )}
            </div>

            <button
              type="button"
              onClick={confirmSelected}
              disabled={
                !Object.values(selected).some(Boolean) || confirmMutation.isPending
              }
              className="focus-ring mt-2 inline-flex items-center gap-1.5 rounded-sm bg-primary px-3 py-[7px] text-[12.5px] font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-40"
            >
              {confirmMutation.isPending
                ? "Saving…"
                : "Confirm selected fields as Project Facts"}
            </button>
          </div>
        )}

        {confirmedCount !== null && confirmedCount > 0 && (
          <p className="mt-3 border-l-2 border-success pl-3 text-[12.5px] text-success">
            Saved {confirmedCount} confirmed field(s) to this project's Project
            Facts.
          </p>
        )}

        {realDocuments.data && realDocuments.data.length > 0 && (
          <div className="mt-4 border-t border-border pt-3">
            <p className="text-[11.5px] font-semibold uppercase tracking-[0.06em] text-muted-foreground">
              Live documents recorded for this project ({realDocuments.data.length})
            </p>
            <ul className="mt-1.5 space-y-1 text-[12px] text-muted-foreground">
              {realDocuments.data.map((d) => (
                <li key={d.id}>
                  {d.name} · {d.status} · {new Date(d.uploaded_at).toLocaleString()}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </section>
  );
}

const docStatusMeta: Record<
  DocumentItem["status"],
  { label: string; status: Status; hint: string }
> = {
  extracted: {
    label: "Extracted",
    status: "ready",
    hint: "Information extracted and verified against the project profile.",
  },
  "missing-info": {
    label: "Missing information",
    status: "attention",
    hint: "Required information could not be extracted from this document.",
  },
  mismatch: {
    label: "Mismatch",
    status: "blocked",
    hint: "Extracted values differ from the project profile.",
  },
};

function DocumentsPage() {
  const { activeProject } = useProject();
  // Session-only sources for the pre-submission check, per project.
  const [checkSources, setCheckSources] = useState<Record<string, CheckSource[]>>({});
  const projectCheckSources = checkSources[activeProject.id] ?? [];
  const setProjectCheckSources = (fn: (prev: CheckSource[]) => CheckSource[]) =>
    setCheckSources((all) => ({ ...all, [activeProject.id]: fn(all[activeProject.id] ?? []) }));
  const { data: docs = [] } = useProjectDocuments(activeProject.id);
  const { data: reqs = [] } = useProjectRequirements(activeProject.id);
  const [filter, setFilter] = useState<"all" | DocumentItem["status"]>("all");
  const [selected, setSelected] = useState<DocumentItem | null>(null);

  const counts = useMemo(() => {
    return {
      extracted: docs.filter((d) => d.status === "extracted").length,
      "missing-info": docs.filter((d) => d.status === "missing-info").length,
      mismatch: docs.filter((d) => d.status === "mismatch").length,
    };
  }, [docs]);

  const filtered =
    filter === "all" ? docs : docs.filter((d) => d.status === filter);
  const outstanding = counts["missing-info"] + counts.mismatch;

  // Outstanding-document requirements a document register entry most likely maps to,
  // used only as contextual reference in the drawer.
  const relatedRequirement = (docId: string) => {
    if (docId.includes("hazard") || docId.includes("chemical")) {
      return reqs.find((r) => r.id === "mpcb-cte" || r.id === "mpcb-cto");
    }
    if (docId.includes("wastewater")) {
      return reqs.find((r) => r.id === "mpcb-cte");
    }
    return reqs.find(
      (r) => r.id === "building-plan" || r.id === "factory-plan",
    );
  };

  return (
    <PageShell wide>
      <PageHeader
        trail={[{ label: "Regulatory intelligence" }, { label: "Documents" }]}
        title="Document Register"
        description={`${activeProject.name} · evidence register`}
        actions={
          <>
            <Link
              to="/requirements"
              className="rounded-sm border border-border px-3 py-[7px] text-[12.5px] font-medium transition-colors hover:bg-secondary"
            >
              Requirements
            </Link>
            <button
              type="button"
              onClick={() =>
                document
                  .getElementById("live-extraction")
                  ?.scrollIntoView({ behavior: "smooth", block: "start" })
              }
              className="focus-ring inline-flex items-center gap-1.5 rounded-sm bg-primary px-3 py-[7px] text-[12.5px] font-medium text-primary-foreground transition-opacity hover:opacity-90"
            >
              <Upload className="h-[13px] w-[13px]" />
              Upload document
            </button>
          </>
        }
        meta={
          <StatLine
            items={[
              { value: docs.length, label: "in register" },
              { value: counts.extracted, label: "extracted", tone: "success" },
              {
                value: counts["missing-info"],
                label: "missing info",
                tone: "warning",
              },
              { value: counts.mismatch, label: "mismatch", tone: "danger" },
              {
                value: outstanding,
                label: "need attention before requirements can proceed",
              },
            ]}
          />
        }
      />

      <div className="mt-5 flex flex-wrap items-center gap-1 border border-border bg-surface px-2 py-2">
        {(
          [
            { key: "all", label: "All documents" },
            { key: "extracted", label: "Extracted" },
            { key: "missing-info", label: "Missing information" },
            { key: "mismatch", label: "Mismatch" },
          ] as const
        ).map((f) => (
          <button
            key={f.key}
            type="button"
            onClick={() => setFilter(f.key)}
            className={cn(
              "rounded-sm px-2.5 py-[6px] text-[12.5px] transition-colors",
              filter === f.key
                ? "bg-primary font-medium text-primary-foreground"
                : "text-muted-foreground hover:bg-secondary hover:text-foreground",
            )}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className="mt-3">
        <Tag tone="info">Live register — loaded from this project's records</Tag>
      </div>

      <div className="mt-2 border border-border bg-surface">
        {filtered.length === 0 ? (
          <EmptyState
            title="No documents match this filter"
            description="Choose a different status filter, or upload a new document to the register."
          />
        ) : (
          <ul className="divide-y divide-border">
            {filtered.map((doc) => {
              const meta = docStatusMeta[doc.status];
              return (
                <li key={doc.id}>
                  <button
                    type="button"
                    onClick={() => setSelected(doc)}
                    className="row-hover flex w-full flex-wrap items-center gap-x-6 gap-y-2 px-5 py-4 text-left hover:bg-surface-sunken"
                  >
                    <div className="flex min-w-0 flex-1 items-start gap-3">
                      <FileText className="mt-[2px] h-4 w-4 shrink-0 text-muted-foreground" />
                      <div className="min-w-0">
                        <div className="truncate text-[13px] font-medium">
                          {doc.name}
                        </div>
                        {doc.issues?.[0] && (
                          <div className="mt-1 text-[11.5px] text-muted-foreground">
                            {doc.issues[0]}
                          </div>
                        )}
                      </div>
                    </div>
                    <span className="tabular shrink-0 text-[11.5px] text-muted-foreground">
                      Uploaded {doc.uploadedAt}
                    </span>
                    <StatusBadge
                      status={meta.status}
                      label={meta.label}
                      className="shrink-0"
                    />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <section id="pre-submission-check" className="mt-8">
        <SectionHeading
          title="Pre-submission check"
          hint="What does not match before you file? Deterministic comparison — no AI decides a match."
        />
        <div className="mt-3">
          <PreSubmissionCheck
            key={activeProject.id}
            projectId={activeProject.id}
            sources={projectCheckSources}
            onAddSource={(src) => setProjectCheckSources((p) => [...p, src])}
            onRemoveSource={(id) => setProjectCheckSources((p) => p.filter((x) => x.id !== id))}
          />
        </div>
      </section>

      <LiveExtractionPanel
        projectId={activeProject.id}
        onAddToCheck={(src) => setProjectCheckSources((p) => [...p, src])}
      />

      <section className="mt-8">
        <SectionHeading
          title="About document intelligence"
          hint="How IRIS evaluates uploaded evidence against the project profile."
        />
        <div className="mt-3 grid gap-4 border border-border bg-surface px-5 py-5 sm:grid-cols-3">
          {Object.values(docStatusMeta).map((m) => (
            <div key={m.label} className="flex items-start gap-2.5">
              <StatusDot status={m.status} className="mt-[6px]" />
              <div>
                <div className="text-[12.5px] font-medium">{m.label}</div>
                <p className="mt-1 text-[11.5px] leading-relaxed text-muted-foreground">
                  {m.hint}
                </p>
              </div>
            </div>
          ))}
        </div>
      </section>

      <Drawer
        open={!!selected}
        onClose={() => setSelected(null)}
        eyebrow="Document detail"
        title={selected?.name ?? ""}
        subtitle={
          selected ? (
            <StatusBadge
              status={docStatusMeta[selected.status].status}
              label={docStatusMeta[selected.status].label}
            />
          ) : null
        }
        footer={
          <Link
            to="/requirements"
            className="inline-flex rounded-sm bg-primary px-3 py-[7px] text-[12.5px] font-medium text-primary-foreground transition-opacity hover:opacity-90"
          >
            Review related requirement
          </Link>
        }
      >
        {selected && (
          <div>
            <DrawerSection label="Upload">
              <div className="grid gap-x-5 gap-y-3 sm:grid-cols-2">
                <DataField
                  label="Uploaded"
                  value={<span className="tabular">{selected.uploadedAt}</span>}
                />
                <DataField
                  label="Status"
                  value={docStatusMeta[selected.status].label}
                />
              </div>
            </DrawerSection>

            {relatedRequirement(selected.id) && (
              <DrawerSection label="Related requirement">
                <p className="text-[12.5px] font-medium">
                  {relatedRequirement(selected.id)?.name}
                </p>
                <p className="mt-1 text-[11.5px] text-muted-foreground">
                  {relatedRequirement(selected.id)?.authority}
                </p>
              </DrawerSection>
            )}

            {selected.extractedInformation &&
              selected.extractedInformation.length > 0 && (
                <DrawerSection label="Extracted vs. project profile">
                  <div className="space-y-3">
                    {selected.extractedInformation.map((info) => (
                      <div
                        key={info.label}
                        className="border border-border bg-surface-sunken px-3 py-2.5"
                      >
                        <div className="text-[12px] font-medium">
                          {info.label}
                        </div>
                        <div className="mt-1.5 grid grid-cols-2 gap-3">
                          <div>
                            <div className="label-meta">Project profile</div>
                            <div className="mt-0.5 text-[12.5px]">
                              {info.projectProfile}
                            </div>
                          </div>
                          <div>
                            <div className="label-meta">Uploaded document</div>
                            <div className="mt-0.5 text-[12.5px] text-destructive">
                              {info.uploadedDocument}
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </DrawerSection>
              )}

            {selected.issues && selected.issues.length > 0 && (
              <DrawerSection label="Issues">
                <ul className="space-y-1.5">
                  {selected.issues.map((issue) => (
                    <li
                      key={issue}
                      className="flex gap-2.5 text-[12.5px] leading-relaxed"
                    >
                      <StatusDot
                        status={docStatusMeta[selected.status].status}
                        className="mt-[6px]"
                      />
                      <span>{issue}</span>
                    </li>
                  ))}
                </ul>
              </DrawerSection>
            )}

            <DrawerSection label="Suggested action">
              <p className="text-[12.5px] leading-relaxed">
                {selected.status === "extracted"
                  ? "No action required. This document has been verified against the project profile."
                  : selected.status === "missing-info"
                    ? "Re-upload this document with the missing information included, or provide it directly in the requirement dossier."
                    : "Resolve the mismatch by correcting the project profile or re-uploading a corrected document, then request re-verification."}
              </p>
            </DrawerSection>

            <div className="px-5 py-4">
              <Tag>Prototype dataset</Tag>
            </div>
          </div>
        )}
      </Drawer>
    </PageShell>
  );
}
