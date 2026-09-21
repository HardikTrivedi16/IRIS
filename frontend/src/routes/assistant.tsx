import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import {
  CornerDownLeft,
  MessagesSquare,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import { useProject } from "@/lib/iris/project-context";
import { suggestedQuestions } from "@/lib/iris/mock-data";
import {
  ApiError,
  BackendUnavailableError,
  irisApi,
  type AskIrisResponse,
} from "@/lib/iris/api-client";
import { deriveEngineProjectFacts, engineRequirementIdFor } from "@/lib/iris/engine-mapping";
import { PageHeader, PageShell } from "@/components/iris/page";
import { Tag } from "@/components/iris/status";
import type { ChatMessage } from "@/lib/iris/types";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/assistant")({
  head: () => ({
    meta: [
      { title: "Ask IRIS — IRIS" },
      {
        name: "description",
        content:
          "Ask IRIS about requirement applicability, blockers, missing documents and the effect of proposed project changes.",
      },
      { property: "og:title", content: "Ask IRIS — IRIS" },
      {
        property: "og:description",
        content:
          "A grounded assistant for questions about the active project's regulatory position.",
      },
    ],
  }),
  component: AssistantPage,
});

/**
 * Optional grounding hint: if a suggested question is clearly about one of
 * the four engine-backed requirements, pass its real requirement_id along
 * so the backend narrows/confirms context on it specifically. Freely-typed
 * questions send no hint — the backend then grounds on every requirement in
 * the dataset, which is exactly what "Which requirements apply?" needs.
 */
const requirementHintForQuestion: Record<string, string | undefined> = {
  "Why is the MPCB Consent to Establish (Water Act) applicable?":
    engineRequirementIdFor("mpcb-cte"),
  "What evidence supports the FSSAI Food Business Licence requirement?":
    engineRequirementIdFor("fssai-licence"),
};

function welcomeMessage(projectName: string): ChatMessage {
  return {
    id: "welcome",
    role: "assistant",
    content: `Ask me about requirement applicability, blockers, missing documents, or the effect of a proposed change for ${projectName}. Answers are grounded in this project's live Phase 9 evaluation, its NetworkX dependency status, and the regulatory dataset itself — with citations, and an honest "insufficient information" when the data doesn't support an answer.`,
    source: { name: "IRIS Assistant", type: "Grounded — Ask IRIS" },
  };
}

function errorMessage(error: unknown): ChatMessage {
  let content =
    "Ask IRIS could not answer that question. Please try again in a moment.";
  if (error instanceof BackendUnavailableError) {
    content =
      "The IRIS backend is unreachable right now. Check that the API server is running and try again.";
  } else if (error instanceof ApiError && error.status === 503) {
    content =
      "Ask IRIS's AI service (Ollama) is currently unreachable, so a grounded answer can't be generated right now. The regulatory engine and dependency graph themselves are unaffected — try again once the AI service is back up.";
  } else if (error instanceof ApiError && error.status === 422) {
    content = "That question couldn't be processed — try rephrasing it.";
  } else if (error instanceof ApiError && error.status === 404) {
    content = "This project could not be found or you don't have access to it.";
  }
  return {
    id: `err-${Date.now()}`,
    role: "assistant",
    content,
    isError: true,
    source: { name: "IRIS Assistant", type: "Unavailable" },
  };
}

function responseToMessage(id: string, question: string, res: AskIrisResponse): ChatMessage {
  return {
    id,
    role: "assistant",
    content: res.answer,
    insufficientInformation: res.insufficient_information,
    requiresHumanReview: res.requires_human_review,
    answerWithheld: res.engine_consistency?.answer_withheld ?? false,
    outOfScope: res.scope?.out_of_scope ?? false,
    warnings: res.warnings,
    citations: res.citations.map((c) => ({
      chunkId: c.chunk_id,
      sourceId: c.source_id,
      documentName: c.document_name ?? null,
      pageNumber: c.page_number ?? null,
      sectionReference: c.section_reference ?? null,
      sourceType: c.source_type,
      sourceLabel: c.source_label,
    })),
    // Ad-hoc facts used only for this answer — never this project's stored
    // Project Facts. Surfaced explicitly so a hypothetical value is never
    // mistaken for a saved one (see fact_context.note from the backend).
    ...(res.fact_context.uses_hypothetical_facts
      ? { hypotheticalFacts: res.fact_context.hypothetical_facts }
      : {}),
    source: { name: "IRIS Assistant", type: "Grounded — Ask IRIS" },
  };
}

