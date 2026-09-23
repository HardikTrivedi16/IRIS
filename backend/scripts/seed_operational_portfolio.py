"""
Idempotent real-Supabase seed — IRIS multi-sector OPERATIONAL demo workload.

Adds a small number of SYNTHETIC_DEMO applications (with their stage history, SLA instance, assignment
history, operational_events and project activity_events) so the Industry and Government portals show the
same persisted rows across the five-sector portfolio.

DEFAULT IS A DRY RUN. Nothing is written unless --apply is passed.

    .venv/Scripts/python.exe scripts/seed_operational_portfolio.py                      # dry run
    .venv/Scripts/python.exe scripts/seed_operational_portfolio.py --apply              # write

Design rules:
  * Uses ONLY existing tables/columns/stages (applications, application_stage_history, assignment_history,
    sla_instances, operational_events, activity_events). No migration, no new stage, no new department.
  * SLA state is NOT written. It is derived by the existing _compute_sla_state() from
    applications.created_at + the linked sla_policies row, so only created_at / sla_policy_id are seeded.
  * No terminal stage (APPROVED / REJECTED): the demo never fabricates a government decision.
  * Every stage path follows ALLOWED_TRANSITIONS (asserted at start-up).
  * Never deletes rows. The ONLY update to an existing row is APP-00003.sla_policy_id (NULL -> the policy its own
    sla_instances row already references). Existing applications (Aarav x2, SwaadHarvest APP-00003),
    grievances, documents and project facts are untouched. Creates no auth users.
  * Idempotent: an application is identified by its unique application_id ("APP-DEMO-..."). If the row
    exists it is never modified; only MISSING append-only children are topped up (keyed as noted below).
  * Timestamps are anchored to run time (now - N days). SLA states are therefore "as of seeding" and
    drift forward with real time, exactly as they would for real applications.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

INDUSTRY_EMAIL = "industry@gmail.com"
OFFICER_EMAIL = "department@gmail.com"      # existing synthetic MPCB officer (no auth user is created)
POLICY_ID = "a1000000-0000-0000-0000-000000000001"   # Standard Review (30 days, warning 75%)
SUBMITTER = INDUSTRY_EMAIL

# steps: (days_before_anchor, new_stage, actor, reason)  — first step is the submission (previous_stage NULL)
# officer: True -> assigned right after the first step following SUBMITTED (the UNDER_REVIEW transition)
APPS = [
    {
        "application_id": "APP-DEMO-VOLTEDGE-REQ-0002",
        "project_id": "voltedge-mobility",
        "requirement_id": "REQ-0002",
        "title": "MPCB Consent to Establish/Operate — Air Act (Chakan plant)",
        "assign": True,
        "steps": [
            (24, "SUBMITTED", SUBMITTER, "Application submitted"),
            (22, "UNDER_REVIEW", "OFFICER", "Departmental review started"),
        ],
    },
    {
        "application_id": "APP-DEMO-DECCAN-REQ-0001",
        "project_id": "deccan-microelectronics",
        "requirement_id": "REQ-0001",
        "title": "MPCB Consent to Establish — Water Act (Ranjangaon plant)",
        "assign": True,
        "steps": [
            (12, "SUBMITTED", SUBMITTER, "Application submitted"),
            (10, "UNDER_REVIEW", "OFFICER", "Departmental review started"),
            (5, "INFORMATION_REQUESTED", "OFFICER", "Additional supporting information requested from applicant (synthetic demo)"),
        ],
    },
    {
        "application_id": "APP-DEMO-KONKAN-REQ-0010",
        "project_id": "konkan-specialty-chemicals",
        "requirement_id": "REQ-0010",
        "title": "MPCB Hazardous waste authorisation — HOWM Rules (Mahad plant)",
        "assign": False,
        "steps": [
            (2, "SUBMITTED", SUBMITTER, "Application submitted"),
        ],
    },
    {   # Gives the Government portal a BREACHED / inspection example (approved).
        "application_id": "APP-DEMO-SWAADHARVEST-REQ-0002",
        "project_id": "92ebc91d-e3e6-46ac-a5ce-46ef5ae240d4",
        "requirement_id": "REQ-0002",
        "title": "MPCB Consent to Establish/Operate — Air Act (Supa plant)",
        "assign": True,
        "steps": [
            (38, "SUBMITTED", SUBMITTER, "Application submitted"),
            (36, "UNDER_REVIEW", "OFFICER", "Departmental review started"),
            (4, "INSPECTION_SCHEDULED", "OFFICER", "Site inspection scheduled"),
        ],
    },
]


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def main() -> None:
    apply = "--apply" in sys.argv

    from app.config import get_settings
    from app.store import get_store
    from app.department_schemas import ALLOWED_TRANSITIONS, ApplicationStage
    from app.store.department_store import _compute_sla_state

    settings = get_settings()
    if settings.iris_demo_mode or not settings.supabase_configured:
        print("REFUSING TO RUN: real Supabase must be configured and IRIS_DEMO_MODE must be off.", file=sys.stderr)
        raise SystemExit(1)
    store = get_store()
    if type(store).__name__ != "SupabaseStore":
        print(f"REFUSING TO RUN: store is {type(store).__name__}, not SupabaseStore.", file=sys.stderr)
        raise SystemExit(1)
    get = store._get

    # Every seeded path must be a legal workflow path.
    for spec in APPS:
        stages = [ApplicationStage(s[1]) for s in spec["steps"]]
        for a, b in zip(stages, stages[1:]):
            assert b in ALLOWED_TRANSITIONS.get(a, set()), f"{spec['application_id']}: illegal {a.value}->{b.value}"
        assert stages[0] == ApplicationStage.SUBMITTED
        assert stages[-1] not in (ApplicationStage.APPROVED, ApplicationStage.REJECTED)

    owners = get("/user_profiles", {"select": "supabase_auth_uid", "email": f"eq.{INDUSTRY_EMAIL}"})
    if not owners:
        print(f"REFUSING TO RUN: no user_profiles row for {INDUSTRY_EMAIL}.", file=sys.stderr)
        raise SystemExit(1)
    owner_id = owners[0]["supabase_auth_uid"]

    officer_rows = get("/department_users", {"select": "*", "email": f"eq.{OFFICER_EMAIL}", "is_active": "eq.true"})
    if not officer_rows or officer_rows[0]["department_id"] != "dept-mpcb":
        print(f"REFUSING TO RUN: active dept-mpcb officer {OFFICER_EMAIL} not found.", file=sys.stderr)
        raise SystemExit(1)
    officer = officer_rows[0]

    if not get("/departments", {"select": "id", "id": "eq.dept-mpcb"}):
        print("REFUSING TO RUN: dept-mpcb missing.", file=sys.stderr)
        raise SystemExit(1)
    policies = get("/sla_policies", {"select": "*", "id": f"eq.{POLICY_ID}"})
    if not policies:
        print("REFUSING TO RUN: SLA policy missing.", file=sys.stderr)
        raise SystemExit(1)
    policy = policies[0]

    anchor = datetime.now(timezone.utc).replace(microsecond=0)
    print(("APPLY" if apply else "DRY RUN") + f" — anchor {anchor.isoformat()}, officer {officer['name']}\n")

    def counts() -> dict:
        return {t: len(get("/" + t, {"select": "id"})) for t in (
            "applications", "application_stage_history", "assignment_history", "sla_instances",
            "operational_events", "activity_events", "grievances")}

    before = counts()
    written = {k: 0 for k in before}

    for spec in APPS:
        pid = spec["project_id"]
        proj = get("/projects", {"select": "id,name,owner_id", "id": f"eq.{pid}"})
        if not proj or proj[0]["owner_id"] != owner_id:
            print(f"[{spec['application_id']}] project {pid} missing or not owned by {INDUSTRY_EMAIL} — skipped", file=sys.stderr)
            continue
        name = proj[0]["name"]
        steps = [(anchor - timedelta(days=d), st, (officer["name"] if actor == "OFFICER" else actor), why)
                 for d, st, actor, why in spec["steps"]]
        created_at = steps[0][0]
        last_at = steps[-1][0]
        final_stage = steps[-1][1]

        existing = get("/applications", {"select": "*", "application_id": f"eq.{spec['application_id']}"})
        if existing:
            app_uuid = existing[0]["id"]
            state = "EXISTS (row untouched; topping up missing children only)"
        else:
            app_uuid = str(uuid.uuid4())
            state = "CREATE"
        sla = _compute_sla_state(policy, _iso(created_at), None, now=anchor)
        print(f"[{spec['application_id']}] {state}: {spec['requirement_id']} dept-mpcb {final_stage}, "
              f"assigned={'yes' if spec['assign'] else 'no'}, created {created_at:%Y-%m-%d}, "
              f"expected SLA {getattr(sla['state'], 'value', sla['state'])} ({sla['elapsed_pct']:.0%})")

        if not apply:
            if not existing:
                n = len(steps) + (1 if spec["assign"] else 0)
                for t, k in (("applications", 1), ("application_stage_history", len(steps)), ("sla_instances", 1),
                             ("assignment_history", 1 if spec["assign"] else 0), ("operational_events", n),
                             ("activity_events", n)):
                    written[t] += k
            continue

        if not existing:
            row = {
                "id": app_uuid, "application_id": spec["application_id"], "project_id": pid,
                "department_id": "dept-mpcb", "requirement_id": spec["requirement_id"],
                "title": spec["title"], "applicant_name": name, "current_stage": final_stage,
                "assigned_officer_id": officer["id"] if spec["assign"] else None,
                "sla_policy_id": POLICY_ID, "created_at": _iso(created_at), "updated_at": _iso(last_at),
                "completed_at": None, "data_classification": "SYNTHETIC_DEMO",
            }
            r = store._client.post("/applications", json=row, headers={"Prefer": "return=minimal"})
            assert r.status_code < 400, f"application insert failed: {r.status_code} {r.text}"
            written["applications"] += 1

        def post(table: str, body: dict) -> None:
            r = store._client.post("/" + table, json=body, headers={"Prefer": "return=minimal"})
            assert r.status_code < 400, f"{table} insert failed: {r.status_code} {r.text}"
            written[table] += 1

        have_hist = {h["new_stage"] for h in get("/application_stage_history", {"select": "new_stage", "application_id": f"eq.{app_uuid}"})}
        have_events = {e["message"] for e in get("/operational_events", {"select": "message", "application_id": f"eq.{app_uuid}"})}
        have_assign = bool(get("/assignment_history", {"select": "id", "application_id": f"eq.{app_uuid}"}))
        have_sla = bool(get("/sla_instances", {"select": "id", "application_id": f"eq.{app_uuid}"}))
        have_act = {e["message"] for e in get("/activity_events", {"select": "message", "project_id": f"eq.{pid}"})}

        if not have_sla:
            post("sla_instances", {"id": str(uuid.uuid4()), "application_id": app_uuid, "policy_id": POLICY_ID,
                                   "started_at": _iso(created_at), "completed_at": None, "created_at": _iso(created_at)})

        prev = None
        for at, stage, actor, why in steps:
            if stage == "SUBMITTED":
                ev_type, msg = "APPLICATION_SUBMITTED", f"Application {spec['application_id']} submitted"
            else:
                ev_type, msg = "STAGE_TRANSITION", f"Stage changed from {prev} to {stage}: {why}"
            if stage not in have_hist:
                post("application_stage_history", {"id": str(uuid.uuid4()), "application_id": app_uuid,
                     "previous_stage": prev, "new_stage": stage, "actor": actor, "reason": why, "created_at": _iso(at)})
            if msg not in have_events:
                post("operational_events", {"id": str(uuid.uuid4()), "application_id": app_uuid,
                     "event_type": ev_type, "message": msg, "actor": actor, "created_at": _iso(at)})
            act_msg = f"{spec['application_id']}: {msg}"
            if act_msg not in have_act:
                post("activity_events", {"id": str(uuid.uuid4()), "project_id": pid, "actor": actor,
                     "event_type": ev_type, "message": act_msg, "created_at": _iso(at)})
            if stage == "UNDER_REVIEW" and spec["assign"] and not have_assign:
                at2 = at + timedelta(minutes=1)
                post("assignment_history", {"id": str(uuid.uuid4()), "application_id": app_uuid,
                     "officer_id": officer["id"], "officer_name": officer["name"], "assigned_by": officer["name"],
                     "reason": "Initial assignment (synthetic demo)", "created_at": _iso(at2)})
                post("operational_events", {"id": str(uuid.uuid4()), "application_id": app_uuid,
                     "event_type": "OFFICER_ASSIGNED", "message": f"Assigned to {officer['name']}",
                     "actor": officer["name"], "created_at": _iso(at2)})
                act2 = f"{spec['application_id']}: Assigned to {officer['name']}"
                if act2 not in have_act:
                    post("activity_events", {"id": str(uuid.uuid4()), "project_id": pid, "actor": officer["name"],
                         "event_type": "OFFICER_ASSIGNED", "message": act2, "created_at": _iso(at2)})
                have_assign = True
            prev = stage

    # Approved one-field correction: APP-00003 has sla_policy_id NULL while its sla_instances row already
    # references a policy. Copy THAT policy id into applications.sla_policy_id. Nothing else is touched.
    legacy = get("/applications", {"select": "id,sla_policy_id", "application_id": "eq.APP-00003"})
    if legacy:
        inst = get("/sla_instances", {"select": "policy_id", "application_id": f"eq.{legacy[0]['id']}"})
        want = inst[0]["policy_id"] if inst else None
        if legacy[0]["sla_policy_id"] is not None:
            print("[APP-00003] sla_policy_id already set — patch satisfied")
        elif not want:
            print("[APP-00003] no SLA instance policy to copy — skipped", file=sys.stderr)
        else:
            print(f"[APP-00003] PATCH sla_policy_id NULL -> {want} (from its sla_instances row); no other field")
            if apply:
                r = store._client.patch("/applications", params={"id": f"eq.{legacy[0]['id']}", "sla_policy_id": "is.null"},
                                        json={"sla_policy_id": want}, headers={"Prefer": "return=minimal"})
                assert r.status_code < 400, f"APP-00003 patch failed: {r.status_code} {r.text}"

    after = counts()
    print("\nrow counts before -> after (" + ("rows written" if apply else "rows PLANNED, nothing written") + "):")
    for t in before:
        print(f"  {t}: {before[t]} -> {after[t] if apply else before[t] + written[t]} ({written[t]})")
    print("\nDone." if apply else "\nDry run only — re-run with --apply to write.")


if __name__ == "__main__":
    main()
