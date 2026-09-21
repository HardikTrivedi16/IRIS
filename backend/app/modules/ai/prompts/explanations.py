"""Prompt definitions for IRIS AI Grounded Explanation Services (Phase 5).

Enforces the core IRIS architectural boundary:
AI UNDERSTANDS. RULES DECIDE. GRAPHS ORGANISE. ANALYTICS IDENTIFY. HUMANS DECIDE.

Universal Invariants:
- AUTHORITATIVE_INPUT has already been computed by another IRIS module.
- The AI explains the supplied input; it NEVER recalculates, overrides, or decides.
- Numbers, statuses, IDs, and lists must be preserved with strict fidelity.
- Never invent units when none are supplied.
- Never invent authorities or blame when none are supplied.
- Never strengthen advisory graph/scheme results into statutory conclusions or awards.
- Never alter official query text or invent unrequested document upload requests.
"""

import json
from typing import Any
from pydantic import BaseModel

from app.modules.ai.schemas import (
    ApplicationStatusInput,
    CriticalPathInput,
    DependencyInput,
    DocumentIssueInput,
    ImpactChangeInput,
    OfficialQueryInput,
    ParallelCandidateInput,
    RequirementTraceInput,
    RiskInput,
    SchemeMatchInput,
    SLAInput,
)

SHARED_EXPLANATION_SYSTEM_PROMPT = """You are the IRIS Grounded Explanation Assistant.

CORE ARCHITECTURAL PRINCIPLE:
AI UNDERSTANDS. RULES DECIDE. GRAPHS ORGANISE. ANALYTICS IDENTIFY. HUMANS DECIDE.

HARD BOUNDARIES & INVARIANTS:
1. AUTHORITATIVE_INPUT is already computed by another deterministic IRIS module.
2. You must EXPLAIN it in clear, concise plain language.
3. You must NOT recalculate it, alter it, or override it.
4. You must NOT infer missing business truth or extrapolate facts beyond what is provided.
5. Do NOT change numbers, ranges, dates, durations, or scores.
6. Do NOT change statuses or outcomes (e.g. CONDITIONAL must stay CONDITIONAL; POTENTIALLY_ELIGIBLE must stay POTENTIALLY_ELIGIBLE).
7. Do NOT invent units of measurement. If no unit is supplied, do NOT invent one.
8. Do NOT invent graph relationships, blocker nodes, or critical-path memberships.
9. Do NOT invent authorities, departments, or delay causes.
10. Do NOT approve or reject applications or make statutory determinations.
11. Do NOT strengthen advisory graph or scheme candidate classifications into statutory mandates or guaranteed outcomes.
12. If required information is absent or ambiguous, clearly state that the supplied data does not contain it and set insufficient_information = true.
"""


def _serialize(obj: Any) -> str:
    """Format input data as readable JSON string."""
    if isinstance(obj, BaseModel):
        return obj.model_dump_json(indent=2)
    if isinstance(obj, (dict, list)):
        try:
            return json.dumps(obj, indent=2, default=str)
        except Exception:
            return str(obj)
    return str(obj)


def build_requirement_trace_prompt(data: RequirementTraceInput | dict[str, Any]) -> str:
    """Prompt for explaining a Rule Engine evaluation trace."""
    serialized = _serialize(data)
    return f"""TASK: Explain Rule Engine Evaluation Trace

AUTHORITATIVE_INPUT:
{serialized}

INSTRUCTIONS:
- Explain why the requirement received the given outcome based strictly on the supplied facts and trace reason.
- If outcome is CONDITIONAL: explain that specific required information (missing_facts) is not yet provided, so the requirement cannot yet be conclusively evaluated. Do NOT state that the requirement applies or does not apply.
- If outcome is APPLICABLE or NOT_APPLICABLE: faithfully explain the trace reason without independently calculating applicability.
- Return structured output: explanation, action_guidance, insufficient_information, warnings, plus fidelity fields (requirement, outcome, missing_facts).
"""


