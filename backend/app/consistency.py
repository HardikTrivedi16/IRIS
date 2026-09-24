"""
Deterministic Consistency Engine (P0-D) — "What does not match before I file?"

This checks OBJECTIVE DATA CONSISTENCY between values that appear in a
project's confirmed record and in submitted documents: the same entity name,
the same premises address, the same batch number, the same pack size, a
document that has passed its stated expiry date.

It is deliberately NOT a regulatory applicability or compliance decision:

* It never says a project is compliant or non-compliant, and never uses any
  dataset's ``expected_result`` label as an answer.
* No LLM is involved at any step. Values may have been *extracted* by the
  local model upstream, but whether two normalised values match is decided
  here, in plain code, with the rule for every field published in
  ``FIELD_REGISTRY``.
* Nothing is written. Project Facts are never updated from a check; every
  non-CONSISTENT result requires a human to review the evidence.

Result statuses
---------------
CONSISTENT      values match under the field's published normalisation
CONFLICT        values differ after normalisation
REVIEW_REQUIRED values are close but not provably the same (e.g. differ only
                in word spacing, or one address is a less specific form of
                the other) — a human must decide; IRIS will not
EXPIRED         a document's stated validity end date is before the as-of date
MISSING         a field the caller required has no usable observation
NOT_COMPARABLE  values cannot be compared safely (unknown/incompatible
                units, unrecognised date format)
LOW_CONFIDENCE  an extracted value is below the review confidence threshold
                and was excluded from comparison

The low-confidence threshold is a PROTOTYPE REVIEW POLICY, not a statutory
or regulatory value.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------

#: Extracted values with a confidence below this are excluded from
#: comparison and flagged LOW_CONFIDENCE. Prototype review policy only.
LOW_CONFIDENCE_THRESHOLD = 0.6

CONSISTENT = "CONSISTENT"
CONFLICT = "CONFLICT"
REVIEW_REQUIRED = "REVIEW_REQUIRED"
EXPIRED = "EXPIRED"
MISSING = "MISSING"
NOT_COMPARABLE = "NOT_COMPARABLE"
LOW_CONFIDENCE = "LOW_CONFIDENCE"

SOURCE_PROJECT_RECORD = "PROJECT_RECORD"
SOURCE_DOCUMENT = "DOCUMENT"
SOURCE_MANUAL = "MANUAL"


class ConsistencyInputError(Exception):
    def __init__(self, errors: list[dict]) -> None:
        super().__init__("; ".join(e["message"] for e in errors))
        self.errors = errors


# ---------------------------------------------------------------------------
# Units — DEFINITIONAL conversions only (1 kg = 1000 g, 1 KLD = 1000 L/day).
# No density, no product-specific or assumed conversions: comparing a mass to
# a volume is NOT_COMPARABLE, never guessed.
# ---------------------------------------------------------------------------

_UNITS: dict[str, tuple[str, float]] = {
    # mass (base: g)
    "mg": ("mass", 0.001), "g": ("mass", 1.0), "gm": ("mass", 1.0), "gram": ("mass", 1.0),
    "grams": ("mass", 1.0), "kg": ("mass", 1000.0), "kgs": ("mass", 1000.0),
    # volume (base: mL)
    "ml": ("volume", 1.0), "l": ("volume", 1000.0), "ltr": ("volume", 1000.0),
    "litre": ("volume", 1000.0), "liter": ("volume", 1000.0), "litres": ("volume", 1000.0),
    "kl": ("volume", 1_000_000.0),
    # volume per day (base: L/day)
    "l/day": ("volume_per_day", 1.0), "lpd": ("volume_per_day", 1.0),
    "kld": ("volume_per_day", 1000.0), "kl/day": ("volume_per_day", 1000.0),
    "m3/day": ("volume_per_day", 1000.0),
    # mass per day (base: tonne/day)
    "tpd": ("mass_per_day", 1.0), "mt/day": ("mass_per_day", 1.0),
    "tonnes/day": ("mass_per_day", 1.0), "kg/day": ("mass_per_day", 0.001),
    # mass per year (base: tonne/year)
    "mt/annum": ("mass_per_year", 1.0), "mt/year": ("mass_per_year", 1.0),
    "tpa": ("mass_per_year", 1.0), "tonnes/year": ("mass_per_year", 1.0),
    "mtpa": ("mass_per_year", 1.0), "kg/year": ("mass_per_year", 0.001),
}


def _unit_key(unit: str) -> str:
    u = unit.strip().lower().replace(" ", "")
    u = u.replace("per", "/").replace("//", "/")
    u = u.replace("litres", "l").replace("liters", "l").replace("litre", "l").replace("liter", "l")
    return u


def _lookup_unit(unit: str) -> Optional[tuple[str, float]]:
    raw = unit.strip().lower()
    return _UNITS.get(raw) or _UNITS.get(_unit_key(unit))


# "," is only ever a digit-group separator here (Indian "1,00,000" or
# "50,000"); "." is the decimal point. A comma is never read as a decimal.
_QTY_RE = re.compile(r"^\s*([-+]?\d[\d,]*(?:\.\d+)?)\s*([a-zA-Z/0-9 .]*?)\s*$")


# ---------------------------------------------------------------------------
# Field registry — small and reliable on purpose
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FieldSpec:
    field: str
    label: str
    kind: str  # name | address | identifier | quantity | expiry_date
    value_type: str
    normalization: str
    comparison: str
    dimensions: tuple[str, ...] = ()


_REVIEW_NOTE = (
    "Any result other than CONSISTENT requires human review. IRIS never "
    "updates Project Facts from a consistency check."
)

FIELD_REGISTRY: dict[str, FieldSpec] = {
    "entity_name": FieldSpec(
        "entity_name", "Entity / business name", "name", "text",
        "Case-folded; punctuation removed; whitespace collapsed; leading 'M/s' "
        "dropped; legal-form abbreviations expanded (Pvt→Private, Ltd→Limited, "
        "Co→Company, Corp→Corporation, Inc→Incorporated); '&'→'and'.",
        "Equal after normalisation → CONSISTENT. Equal only when all spaces "
        "are also ignored → REVIEW_REQUIRED. Otherwise → CONFLICT.",
    ),
    "address": FieldSpec(
        "address", "Premises address", "address", "text",
        "Case-folded; punctuation replaced by spaces; whitespace collapsed; "
        "filler words 'no'/'number' dropped; 'rd'→'road', 'opp'→'opposite', "
        "'nr'→'near', 'dist'→'district'.",
        "Same token sequence → CONSISTENT. Same tokens in a different order, "
        "or one address a strict subset of the other (less specific) → "
        "REVIEW_REQUIRED. Otherwise → CONFLICT.",
    ),
    "registration_number": FieldSpec(
        "registration_number", "Registration / licence number", "identifier", "text",
        "Upper-cased; whitespace removed.",
        "Equal → CONSISTENT. Equal only when '-' and '/' are also ignored → "
        "REVIEW_REQUIRED. Otherwise → CONFLICT.",
    ),
    "batch_number": FieldSpec(
        "batch_number", "Batch number", "identifier", "text",
        "Upper-cased; whitespace removed.",
        "Equal → CONSISTENT. Equal only when '-' and '/' are also ignored → "
        "REVIEW_REQUIRED. Otherwise → CONFLICT.",
    ),
    "net_quantity": FieldSpec(
        "net_quantity", "Net quantity / pack size", "quantity", "quantity",
        "Parsed as number + unit; converted with definitional factors only "
        "(mg/g/kg, mL/L/kL).",
        "Same dimension and equal after conversion → CONSISTENT; different "
        "value → CONFLICT; mass vs volume or unknown unit → NOT_COMPARABLE.",
        ("mass", "volume"),
    ),
    "production_capacity": FieldSpec(
        "production_capacity", "Production capacity", "quantity", "quantity",
        "Parsed as number + unit; converted with definitional factors only "
        "(L/day↔KLD, kg/day↔TPD, kg/year↔MT/annum).",
        "Same dimension and equal after conversion → CONSISTENT; different "
        "value → CONFLICT; incompatible dimensions or unknown unit → "
        "NOT_COMPARABLE.",
        ("volume_per_day", "mass_per_day", "mass_per_year"),
    ),
    "valid_until": FieldSpec(
        "valid_until", "Validity end date", "expiry_date", "date",
        "ISO date YYYY-MM-DD only (other formats are ambiguous between "
        "DD/MM and MM/DD and are not guessed).",
        "Checked per document against the as-of date: before it → EXPIRED, "
        "on or after → CONSISTENT (with days remaining). Not compared across "
        "documents — each document has its own validity.",
    ),
}


def field_registry() -> list[dict]:
    return [
        {
            "field": s.field,
            "label": s.label,
            "value_type": s.value_type,
            "normalization": s.normalization,
            "comparison": s.comparison,
            "units": sorted(u for u, (dim, _) in _UNITS.items() if dim in s.dimensions)
            if s.dimensions else [],
            "human_review": _REVIEW_NOTE,
        }
        for s in FIELD_REGISTRY.values()
    ]


# ---------------------------------------------------------------------------
# Normalisers (pure)
# ---------------------------------------------------------------------------

_NAME_TOKENS = {
    "pvt": "private", "ltd": "limited", "co": "company", "corp": "corporation",
    "corpn": "corporation", "inc": "incorporated",
}
_ADDRESS_TOKENS = {"rd": "road", "opp": "opposite", "nr": "near", "dist": "district"}
_ADDRESS_FILLER = {"no", "number"}


def _normalize_name(value: str) -> str:
    v = value.strip().lower()
    v = re.sub(r"^m\s*/\s*s\.?\s+", "", v)
    v = v.replace("&", " and ")
    v = re.sub(r"[^\w\s]", " ", v)
    tokens = [_NAME_TOKENS.get(t, t) for t in v.split()]
    return " ".join(tokens)


def _address_tokens(value: str) -> list[str]:
    v = re.sub(r"[^\w\s]", " ", value.strip().lower())
    return [
        _ADDRESS_TOKENS.get(t, t) for t in v.split() if t not in _ADDRESS_FILLER
    ]


def _normalize_identifier(value: str) -> str:
    return re.sub(r"\s+", "", value).upper()


def _parse_quantity(value: Any, unit: Optional[str]) -> tuple[Optional[float], Optional[str], Optional[str]]:
    """Returns (number, unit, error)."""
    if isinstance(value, bool):
        return None, None, "a boolean is not a quantity"
    if isinstance(value, (int, float)):
        return float(value), (unit or "").strip() or None, None
    if isinstance(value, str):
        m = _QTY_RE.match(value)
        if not m:
            return None, None, f"could not read a number and unit from {value!r}"
        number = float(m.group(1).replace(",", ""))
        parsed_unit = m.group(2).strip() or None
        return number, (unit or parsed_unit), None
    return None, None, f"unsupported value type {type(value).__name__}"


# ---------------------------------------------------------------------------
# Observations
# ---------------------------------------------------------------------------

def _obs_view(obs: dict, normalized: Any) -> dict:
    return {
        "observation_id": obs["observation_id"],
        "raw_value": obs.get("value"),
        "unit": obs.get("unit"),
        "normalized_value": normalized,
        "confidence": obs.get("confidence"),
        "source": dict(obs.get("source") or {}),
    }


def _check_id(*parts: Any) -> str:
    blob = json.dumps(parts, sort_keys=True, default=str).encode("utf-8")
    return "CHK-" + hashlib.sha256(blob).hexdigest()[:16]


def _normalized(spec: FieldSpec, obs: dict) -> tuple[Any, Optional[str]]:
    """(normalized_value, error). Error means NOT_COMPARABLE."""
    value = obs.get("value")
    if spec.kind in ("name", "address", "identifier"):
        if not isinstance(value, str) or not value.strip():
            return None, "expected a non-empty text value"
        if spec.kind == "name":
            return _normalize_name(value), None
        if spec.kind == "address":
            return " ".join(_address_tokens(value)), None
        return _normalize_identifier(value), None
    if spec.kind == "quantity":
        number, unit, err = _parse_quantity(value, obs.get("unit"))
        if err:
            return None, err
        if not unit:
            return None, "no unit given, so the value cannot be compared safely"
        found = _lookup_unit(unit)
        if found is None:
            return None, f"unit {unit!r} is not in the definitional conversion table"
        dim, factor = found
        if dim not in spec.dimensions:
            return None, f"unit {unit!r} ({dim}) is not valid for {spec.label.lower()}"
        return {"dimension": dim, "base_value": number * factor}, None
    if spec.kind == "expiry_date":
        if not isinstance(value, str):
            return None, "expected an ISO date string (YYYY-MM-DD)"
        try:
            return _dt.date.fromisoformat(value.strip()).isoformat(), None
        except ValueError:
            return None, f"{value!r} is not an ISO date (YYYY-MM-DD); other formats are not guessed"
    return None, f"unsupported field kind {spec.kind}"


def _compare(spec: FieldSpec, ref: dict, cand: dict, ref_n: Any, cand_n: Any) -> tuple[str, str]:
    if spec.kind == "name":
        if ref_n == cand_n:
            return CONSISTENT, "Names match after normalisation."
        if ref_n.replace(" ", "") == cand_n.replace(" ", ""):
            return REVIEW_REQUIRED, (
                "Names differ only in word spacing. They may denote the same "
                "entity, but IRIS cannot confirm that — a human must decide."
            )
        return CONFLICT, "Names differ after normalisation."
    if spec.kind == "address":
        r, c = ref_n.split(), cand_n.split()
        if r == c:
            return CONSISTENT, "Addresses match after normalisation."
        if sorted(r) == sorted(c):
            return REVIEW_REQUIRED, (
                "Same address components in a different order — numbers may "
                "attach to different parts (e.g. plot vs sector). Confirm manually."
            )
        rs, cs = set(r), set(c)
        if rs < cs or cs < rs:
            return REVIEW_REQUIRED, (
                "One address is a less specific form of the other. They do not "
                "contradict, but IRIS cannot confirm they are the same premises."
            )
        return CONFLICT, "Addresses differ after normalisation."
    if spec.kind == "identifier":
        if ref_n == cand_n:
            return CONSISTENT, "Identifiers match."
        strip = lambda s: re.sub(r"[-/]", "", s)  # noqa: E731
        if strip(ref_n) == strip(cand_n):
            return REVIEW_REQUIRED, "Identifiers differ only in '-' or '/' separators."
        return CONFLICT, "Identifiers differ."
    if spec.kind == "quantity":
        if ref_n["dimension"] != cand_n["dimension"]:
            return NOT_COMPARABLE, (
                f"{ref_n['dimension']} cannot be compared with {cand_n['dimension']} "
                "without an assumption IRIS will not make."
            )
        a, b = ref_n["base_value"], cand_n["base_value"]
        if abs(a - b) <= 1e-9 * max(abs(a), abs(b), 1.0):
            return CONSISTENT, "Quantities are equal after unit conversion."
        return CONFLICT, "Quantities differ after unit conversion."
    return NOT_COMPARABLE, "No comparison rule for this field."


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

MAX_OBSERVATIONS = 200


def _validate(observations: list[dict], required_fields: list[str]) -> None:
    errors: list[dict] = []
    if len(observations) > MAX_OBSERVATIONS:
        errors.append({"index": None, "code": "TOO_MANY_OBSERVATIONS",
                       "message": f"At most {MAX_OBSERVATIONS} observations per check."})
    for i, obs in enumerate(observations):
        if obs.get("field") not in FIELD_REGISTRY:
            errors.append({"index": i, "code": "UNKNOWN_FIELD",
                           "message": f"Observation {i}: unsupported field {obs.get('field')!r}."})
        conf = obs.get("confidence")
        if conf is not None and (isinstance(conf, bool) or not isinstance(conf, (int, float))
                                 or not 0.0 <= float(conf) <= 1.0):
            errors.append({"index": i, "code": "INVALID_CONFIDENCE",
                           "message": f"Observation {i}: confidence must be between 0 and 1."})
    for f in required_fields:
        if f not in FIELD_REGISTRY:
            errors.append({"index": None, "code": "UNKNOWN_FIELD",
                           "message": f"Required field {f!r} is not supported."})
    if errors:
        raise ConsistencyInputError(errors)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

def run_consistency_check(
    observations: list[dict],
    *,
    as_of: _dt.date,
    required_fields: list[str] | None = None,
) -> dict:
    """Run every applicable check over ``observations``. Pure function of its
    inputs: same observations + same as-of date → same result, same check ids.

    Each observation: ``{field, value, unit?, confidence?, is_reference?,
    source: {kind, document_id?, document_name?, page?, evidence_text?}}``.
    """
    required_fields = list(required_fields or [])
    _validate(observations, required_fields)

    obs_list = []
    for i, o in enumerate(observations):
        o = dict(o)
        o["observation_id"] = o.get("observation_id") or f"OBS-{i + 1}"
        o["source"] = dict(o.get("source") or {"kind": SOURCE_MANUAL})
        obs_list.append(o)

    checks: list[dict] = []
    uncompared: list[dict] = []

    def add(field: str, status: str, message: str, *, reference=None, candidate=None,
            basis=None, extra=None) -> None:
        spec = FIELD_REGISTRY[field]
        record = {
            "field": field,
            "field_label": spec.label,
            "status": status,
            "message": message,
            "human_review_required": status != CONSISTENT,
            "reference": reference,
            "candidate": candidate,
            "reference_basis": basis,
            "comparison_rule": spec.comparison,
            **(extra or {}),
        }
        record["check_id"] = _check_id(
            field, status,
            (reference or {}).get("observation_id"), (reference or {}).get("raw_value"),
            (candidate or {}).get("observation_id"), (candidate or {}).get("raw_value"),
            as_of.isoformat(),
        )
        checks.append(record)

    by_field: dict[str, list[dict]] = {}
    for o in obs_list:
        if o.get("value") is None or (isinstance(o.get("value"), str) and not o["value"].strip()):
            continue  # the document does not state this field — not an observation
        by_field.setdefault(o["field"], []).append(o)

    for field in FIELD_REGISTRY:
        spec = FIELD_REGISTRY[field]
        group = by_field.get(field, [])

        usable: list[tuple[dict, Any]] = []
        for o in group:
            conf = o.get("confidence")
            if conf is not None and float(conf) < LOW_CONFIDENCE_THRESHOLD:
                add(field, LOW_CONFIDENCE,
                    f"Extraction confidence {float(conf):.2f} is below the review "
                    f"threshold {LOW_CONFIDENCE_THRESHOLD:.2f} (prototype policy); "
                    "excluded from comparison.",
                    candidate=_obs_view(o, None))
                continue
            normalized, err = _normalized(spec, o)
            if err:
                add(field, NOT_COMPARABLE, err, candidate=_obs_view(o, None))
                continue
            usable.append((o, normalized))

        if field in required_fields and not usable:
            add(field, MISSING,
                "No usable value was found for this required field in the "
                "project record or the submitted documents.")

        if spec.kind == "expiry_date":
            for o, iso in usable:
                days = (_dt.date.fromisoformat(iso) - as_of).days
                if days < 0:
                    add(field, EXPIRED,
                        f"Stated validity ended {iso}, {-days} day(s) before {as_of.isoformat()}.",
                        candidate=_obs_view(o, iso), extra={"days_remaining": days})
                else:
                    add(field, CONSISTENT,
                        f"Valid on {as_of.isoformat()}; {days} day(s) remaining.",
                        candidate=_obs_view(o, iso), extra={"days_remaining": days})
            continue

        if len(usable) < 2:
            if usable:
                uncompared.append({
                    "field": field, "field_label": spec.label,
                    "reason": "Only one source states this value, so there is nothing to compare it with.",
                })
            continue

        explicit = [u for u in usable if u[0].get("is_reference")]
        record = [u for u in usable if u[0]["source"].get("kind") == SOURCE_PROJECT_RECORD]
        if explicit:
            ref, basis = explicit[0], "EXPLICIT_REFERENCE"
        elif record:
            ref, basis = record[0], "PROJECT_RECORD"
        else:
            ref, basis = usable[0], "FIRST_SUBMITTED"

        ref_view = _obs_view(ref[0], ref[1])
        for cand in usable:
            if cand is ref:
                continue
            status, message = _compare(spec, ref[0], cand[0], ref[1], cand[1])
            add(field, status, message, reference=ref_view,
                candidate=_obs_view(cand[0], cand[1]), basis=basis)

    order = {CONFLICT: 0, EXPIRED: 1, MISSING: 2, REVIEW_REQUIRED: 3,
             LOW_CONFIDENCE: 4, NOT_COMPARABLE: 5, CONSISTENT: 6}
    checks.sort(key=lambda c: (order[c["status"]], c["field"], c["check_id"]))

    summary = {s: 0 for s in order}
    for c in checks:
        summary[c["status"]] += 1
    issues = sum(n for s, n in summary.items() if s != CONSISTENT)

    return {
        "as_of_date": as_of.isoformat(),
        "checks_performed": len(checks),
        "issues_found": issues,
        "human_review_required": issues > 0,
        "summary": summary,
        "checks": checks,
        "uncompared_fields": uncompared,
        "project_facts_modified": False,
        "policy": {
            "low_confidence_threshold": LOW_CONFIDENCE_THRESHOLD,
            "note": (
                "Objective data-consistency check only — not a regulatory "
                "applicability or compliance determination. The low-confidence "
                "threshold is a prototype review policy, not a statutory value. "
                "No value was written to Project Facts."
            ),
        },
    }


# Confirmed Project Facts (written by the Documents page after human review,
# under `document.<field>`) that can stand in as the project's own record.
_PROJECT_RECORD_FACTS: dict[str, str] = {
    "document.business_name": "entity_name",
    "document.registration_number": "registration_number",
    "document.location": "address",
}


def project_record_observations(stored_facts: dict[str, Any], project_id: str | None = None) -> list[dict]:
    """Human-confirmed values already in the project's record, as reference
    observations. Only exact, same-meaning mappings — nothing inferred.

    When the project is EXPLICITLY declared (legacy_evidence.json) to hold document.* facts describing a
    prior facility, each automatic observation is labelled as a legacy document record. The values, the
    comparison and the resulting statuses are untouched."""
    from .legacy_evidence import legacy_document_facts_info

    legacy = legacy_document_facts_info(project_id)
    name = legacy["label"] if legacy else "Confirmed project record"
    out: list[dict] = []
    for fact_key, field in _PROJECT_RECORD_FACTS.items():
        value = stored_facts.get(fact_key)
        if isinstance(value, str) and value.strip():
            out.append({
                "field": field, "value": value, "observation_id": f"REC-{field}",
                "source": {"kind": SOURCE_PROJECT_RECORD, "fact_key": fact_key,
                           "document_name": name, **({"legacy_evidence": legacy} if legacy else {})},
            })
    cap_v = stored_facts.get("document.capacity_value")
    cap_u = stored_facts.get("document.capacity_unit")
    if isinstance(cap_v, (int, float)) and not isinstance(cap_v, bool) and isinstance(cap_u, str) and cap_u.strip():
        out.append({
            "field": "production_capacity", "value": cap_v, "unit": cap_u,
            "observation_id": "REC-production_capacity",
            "source": {"kind": SOURCE_PROJECT_RECORD,
                       "fact_key": "document.capacity_value",
                       "document_name": name, **({"legacy_evidence": legacy} if legacy else {})},
        })
    return out
