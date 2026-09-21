"""
Bottleneck explanation (P1-J).

Re-presents the EXISTING deterministic bottleneck report (department store)
component by component — duration, backlog, SLA breach — and lists the
applications currently sitting in each stage. It adds no new metric.

The composite ``bottleneck_score`` is kept (existing API/tests rely on its
ranking) but is labelled for what it is: a PROTOTYPE OPERATIONAL HEURISTIC.
Its weights (0.40 / 0.35 / 0.25) are prototype choices, not calibrated, and it
adds quantities in different units (hours, a count, a percentage). The raw
components are the primary evidence.

Nothing here predicts, mines processes, or claims causation: a stage with a
long average duration is where time is being spent, not proof of why.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from .store.department_store import (
    _BOTTLENECK_W_BACKLOG,
    _BOTTLENECK_W_BREACH,
    _BOTTLENECK_W_DURATION,
    _parse_dt,
)

SCORE_CLASSIFICATION = "PROTOTYPE_OPERATIONAL_HEURISTIC"

_ACTIVE_EXCLUDED = {"APPROVED", "REJECTED"}


def _state(v) -> Optional[str]:
    return v.value if hasattr(v, "value") else v


def explain_bottlenecks(report: dict, applications: list[dict], now: Optional[datetime] = None) -> dict:
    now = now or datetime.now(timezone.utc)

    by_stage: dict[str, list[dict]] = {}
    synthetic = unclassified = 0
    for a in applications:
        cls = a.get("data_classification")
        if cls == "SYNTHETIC_DEMO":
            synthetic += 1
        elif cls is None:
            unclassified += 1
        stage = a.get("current_stage")
        if stage in _ACTIVE_EXCLUDED or a.get("completed_at"):
            continue
        created = _parse_dt(a.get("created_at"))
        by_stage.setdefault(stage, []).append({
            "id": a.get("id"),
            "application_id": a.get("application_id"),
            "title": a.get("title"),
            "sla_state": _state((a.get("sla") or {}).get("state")),
            "age_hours": round((now - created).total_seconds() / 3600.0, 1) if created else None,
            "data_classification": cls,
        })

    stages = []
    for s in report.get("stages") or []:
        avg = s.get("avg_duration_hours")
        backlog = s.get("backlog") or 0
        pct = s.get("sla_breach_pct") or 0.0
        contributions = {
            "duration": round((avg or 0.0) * _BOTTLENECK_W_DURATION, 4),
            "backlog": round(backlog * _BOTTLENECK_W_BACKLOG, 4),
            "breach": round(pct * 100.0 * _BOTTLENECK_W_BREACH, 4),
        }
        affected = sorted(by_stage.get(s.get("stage"), []), key=lambda x: -(x["age_hours"] or 0))
        stages.append({
            "stage": s.get("stage"),
            "rank_by_heuristic": s.get("rank"),
            "components": {
                "avg_duration_hours": avg,
                "median_duration_hours": s.get("median_duration_hours"),
                "completed_passages": s.get("completed_count"),
                "backlog": backlog,
                "sla_breach_pct": pct,
                "breached_count": s.get("breached_count"),
                "at_risk_count": s.get("at_risk_count"),
            },
            "heuristic_score": s.get("bottleneck_score"),
            "heuristic_contributions": contributions,
            "affected_applications": affected,
        })

    notes = [
        "The composite score is a PROTOTYPE OPERATIONAL HEURISTIC: its weights are "
        "prototype choices, not calibrated, and it adds hours, a count and a percentage. "
        "Read the components, not the score.",
        "These figures describe where time and backlog currently sit. They do not "
        "establish why — correlation is not cause. No prediction or process mining is used.",
        "Durations come only from recorded stage transitions; a stage with no completed "
        "passages has no average.",
    ]
    if synthetic:
        notes.insert(0, f"SYNTHETIC DEMO DATA: {synthetic} of {len(applications)} applications "
                        "in scope come from a synthetic seed.")
    if unclassified:
        notes.append(f"{unclassified} application(s) have no recorded data provenance "
                     "(Supabase records are classified once migration 0007 is applied).")

    return {
        "generated_at": now.isoformat(),
        "score_classification": SCORE_CLASSIFICATION,
        "weights": {
            "duration_per_hour": _BOTTLENECK_W_DURATION,
            "backlog_per_application": _BOTTLENECK_W_BACKLOG,
            "breach_per_percent": _BOTTLENECK_W_BREACH,
        },
        "data": {
            "applications_in_scope": len(applications),
            "synthetic_demo": synthetic,
            "unclassified": unclassified,
        },
        "stages": stages,
        "notes": notes,
    }