def build_dependency_prompt(data: DependencyInput | dict[str, Any]) -> str:
    """Prompt for explaining NetworkX dependency/blocker status."""
    serialized = _serialize(data)
    return f"""TASK: Explain Requirement Dependency and Blocker Status

AUTHORITATIVE_INPUT:
{serialized}

INSTRUCTIONS:
- Explain the dependency status of the requirement and list every blocker in blocked_by.
- Preserve the dependency direction: the requirement is blocked BY the prerequisites, not vice versa.
- Explain the reason_code using the supplied data.
- If requirement_on_critical_path is true: note that this requirement is on the critical path, but do NOT assert that the blocker nodes individually belong to the critical path unless they are explicitly listed in critical_path_nodes.
- Do NOT claim statutory or legal prohibition merely because the graph status is BLOCKED. It is a workflow prerequisite.
- Return structured output: explanation, action_guidance, insufficient_information, warnings, plus fidelity fields (requirement, status, blocked_by, reason_code, requirement_on_critical_path, critical_path_nodes, parallel_candidates).
"""


def build_parallel_candidate_prompt(data: ParallelCandidateInput | dict[str, Any]) -> str:
    """Prompt for explaining parallel candidate requirements."""
    serialized = _serialize(data)
    return f"""TASK: Explain Parallel Candidate Requirements

AUTHORITATIVE_INPUT:
{serialized}

INSTRUCTIONS:
- Explain that IRIS identifies these requirements as potential parallel candidates because no configured prerequisite relationship exists between them.
- Preserve advisory meaning: do NOT claim government departments are legally required to process them simultaneously, and do NOT claim they will definitely be processed in parallel.
- Return structured output: explanation, action_guidance, insufficient_information, warnings, plus fidelity fields (requirements, classification, reason).
"""


def build_critical_path_prompt(data: CriticalPathInput | dict[str, Any]) -> str:
    """Prompt for explaining the critical path and estimated duration."""
    serialized = _serialize(data)
    return f"""TASK: Explain Computed Critical Path

AUTHORITATIVE_INPUT:
{serialized}

INSTRUCTIONS:
- Identify the sequence of requirements that form the computed critical path in their exact order.
- State the estimated total duration in days if supplied.
- Do NOT strengthen this into a claim that these statutory stages MUST legally occur in this exact order unless explicitly stated. It is the computed longest path based on estimated durations.
- Return structured output: explanation, action_guidance, insufficient_information, warnings, plus fidelity fields (critical_path, estimated_total_duration_days).
"""


def build_document_issue_prompt(data: DocumentIssueInput | dict[str, Any]) -> str:
    """Prompt for explaining document validation issues/inconsistencies."""
    serialized = _serialize(data)
    return f"""TASK: Explain Document Validation Issue

AUTHORITATIVE_INPUT:
{serialized}

INSTRUCTIONS:
- Explain the inconsistency or defect, stating the expected_value and actual_value faithfully.
- Maintain severity and issue_type exactly as supplied.
- Copy expected_value and actual_value directly as scalar values (number, string, or boolean) exactly as supplied in AUTHORITATIVE_INPUT (do NOT wrap them in nested objects).
- STRICT RULE ON UNITS: If unit is null or empty, DO NOT invent any unit (e.g. do not invent TPD, tonnes, units/day, etc.) in your explanation or structured fields. Preserve unit as null.
- Do NOT independently determine that a mismatch exists; explain the supplied finding.
- Return structured output: explanation, action_guidance, insufficient_information, warnings, plus fidelity fields (field_name, issue_type, severity, expected_value, actual_value, unit).
"""


def build_impact_change_prompt(data: ImpactChangeInput | dict[str, Any]) -> str:
    """Prompt for explaining regulatory impact recalculation diff."""
    serialized = _serialize(data)
    return f"""TASK: Explain Regulatory Impact Recalculation

AUTHORITATIVE_INPUT:
{serialized}

INSTRUCTIONS:
- Explain the change in the project fact from old_value to new_value.
- Explain which requirements became newly applicable or no longer applicable based strictly on the supplied diff.
- STRICT RULE ON THRESHOLDS: If condition_trace does not state an exact numeric threshold, do NOT invent or assume one (e.g. do not invent '>50').
- Return structured output: explanation, action_guidance, insufficient_information, warnings, plus fidelity fields (changed_fact, old_value, new_value, newly_applicable, no_longer_applicable, dependency_changes, critical_path_changed).
"""


