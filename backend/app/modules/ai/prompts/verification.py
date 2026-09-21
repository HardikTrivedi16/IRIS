"""Verification prompts for IRIS AI fidelity checks.

The verifier checks whether LOCAL_OUTPUT faithfully represents AUTHORITATIVE_INPUT.
It evaluates fidelity only and must NEVER use general model knowledge to invent facts,
alter statutory boundaries, or act as an independent legal decision-maker.
"""

import json
from typing import Any
from pydantic import BaseModel

VERIFICATION_SYSTEM_PROMPT = """You are the IRIS AI Output Fidelity Verifier.

ROLE & BOUNDARY:
- Your sole job is to verify whether LOCAL_OUTPUT faithfully represents AUTHORITATIVE_INPUT.
- AUTHORITATIVE_INPUT is the single source of truth for this task.
- You must NOT independently solve the underlying regulatory, legal, or business problem.
- You must NOT use outside knowledge, general facts, or assumptions to introduce facts not present in AUTHORITATIVE_INPUT.
- Agreement or disagreement does not establish legal truth; only strict fidelity to AUTHORITATIVE_INPUT matters.

FIDELITY CHECKLIST:
Check LOCAL_OUTPUT for:
1. Unsupported claims or assumptions not grounded in AUTHORITATIVE_INPUT.
2. Omitted critical conditions, qualifications, or limitations.
3. Changed numbers, corrupted digits, formatting artifacts (e.g. '2:00' instead of '20').
4. Changed numerical ranges, thresholds, or comparative bounds (<, <=, >, >=).
5. Changed or misstated units (e.g. crore INR, TPD, acres).
6. Changed dates, deadlines, SLA durations, or validity periods.
7. Changed statuses (e.g. APPLICABLE vs CONDITIONAL, BLOCKED vs INDEPENDENT).
8. Changed or corrupted identifiers or codes.
9. Reversed or inverted dependency relationships.
10. Invented relationships, blockers, or critical-path memberships (e.g. assuming blocker nodes individually lie on critical path merely because a parent requirement is marked critical_path=true).
11. Strengthened legal meaning (e.g. turning an advisory guideline into a mandatory rule) or weakened legal meaning.
12. Hallucinated requirements, authorities, inspections, or forms.
13. Direct contradictions with AUTHORITATIVE_INPUT.
14. For task_type='regulatory_candidate_extraction', verify EACH structured condition field against the source: fact_text, comparison_text, value, lower_value, upper_value, unit, is_numeric, condition_logic, qualifiers, and timing_text.
15. For regulatory extraction, a number/operator/unit appearing only inside fact_text or raw_snippet is NOT sufficient. If the source says 'at least 20 workers', the structured output must preserve comparison_text='at least', value=20, unit='workers', is_numeric=true.
16. For regulatory extraction, preserve qualitative applicability predicates as conditions. Example: 'All agro-processing factories shall...' must preserve the 'agro-processing' factory-type predicate; do not replace it with the required action.

VERDICT RULES:
- PASS: LOCAL_OUTPUT faithfully, accurately, and completely reflects AUTHORITATIVE_INPUT without any unsupported claims, distortions, or fidelity errors.
- CORRECTED: LOCAL_OUTPUT contained minor, clear defects (e.g. an obvious typo or corrupted number directly fixable from AUTHORITATIVE_INPUT), and you can provide a complete corrected output supported DIRECTLY by AUTHORITATIVE_INPUT.
  * You may return CORRECTED ONLY if the correction is 100% grounded in AUTHORITATIVE_INPUT.
  * Never invent or extrapolate facts to create a correction.
  * For regulatory_candidate_extraction, CORRECTED is allowed ONLY when the corrected output completely restores every explicit applicability threshold, range bound, comparison operator, unit, qualitative predicate, condition logic, qualifier, and timing phrase from AUTHORITATIVE_INPUT into the proper structured fields.
  * If you detect a regulatory fidelity defect but cannot provide a COMPLETE schema-valid correction, return REJECT rather than a partial CORRECTED output.
- REJECT: LOCAL_OUTPUT contains hallucinations, unsupported claims, inverted logic, critical contradictions, or errors that cannot be safely corrected using AUTHORITATIVE_INPUT alone.

OUTPUT FORMAT:
You MUST respond with a JSON object strictly adhering to this structure:
{
  "verdict": "PASS" | "CORRECTED" | "REJECT",
  "issues": [
    {
      "code": "MACHINE_READABLE_CODE",
      "field": "affected_field_or_null",
      "message": "Detailed description of the fidelity issue."
    }
  ],
  "corrected_output": null | <corrected_data_matching_original_structure>
}
"""


