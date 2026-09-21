import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import {
  ApiError,
  BackendUnavailableError,
  irisApi,
  type NewProjectPayload,
} from "@/lib/iris/api-client";

// Closed option lists mirror what the existing display layer already
// understands (lib/iris/types.ts Industry / ProjectStage / ProjectScale), so a
// new project renders correctly everywhere. They are profile labels, not
// regulatory classifications.
const INDUSTRIES = [
  { value: "food", label: "Food processing" },
  { value: "pharmaceutical", label: "Pharmaceutical" },
];
const STAGES = [
  { value: "pre-establishment", label: "Pre-establishment" },
  { value: "construction", label: "Construction" },
  { value: "commissioning", label: "Commissioning" },
  { value: "operations", label: "Operations" },
];
const SCALES = [
  { value: "small", label: "Small" },
  { value: "medium", label: "Medium" },
  { value: "large", label: "Large" },
];
// The six existing public.projects.characteristics flags.
const CHARACTERISTICS: { key: string; label: string }[] = [
  { key: "wastewater", label: "Generates wastewater / effluent" },
  { key: "airEmissions", label: "Has air emissions" },
  { key: "waterUse", label: "Uses water in process" },
  { key: "hazardousChemicals", label: "Handles hazardous chemicals" },
  { key: "hazardousWaste", label: "Generates hazardous waste" },
  { key: "chemicalStorage", label: "Stores chemicals on site" },
];

const inputClass =
  "focus-ring w-full rounded-sm border border-border bg-surface px-2.5 py-[7px] text-[13px]";

function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string;
  hint?: string;
  error?: string | undefined;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="text-[12px] font-medium">{label}</span>
      {hint && <span className="ml-1.5 text-[11px] text-muted-foreground">{hint}</span>}
      <div className="mt-1">{children}</div>
      {error && <span className="mt-1 block text-[11.5px] text-destructive">{error}</span>}
    </label>
  );
}

export type CreatedProject = { id: string } & Record<string, unknown>;

/**
 * Step 1 of project intake: the existing public.projects columns only. The
 * backend generates the id, stamps owner_id from the session and refuses to
 * overwrite an existing project.
 */
export function NewProjectForm({
  onCreated,
  onCancel,
}: {
  onCreated: (project: CreatedProject) => void;
  onCancel?: () => void;
}) {
  const [name, setName] = useState("");
  const [industry, setIndustry] = useState(INDUSTRIES[0]!.value);
  const [activity, setActivity] = useState("");
  const [location, setLocation] = useState("");
  const [stage, setStage] = useState(STAGES[0]!.value);
  const [scale, setScale] = useState(SCALES[0]!.value);
  const [workers, setWorkers] = useState("");
  const [characteristics, setCharacteristics] = useState<Record<string, boolean>>(
    Object.fromEntries(CHARACTERISTICS.map((c) => [c.key, false])),
  );
  const [errors, setErrors] = useState<Record<string, string>>({});

  const create = useMutation({
    mutationFn: (payload: NewProjectPayload) => irisApi.createProject(payload),
    onSuccess: (project) => onCreated(project as unknown as CreatedProject),
  });

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const errs: Record<string, string> = {};
    const trimmedName = name.trim();
    if (!trimmedName) errs["name"] = "Enter a project or company name.";
    else if (trimmedName.length > 200) errs["name"] = "Keep the name under 200 characters.";
    let workerCount: number | undefined;
    if (workers.trim() !== "") {
      const n = Number(workers);
      if (!Number.isInteger(n) || n < 0) errs["workers"] = "Enter a whole number, 0 or more.";
      else workerCount = n;
    }
    setErrors(errs);
    if (Object.keys(errs).length) return;

    const payload: NewProjectPayload = {
      name: trimmedName,
      industry,
      stage,
      scale,
      characteristics,
    };
    if (activity.trim()) payload.activity = activity.trim();
    if (location.trim()) payload.location = location.trim();
    if (workerCount !== undefined) payload.workers = workerCount;
    create.mutate(payload);
  }

  const serverError = create.error;
  let serverMessage: string | null = null;
  if (serverError instanceof BackendUnavailableError) {
    serverMessage = "The IRIS backend isn't reachable. Nothing was created.";
  } else if (serverError instanceof ApiError) {
    serverMessage =
      serverError.status === 401
        ? "Your session has expired. Sign in again to create a project."
        : serverError.status === 409
          ? "A project with this identifier already exists."
          : serverError.status === 422
            ? "Some details were rejected by the server. Check the fields and try again."
            : "The project could not be created.";
  } else if (serverError) {
    serverMessage = "The project could not be created.";
  }

  return (
    <form onSubmit={submit} noValidate>
      <div className="grid gap-4 px-5 py-5 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <Field label="Project / company name" error={errors["name"]}>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className={inputClass}
              placeholder="e.g. Company name — plant name"
              autoFocus
            />
          </Field>
        </div>
        <Field label="Industry">
          <select value={industry} onChange={(e) => setIndustry(e.target.value)} className={inputClass}>
            {INDUSTRIES.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </Field>
        <Field label="Activity" hint="optional">
          <input value={activity} onChange={(e) => setActivity(e.target.value)} className={inputClass}
            placeholder="What the plant does" />
        </Field>
        <Field label="Location" hint="optional — district, state">
          <input value={location} onChange={(e) => setLocation(e.target.value)} className={inputClass} />
        </Field>
        <Field label="Workers" hint="optional" error={errors["workers"]}>
          <input value={workers} onChange={(e) => setWorkers(e.target.value)} className={`${inputClass} tabular`}
            inputMode="numeric" />
        </Field>
        <Field label="Project stage">
          <select value={stage} onChange={(e) => setStage(e.target.value)} className={inputClass}>
            {STAGES.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </Field>
        <Field label="Scale">
          <select value={scale} onChange={(e) => setScale(e.target.value)} className={inputClass}>
            {SCALES.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </Field>
        <fieldset className="sm:col-span-2">
          <legend className="text-[12px] font-medium">Operational profile</legend>
          <p className="text-[11px] text-muted-foreground">
            Descriptive only. These are not regulatory facts and do not decide
            applicability — the next step asks the rules' own questions.
          </p>
          <div className="mt-2 grid gap-x-6 gap-y-1.5 sm:grid-cols-2">
            {CHARACTERISTICS.map((c) => (
              <label key={c.key} className="flex items-center gap-2 text-[12.5px]">
                <input
                  type="checkbox"
                  checked={!!characteristics[c.key]}
                  onChange={(e) =>
                    setCharacteristics((prev) => ({ ...prev, [c.key]: e.target.checked }))
                  }
                  className="accent-[var(--info)]"
                />
                {c.label}
              </label>
            ))}
          </div>
        </fieldset>
      </div>
      <div className="flex flex-wrap items-center gap-3 border-t border-border px-5 py-3">
        <button
          type="submit"
          disabled={create.isPending}
          className="focus-ring rounded-sm bg-primary px-3 py-[7px] text-[12.5px] font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-40"
        >
          {create.isPending ? "Creating…" : "Create project"}
        </button>
        {onCancel && (
          <button type="button" onClick={onCancel}
            className="focus-ring rounded-sm border border-border px-3 py-[7px] text-[12.5px] font-medium hover:bg-secondary">
            Cancel
          </button>
        )}
        {serverMessage && <span className="text-[11.5px] text-destructive">{serverMessage}</span>}
      </div>
    </form>
  );
}