def build_sla_prompt(data: SLAInput | dict[str, Any]) -> str:
    """Prompt for explaining SLA status and delay factors."""
    serialized = _serialize(data)
    return f"""TASK: Explain SLA Status and Timeline

AUTHORITATIVE_INPUT:
{serialized}

INSTRUCTIONS:
- Explain the current SLA status (ON_TRACK, APPROACHING, BREACHED) and duration figures (total_days, elapsed_days, remaining_days).
- Preserve all numbers faithfully; do NOT recalculate SLA numbers.
- STRICT RULE ON DELAY CAUSES & AUTHORITIES:
  * Only cite delay causes listed in delay_factors.
  * If delay_factors is empty and responsible_authority is null/absent: you MUST state that the supplied data does not identify a delay cause or responsible authority, and set insufficient_information = true if asked about delay causes or responsible parties.
  * NEVER invent or blame any authority, department, board, or officer (e.g. do NOT blame Pollution Control Board).
  * If responsible_authority is supplied, preserve it exactly; if null, keep responsible_authority as null.
- Return structured output: explanation, action_guidance, insufficient_information, warnings, plus fidelity fields (status, total_days, elapsed_days, remaining_days, paused, pause_reason, delay_factors, responsible_authority).
"""


def build_scheme_prompt(data: SchemeMatchInput | dict[str, Any]) -> str:
    """Prompt for explaining scheme matching results."""
    serialized = _serialize(data)
    return f"""TASK: Explain Scheme Matching Result

AUTHORITATIVE_INPUT:
{serialized}

INSTRUCTIONS:
- Explain the scheme match, citing the scheme_name and matched conditions.
- Preserve numeric ranges (e.g. between 5 and 20 crore INR) and required documents faithfully.
- STRICT RULE ON ELIGIBILITY:
  * Preserve POTENTIALLY_ELIGIBLE.
  * NEVER describe the applicant or project as ELIGIBLE, APPROVED, or AWARDED.
  * Explicitly include the disclaimer that final eligibility requires official verification.
- Return structured output: explanation, action_guidance, insufficient_information, warnings, plus fidelity fields (scheme_name, eligibility_outcome, matched_conditions, required_documents, disclaimer).
"""


def build_risk_prompt(data: RiskInput | dict[str, Any]) -> str:
    """Prompt for explaining risk score and factors."""
    serialized = _serialize(data)
    return f"""TASK: Explain Application Risk Indicators

AUTHORITATIVE_INPUT:
{serialized}

INSTRUCTIONS:
- Explain the computed risk score (e.g. 65) and each contributing risk factor faithfully.
- Do NOT recalculate the score or add unlisted factors.
- STRICT RULE ON ADJUDICATION:
  * The risk indicator is for review prioritisation and advisory screening only.
  * Do NOT infer or claim that the application is approved, rejected, or likely rejected.
  * Do NOT claim the risk score represents a statutory decision.
- Return structured output: explanation, action_guidance, insufficient_information, warnings, plus fidelity fields (risk_score, risk_level, factors, purpose).
"""


def build_official_query_prompt(data: OfficialQueryInput | dict[str, Any]) -> str:
    """Prompt for explaining an official government query."""
    serialized = _serialize(data)
    return f"""TASK: Explain Official Government Query

AUTHORITATIVE_INPUT:
{serialized}

INSTRUCTIONS:
- Provide a plain-language explanation of what the official query is asking.
- Identify the requested_action (e.g. clarification).
- STRICT RULE ON OFFICIAL TEXT & DOCUMENTS:
  * The official_text is immutable: copy official_text exactly into the output field official_text.
  * If the official query explicitly states 'No additional document is requested' or does not request documents: additional_document_requested MUST be false.
  * Do NOT instruct or advise the applicant to upload an unrequested document (e.g. do NOT advise uploading a revised project report if no document was requested).
  * Do NOT invent deadlines or authorities not present in the query.
  * Do NOT attempt to answer the query on behalf of the applicant.
- Preserve related_requirement and related_document exactly when supplied so the explanation can guide the applicant toward the relevant correction without inventing links.
- Return structured output: explanation, requested_action, additional_document_requested, insufficient_information, warnings, official_text, related_requirement, related_document.
"""


def build_application_status_prompt(data: ApplicationStatusInput | dict[str, Any]) -> str:
    """Prompt for explaining application workflow status."""
    serialized = _serialize(data)
    return f"""TASK: Explain Application Status

AUTHORITATIVE_INPUT:
{serialized}

INSTRUCTIONS:
- Explain the current application status and supplied reasons clearly.
- Do NOT transition application states or decide next statutory steps.
- Return structured output: explanation, action_guidance, insufficient_information, warnings, plus fidelity fields (status, reasons, pending_actions).
"""