function AssistantPage() {
  const { activeProject } = useProject();
  const [messages, setMessages] = useState<ChatMessage[]>([
    welcomeMessage(activeProject.name),
  ]);
  const [draft, setDraft] = useState("");

  const askMutation = useMutation({
    mutationFn: (question: string) => {
      const requirementId = requirementHintForQuestion[question];
      return irisApi.askIris(activeProject.id, {
        question,
        facts: deriveEngineProjectFacts(activeProject),
        ...(requirementId ? { requirementId } : {}),
      });
    },
  });

  function ask(question: string) {
    const userMessage: ChatMessage = {
      id: `u-${Date.now()}`,
      role: "user",
      content: question,
    };
    const pendingId = `a-${Date.now()}`;
    const pendingMessage: ChatMessage = {
      id: pendingId,
      role: "assistant",
      content: "Thinking through the current evaluation and dependency graph…",
      pending: true,
    };
    setMessages((prev) => [...prev, userMessage, pendingMessage]);
    setDraft("");

    askMutation.mutate(question, {
      onSuccess: (res) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === pendingId ? responseToMessage(pendingId, question, res) : m,
          ),
        );
      },
      onError: (error) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === pendingId ? { ...errorMessage(error), id: pendingId } : m,
          ),
        );
      },
    });
  }

  return (
    <PageShell wide className="pb-0">
      <PageHeader
        trail={[{ label: "Oversight" }, { label: "Ask IRIS" }]}
        title="Ask IRIS"
        description={`Grounded answers on ${activeProject.name}'s regulatory position`}
      />

      <div className="mt-6 grid gap-6 pb-10 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="flex min-h-[560px] flex-col border border-border bg-surface">
          <div className="flex-1 space-y-5 overflow-y-auto px-5 py-5">
            {messages.map((m) => (
              <div
                key={m.id}
                className={cn(
                  "flex",
                  m.role === "user" ? "justify-end" : "justify-start",
                )}
              >
                <div
                  className={cn(
                    "max-w-[min(560px,88%)] rounded-sm border px-4 py-3 text-[13px] leading-relaxed",
                    m.role === "user"
                      ? "border-primary bg-primary text-primary-foreground"
                      : m.isError
                        ? "border-destructive/30 bg-danger-surface"
                        : "border-border bg-surface-sunken",
                  )}
                >
                  {m.role === "assistant" && (
                    <div className="mb-1.5 flex items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-[0.06em] text-muted-foreground">
                      <Sparkles className="h-3 w-3" />
                      IRIS Assistant
                      {m.pending && (
                        <span className="normal-case tracking-normal text-muted-foreground/80">
                          · answering…
                        </span>
                      )}
                    </div>
                  )}
                  <p className={cn(m.pending && "animate-pulse")}>{m.content}</p>

                  {!m.pending &&
                    (m.insufficientInformation || m.requiresHumanReview || m.answerWithheld || m.outOfScope) && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {m.answerWithheld && (
                        <Tag tone="danger">
                          AI explanation withheld — contradicted the Rule Engine
                        </Tag>
                      )}
                      {m.outOfScope && (
                        <Tag tone="info">Outside this project's scope</Tag>
                      )}
                      {m.insufficientInformation && !m.outOfScope && (
                        <Tag tone="warning">Insufficient evidence in dataset</Tag>
                      )}
                      {m.requiresHumanReview && (
                        <Tag tone="danger">
                          <ShieldAlert className="h-3 w-3" />
                          Needs human review
                        </Tag>
                      )}
                    </div>
                  )}

                  {m.citations && m.citations.length > 0 && (
                    <div className="mt-2 space-y-1.5 border-t border-border/60 pt-2">
                      <p className="text-[10.5px] font-semibold uppercase tracking-[0.06em] text-muted-foreground">
                        Sources
                      </p>
                      <ul className="space-y-1.5 text-[11px] text-muted-foreground">
                        {m.citations.map((c) => (
                          <li key={c.chunkId}>
                            <div>
                              {c.documentName ?? c.sourceId}
                              {c.sectionReference ? ` · ${c.sectionReference}` : ""}
                              {c.pageNumber ? ` · p.${c.pageNumber}` : ""}
                            </div>
                            {/* Always shown: distinguishes IRIS's own dataset/live
                                grounding from an official government source. */}
                            <div className="italic text-muted-foreground/70">
                              {c.sourceLabel}
                            </div>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {m.hypotheticalFacts && Object.keys(m.hypotheticalFacts).length > 0 && (
                    <div className="mt-2 space-y-1 border-t border-border/60 pt-2">
                      <Tag tone="info">Hypothetical facts used — not saved</Tag>
                      <ul className="space-y-0.5 text-[11px] text-muted-foreground">
                        {Object.entries(m.hypotheticalFacts).map(([k, v]) => (
                          <li key={k}>
                            {k} = {JSON.stringify(v)}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {m.warnings && m.warnings.length > 0 && (
                    <ul className="mt-2 space-y-0.5 border-t border-border/60 pt-2 text-[11px] text-muted-foreground">
                      {m.warnings.map((w, i) => (
                        <li key={i}>⚠ {w}</li>
                      ))}
                    </ul>
                  )}

                  {m.source && !m.citations?.length && !m.warnings?.length && (
                    <p className="mt-2 border-t border-border/60 pt-2 text-[11px] text-muted-foreground">
                      Source: {m.source.name} · {m.source.type}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (draft.trim() && !askMutation.isPending) ask(draft.trim());
            }}
            className="flex items-center gap-2 border-t border-border px-4 py-3"
          >
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Ask about a requirement, blocker, document, or change…"
              className="focus-ring flex-1 rounded-sm border border-border bg-surface px-3 py-[8px] text-[13px]"
              disabled={askMutation.isPending}
            />
            <button
              type="submit"
              disabled={!draft.trim() || askMutation.isPending}
              className="focus-ring inline-flex items-center gap-1.5 rounded-sm bg-primary px-3 py-[8px] text-[12.5px] font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-40"
            >
              Ask
              <CornerDownLeft className="h-3.5 w-3.5" />
            </button>
          </form>
        </div>

        <aside className="space-y-6">
          <div className="border border-border bg-surface px-4 py-4">
            <div className="label-meta">Suggested questions</div>
            <ul className="mt-3 space-y-2">
              {suggestedQuestions.map((q) => (
                <li key={q}>
                  <button
                    type="button"
                    onClick={() => ask(q)}
                    disabled={askMutation.isPending}
                    className="row-hover flex w-full items-start gap-2 rounded-sm border border-border px-3 py-2.5 text-left text-[12.5px] leading-snug transition-colors hover:border-info hover:bg-info-surface disabled:opacity-40"
                  >
                    <MessagesSquare className="mt-[2px] h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                    {q}
                  </button>
                </li>
              ))}
            </ul>
          </div>

          <div className="border-t border-border pt-4">
            <Tag>Grounded assistant</Tag>
            <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
              Answers combine the live Phase 9 evaluation, the NetworkX
              dependency graph, and the regulatory dataset's own text — never
              an AI-invented regulatory decision. AI explanations are
              advisory; the applicability outcome always comes from the Rule
              Engine.
            </p>
          </div>
        </aside>
      </div>
    </PageShell>
  );
}