def _serialize_payload(obj: Any) -> str:
    """Serialize input/output payload to readable JSON or string representation."""
    if isinstance(obj, BaseModel):
        return obj.model_dump_json(indent=2)
    if isinstance(obj, (dict, list)):
        try:
            return json.dumps(obj, indent=2, default=str)
        except Exception:
            return str(obj)
    return str(obj)


def build_verification_prompt(
    task_type: str,
    authoritative_input: Any,
    local_output: Any,
    output_schema: type[BaseModel] | None = None,
) -> str:
    """Build a task-aware verification prompt.

    The verifier must judge factual/structured fidelity, not literal JSON equality.
    AUTHORITATIVE_INPUT and LOCAL_OUTPUT intentionally have different schemas for
    explanation, RAG, document-extraction, and regulatory-extraction tasks.
    """
    auth_str = _serialize_payload(authoritative_input)
    local_str = _serialize_payload(local_output)
    schema_str = (
        json.dumps(output_schema.model_json_schema(), indent=2, default=str)
        if output_schema is not None else "No correction schema supplied."
    )

    task_rules = ""
    if task_type.startswith("explanation_"):
        task_rules = """
TASK-SPECIFIC RULES — EXPLANATION:
- AUTHORITATIVE_INPUT is deterministic business/graph/rule-engine data; LOCAL_OUTPUT is an explanation schema, so their JSON shapes are intentionally different.
- Do NOT reject merely because LOCAL_OUTPUT contains explanation, action_guidance, warnings, or other presentation fields absent from AUTHORITATIVE_INPUT.
- PASS when every structured fidelity field copied from AUTHORITATIVE_INPUT is preserved and the prose is a faithful paraphrase with no new factual/legal claim.
- A concise paraphrase is not an unsupported claim merely because its wording does not literally occur in AUTHORITATIVE_INPUT.
- REJECT/CORRECT only factual mutations, omissions of authoritative structured facts, invented facts, changed statuses/numbers/relationships, or strengthened/weakened meaning.
"""
    elif task_type == "grounded_rag_answer":
        task_rules = """
TASK-SPECIFIC RULES — GROUNDED RAG:
- AUTHORITATIVE_INPUT contains a question plus supplied source chunks; LOCAL_OUTPUT is an answer schema, so literal object equality is NOT expected.
- Verify every factual claim in answer against supplied_sources only.
- Citation identifiers/metadata must refer only to supplied sources.
- If sources are insufficient, insufficient_information must be true and no unsupported answer may be invented.
"""
    elif task_type == "applicant_document_extraction":
        task_rules = """
TASK-SPECIFIC RULES — DOCUMENT EXTRACTION:
- AUTHORITATIVE_INPUT is raw document text and LOCAL_OUTPUT is structured extraction; literal JSON equality is NOT expected.
- Every populated fact, identifier, number, date, unit, evidence snippet, and provenance claim must be supported by the supplied text.
- Null/absent fields are correct when the source does not state the value.
- Confidence is reviewer-attention metadata; do not invent source facts to make the extraction more complete.
"""
    elif task_type == "regulatory_candidate_extraction":
        task_rules = """
TASK-SPECIFIC RULES — REGULATORY EXTRACTION:
- AUTHORITATIVE_INPUT is source text and LOCAL_OUTPUT is a structured candidate; literal JSON equality is NOT expected.
- Verify complete preservation of requirement/action, applicability predicates, thresholds, operators, ranges, units, logic, timing, qualifiers, required documents, issuing authority, and source provenance when explicitly present.
- Do not require fields that are not stated by the source.
"""

    return f"""TASK TYPE: {task_type}
{task_rules}
=== AUTHORITATIVE_INPUT (SOURCE OF TRUTH) ===
{auth_str}

=== LOCAL_OUTPUT (BEING CHECKED) ===
{local_str}

=== CORRECTED_OUTPUT JSON SCHEMA ===
{schema_str}

Verify semantic and structured fidelity according to the system and task-specific rules.
If verdict is CORRECTED, corrected_output MUST validate against CORRECTED_OUTPUT JSON SCHEMA.
Return only the required verification JSON object.
"""
