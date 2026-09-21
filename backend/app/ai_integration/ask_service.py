"""
Ask IRIS — grounded, read-only regulatory Q&A (backend wiring only).

This module contains no AI logic of its own. It wires together three
things that already exist and are individually frozen/authoritative:

    1. The Phase 9 Rule Engine (``app.engine_service``) — the ONLY source of
       applicability decisions (APPLICABLE / CONDITIONAL / NOT_APPLICABLE /
       BLOCKED_*).
    2. The NetworkX dependency graph (``app.graph.service``) — the ONLY
       source of blocker/critical-path status.
    3. The IRIS AI module's Phase 4 ``RetrievalService`` (already-built RAG
       pipeline with citation validation) — used to turn (1) + (2) + the
       regulatory dataset's own text into a grounded, cited, plain-language
       answer.

Nothing here lets the LLM invent an applicability decision: the engine and
graph calls happen independently of, and BEFORE, the LLM call, and the raw
results are always returned alongside the AI answer as
``authoritative_context`` so a caller never has to trust the prose alone.

The regulatory corpus indexed into the retrieval index is built exclusively
from the frozen Phase 9 dataset's own authored text (requirement titles/
notes, rule descriptions, rule-version true/false/unknown outcome text) —
never invented, never NetworkX demo/mock data.
"""
from __future__ import annotations

import logging
import threading
from typing import Any

from app.modules.ai.exceptions import AIError, AIInvalidOutputError, AIUnavailableError
from app.modules.ai.facade import get_ai
from app.modules.ai.schemas import RegulatorySourceChunk, RetrievalResult

from .. import engine_service
from ..graph.service import get_project_dependency_graph
from .engine_guard import (
    engine_result_answer,
    find_engine_contradictions,
    question_targets_other_facility,
    scope_answer,
)

logger = logging.getLogger("iris.ai_integration.ask")


# ---------------------------------------------------------------------------
# Citation provenance labeling
#
# Every citation currently resolves to one of three internal chunk kinds
# (frozen dataset text, a live engine decision, or a live dependency-graph
# status) — never an official government document. This mapping exists so
# the API/frontend can say so explicitly instead of letting a plausible
# document_name (e.g. a requirement's title) read as if it were an official
# publication. It labels the CATEGORY of an existing chunk_id (a structural
# fact already known from how the chunk was built) — it never invents a
# URL, order number, page number, authority, or publication date.
# ---------------------------------------------------------------------------

_CITATION_PROVENANCE: dict[str, tuple[str, str]] = {
    "requirement": (
        "iris_regulatory_dataset",
        "IRIS Regulatory Dataset — internal Phase 9 requirement record (not an official government publication)",
    ),
    "rule-version": (
        "iris_regulatory_dataset",
        "IRIS Regulatory Dataset — internal Phase 9 rule-version record (not an official government publication)",
    ),
    "engine-decision": (
        "iris_live_evaluation",
        "Live IRIS Rule Engine decision, computed for this project (not an official document)",
    ),
    "dependency-status": (
        "iris_live_evaluation",
        "Live IRIS NetworkX dependency status, computed for this project (not an official document)",
    ),
}

_DEFAULT_CITATION_PROVENANCE = (
    "iris_internal",
    "IRIS internal grounding — not verified as an official government document",
)


def _citation_provenance(chunk_id: str) -> tuple[str, str]:
    """Return (source_type, source_label) for a citation's chunk_id.

    Never returns anything implying an official/government source — the
    only kinds of chunk currently produced are internal dataset text or
    live computed results, and the fallback for anything unrecognized is
    explicitly labeled unverified rather than assumed official.
    """
    prefix = chunk_id.split(":", 1)[0]
    return _CITATION_PROVENANCE.get(prefix, _DEFAULT_CITATION_PROVENANCE)


def _hypothetical_facts_note(hypothetical_facts: dict[str, Any]) -> str:
    """A grounding-text note (fed to the LLM alongside live decisions/
    dependency status) making explicit that certain fact values were
    supplied only for this question and are not persisted Project Facts.

    Returns "" when no hypothetical facts were supplied, so existing
    grounding text is byte-for-byte unchanged for the common case.
    """
    if not hypothetical_facts:
        return ""
    pairs = ", ".join(f"{k}={v!r}" for k, v in sorted(hypothetical_facts.items()))
    return (
        "NOTE: this result was computed using the following hypothetical fact "
        f"override(s) supplied only for this question — they are NOT stored/"
        f"persisted Project Facts: {pairs}."
    )


class AIUnavailable(Exception):
    """Raised (and only raised) when Ask IRIS cannot run because the AI
    module itself reports it can't run right now — disabled via config, or
    the Ollama daemon is unreachable. Mirrors the same contract as
    ``ai_integration.service.AIUnavailable`` so routers can map it to a
    clean 503 instead of a 500."""


# ---------------------------------------------------------------------------
# Regulatory corpus indexing (Phase 9 dataset text -> RAG index)
# ---------------------------------------------------------------------------

_corpus_lock = threading.Lock()


def _build_regulatory_corpus_chunks() -> list[RegulatorySourceChunk]:
    """Build retrievable chunks strictly from the frozen Phase 9 dataset's
    own authored text. No text is invented, summarized, or paraphrased here
    — it is copied verbatim from the dataset records the Rule Engine itself
    uses to decide."""
    ds = engine_service.get_dataset()
    chunks: list[RegulatorySourceChunk] = []

    for req_id, req in sorted(ds.requirements.items()):
        title = req.get("title") or req_id
        notes = (req.get("requirement_notes") or "").strip()
        text = f"{title} (code: {req.get('code', '')}, category: {req.get('category', '')})."
        if notes:
            text += f"\n{notes}"
        chunks.append(
            RegulatorySourceChunk(
                chunk_id=f"requirement:{req_id}",
                source_id=req_id,
                text=text,
                document_name=title,
                section_reference=req.get("code"),
            )
        )

    for rv_id, rv in sorted(ds.rule_versions.items()):
        rule = ds.rules.get(rv.get("rule_id"), {}) or {}
        title = rule.get("title") or rv.get("rule_id") or rv_id
        parts = [title]
        if rule.get("description"):
            parts.append(rule["description"].strip())
        if rv.get("true_outcome"):
            parts.append(f"If TRUE: {rv['true_outcome'].strip()}")
        if rv.get("false_outcome"):
            parts.append(f"If FALSE: {rv['false_outcome'].strip()}")
        if rv.get("unknown_outcome"):
            parts.append(f"If UNKNOWN: {rv['unknown_outcome'].strip()}")
        parts.append(f"(Rule Version status: {rv.get('status')})")
        chunks.append(
            RegulatorySourceChunk(
                chunk_id=f"rule-version:{rv_id}",
                source_id=rv.get("rule_id") or rv_id,
                text="\n".join(parts),
                document_name=title,
                section_reference=rv_id,
            )
        )

    return chunks


def _ensure_regulatory_corpus_indexed(ai) -> None:
    """Index the regulatory corpus into the retrieval index if it is empty.

    Checking ``count() > 0`` (rather than a module-level "already did this"
    flag) makes this correct regardless of whether ``ai`` is the shared
    default facade or a freshly constructed one (e.g. in tests that reset
    the facade) — an empty index always gets (re)populated.
    """
    if ai.retrieval.count() > 0:
        return
    with _corpus_lock:
        if ai.retrieval.count() > 0:
            return
        chunks = _build_regulatory_corpus_chunks()
        if chunks:
            ai.retrieval.index_chunks(chunks)


# ---------------------------------------------------------------------------
# Ephemeral live-context chunks (Phase 9 decisions / NetworkX status)
# ---------------------------------------------------------------------------

def _requirement_title(ds, requirement_id: str) -> str:
    req = ds.requirements.get(requirement_id) or {}
    return req.get("title") or requirement_id


def _decision_chunk(
    decision: dict, requirement_title: str, hypothetical_note: str = ""
) -> RegulatorySourceChunk:
    req_id = decision["requirement_id"]
    lines = [
        f"Live Phase 9 Rule Engine decision for {req_id} ({requirement_title}).",
        f"Evaluation mode: {decision.get('evaluation_mode')}",
        f"Result: {decision.get('final_state')}",
        f"Reason: {decision.get('reason_text')}",
    ]
    missing = decision.get("missing_project_fact_keys") or []
    if missing:
        lines.append(f"Missing project facts: {', '.join(missing)}")
    narrative = ((decision.get("explanation") or {}).get("narrative") or "").strip()
    if narrative and narrative != decision.get("reason_text"):
        lines.append(f"Explanation: {narrative}")
    if hypothetical_note:
        lines.append(hypothetical_note)
    return RegulatorySourceChunk(
        chunk_id=f"engine-decision:{req_id}",
        source_id="phase9-rule-engine",
        text="\n".join(lines),
        document_name=f"Live evaluation — {requirement_title}",
        section_reference=req_id,
    )


def _dependency_chunk(node: dict, hypothetical_note: str = "") -> RegulatorySourceChunk:
    req_id = node["requirement_id"]
    lines = [
        f"Live NetworkX dependency status for {req_id} ({node.get('name')}).",
        f"Status: {node.get('status')}",
        f"Parallel classification: {node.get('parallel_classification')}",
    ]
    unmet = node.get("unmet_prerequisite_ids") or []
    if unmet:
        lines.append(f"Blocked by unmet prerequisites: {', '.join(unmet)}")
    prereq = node.get("direct_prerequisite_ids") or []
    if prereq:
        lines.append(f"Direct prerequisites: {', '.join(prereq)}")
    if hypothetical_note:
        lines.append(hypothetical_note)
    return RegulatorySourceChunk(
        chunk_id=f"dependency-status:{req_id}",
        source_id="networkx-dependency-graph",
        text="\n".join(lines),
        document_name=f"Live dependency graph — {node.get('name')}",
        section_reference=req_id,
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def ask_iris(
    project_id: str,
    question: str,
    facts: dict[str, Any],
    requirement_id: str | None = None,
    evaluation_mode: str = "PRODUCTION",
    top_k: int = 5,
    hypothetical_facts: dict[str, Any] | None = None,
    project_name: str | None = None,
) -> dict:
    """Answer a read-only regulatory question about ``project_id``.

    Pipeline (see module docstring): Phase 9 decisions + NetworkX status
    (computed independently, never by the LLM) + indexed regulatory-dataset
    text -> RetrievalService.answer() (grounded generation + mandatory
    citation validation) -> structured result. Never mutates Project Facts
    or any Decision.

    ``facts`` is the evaluation input exactly as before (stored Project
    Facts merged with any ad-hoc request-body facts, body wins) — engine/
    graph behavior is unchanged. ``hypothetical_facts`` is the ad-hoc
    subset of that (i.e. the caller's request-body facts, echoed by the
    router), used ONLY to (a) label the response so hypothetical values
    are never presented as persisted Project Facts, and (b) note their use
    in the live-context grounding text so the AI's own wording doesn't
    imply they are stored either. It is never written to any store.
    """
    if not question or not question.strip():
        raise AIInvalidOutputError("question must not be empty or whitespace-only.")

    hypothetical_facts = hypothetical_facts or {}
    hypothetical_note = _hypothetical_facts_note(hypothetical_facts)

    ai = get_ai()
    ds = engine_service.get_dataset()

    warnings: list[str] = []

    if requirement_id and requirement_id in ds.requirements:
        target_requirement_ids = [requirement_id]
    else:
        if requirement_id:
            warnings.append(
                f"Requirement '{requirement_id}' was not found in the regulatory dataset; "
                "grounding this answer on every known requirement instead."
            )
        target_requirement_ids = sorted(ds.requirements.keys())

    try:
        _ensure_regulatory_corpus_indexed(ai)
    except AIUnavailableError as exc:
        raise AIUnavailable(str(exc)) from exc

    # --- Authoritative context: computed independently of the LLM ---------
    decisions: list[dict] = []
    for req_id in target_requirement_ids:
        try:
            decision = engine_service.evaluate_requirement(
                project_id=project_id,
                requirement_id=req_id,
                project_facts=facts,
                evaluation_mode=evaluation_mode,
            )
            decisions.append(decision)
        except Exception:
            logger.exception("Ask IRIS: engine evaluation failed for %s/%s", project_id, req_id)
            warnings.append(f"Could not evaluate {req_id} for this project; it is excluded from grounding.")

    dependency_nodes: list[dict] = []
    try:
        graph = get_project_dependency_graph(
            project_id=project_id, facts=facts, evaluation_mode=evaluation_mode
        )
        dependency_nodes = [
            n for n in graph.get("nodes", []) if n.get("requirement_id") in target_requirement_ids
        ]
    except Exception:
        logger.exception("Ask IRIS: dependency graph build failed for %s", project_id)
        warnings.append("Dependency graph information could not be computed for this request.")

    titles = {rid: _requirement_title(ds, rid) for rid in ds.requirements}
    authoritative_context = {
        "evaluation_mode": evaluation_mode,
        "decisions": [
            {
                "requirement_id": d.get("requirement_id"),
                "final_state": d.get("final_state"),
                "reason_text": d.get("reason_text"),
            }
            for d in decisions
        ],
        "dependency_status": [
            {
                "requirement_id": n.get("requirement_id"),
                "status": n.get("status"),
                "unmet_prerequisite_ids": n.get("unmet_prerequisite_ids", []),
            }
            for n in dependency_nodes
        ],
    }
    fact_context = {
        "uses_hypothetical_facts": bool(hypothetical_facts),
        "hypothetical_fact_keys": sorted(hypothetical_facts.keys()),
        "hypothetical_facts": hypothetical_facts,
        "note": (
            "hypothetical_facts were supplied for this question only and were "
            "NOT written to this project's stored Project Facts."
            if hypothetical_facts
            else "This answer used only this project's stored Project Facts — no "
            "hypothetical overrides were supplied."
        ),
    }

    # --- Scope guard (deterministic, before any LLM call) ------------------
    # The engine results above describe THIS project only. A question about a
    # different or generic facility must not be answered by transferring them.
    if question_targets_other_facility(question):
        return {
            "question": question,
            "answer": scope_answer(project_name or f"project {project_id}"),
            "insufficient_information": True,
            "requires_human_review": False,
            "citations_valid": True,
            "citations": [],
            "warnings": [
                *warnings,
                "Question appears to concern a facility other than the active "
                "project; no AI answer was generated.",
            ],
            "fact_context": fact_context,
            "authoritative_context": authoritative_context,
            "engine_consistency": {"checked": False, "contradictions": [], "answer_withheld": False},
            "scope": {"out_of_scope": True, "reason": "OTHER_FACILITY"},
            "ai_enabled": ai.config.ai_enabled,
        }

    engine_sources = [
        RetrievalResult(
            chunk=_decision_chunk(
                d, _requirement_title(ds, d["requirement_id"]), hypothetical_note
            ),
            similarity_score=1.0,
            rank=i + 1,
        )
        for i, d in enumerate(decisions)
    ]
    dependency_sources = [
        RetrievalResult(
            chunk=_dependency_chunk(n, hypothetical_note), similarity_score=1.0, rank=i + 1
        )
        for i, n in enumerate(dependency_nodes)
    ]

    try:
        semantic_sources = ai.retrieval.search(question, top_k=top_k)
    except AIUnavailableError as exc:
        raise AIUnavailable(str(exc)) from exc

    seen_ids: set[str] = set()
    combined_sources: list[RetrievalResult] = []
    for r in [*engine_sources, *dependency_sources, *semantic_sources]:
        if r.chunk.chunk_id in seen_ids:
            continue
        seen_ids.add(r.chunk.chunk_id)
        combined_sources.append(r)

    # --- Grounded, cited generation (existing Phase 4 RAG pipeline) -------
    try:
        result = ai.retrieval.answer(question, sources=combined_sources)
    except AIUnavailableError as exc:
        raise AIUnavailable(str(exc)) from exc

    all_warnings = [*warnings, *result.warnings]

    labeled_citations: list[dict] = []
    for c in result.answer.citations:
        d = c.model_dump()
        source_type, source_label = _citation_provenance(c.chunk_id)
        d["source_type"] = source_type
        d["source_label"] = source_label
        labeled_citations.append(d)

    # --- Engine-consistency guard (deterministic, after generation) --------
    # Citation validation proves the answer cites real sources, not that it
    # agrees with them. Any applicability claim that contradicts the engine's
    # own result withholds the prose; the engine's result is returned instead.
    answer_text = result.answer.answer
    requires_review = result.requires_human_review
    contradictions = find_engine_contradictions(answer_text, decisions, titles)
    withheld = bool(contradictions)
    if withheld:
        answer_text = engine_result_answer(
            decisions, titles, only={c["requirement_id"] for c in contradictions}
        )
        requires_review = True
        # The model's own warning text is LLM prose too and can restate the
        # withheld claim; keep only system-generated warnings (engine/graph,
        # citation and verification issues).
        model_warnings = set(result.answer.warnings or [])
        all_warnings = [*warnings, *(w for w in result.warnings if w not in model_warnings)]
        labeled_citations = [
            c for c in labeled_citations if c["chunk_id"].startswith("engine-decision:")
        ]
        all_warnings.append(
            "The AI explanation contradicted the Rule Engine ("
            + "; ".join(
                f"{c['requirement_id']}: claimed {c['claimed']}, engine {c['engine_state']}"
                for c in contradictions
            )
            + ") and was withheld."
        )

    return {
        "question": question,
        "answer": answer_text,
        "insufficient_information": result.answer.insufficient_information,
        "requires_human_review": requires_review,
        "citations_valid": result.citations_valid,
        "citations": labeled_citations,
        "warnings": all_warnings,
        "fact_context": fact_context,
        "authoritative_context": authoritative_context,
        "engine_consistency": {
            "checked": True,
            "contradictions": contradictions,
            "answer_withheld": withheld,
            # Kept for audit only; never shown as the answer.
            "withheld_answer": result.answer.answer if withheld else None,
        },
        "scope": {"out_of_scope": False, "reason": None},
        "ai_enabled": ai.config.ai_enabled,
    }
