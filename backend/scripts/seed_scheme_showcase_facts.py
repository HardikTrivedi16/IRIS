"""
Idempotent real-Supabase fact delta for the Scheme Catalogue Tranche 1 showcase (SCH-0005 .. SCH-0010).

DEFAULT IS A DRY RUN. Nothing is written unless --apply is passed.

    .venv/Scripts/python.exe scripts/seed_scheme_showcase_facts.py            # dry run: prints the delta + simulated matrix
    .venv/Scripts/python.exe scripts/seed_scheme_showcase_facts.py --apply    # write

Only the approved POSITIVE synthetic facts are set (provenance class B, SYNTHETIC_DEMO_FACT: deliberately authored, not extracted
from any document). No explicit false / negative facts are invented: everything else stays UNKNOWN, so IRIS reports NEEDS_INFORMATION
rather than a manufactured result. project.is_new_unit / project.is_expansion are deliberately NOT set on any project.

Safety: refuses demo/memory mode; requires SupabaseStore; uses merge_project_facts (upsert on (project_id, fact_key)); unrelated facts
are asserted unchanged; deletes nothing; projects, applications, documents, grievances and department data are never touched.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

P = "project."
# project_id -> {fact_key: value}   (all class B, SYNTHETIC_DEMO_FACT)
DELTA = {
    "deccan-microelectronics": {
        P + "manufactures_ecms_eligible_product": True,   # F-21
        P + "ecms_target_segment": "D",                   # F-20
        P + "sells_within_maharashtra": True,             # F-17
    },
    "voltedge-mobility": {
        P + "ev_value_chain_role": "VEHICLE_OEM",         # F-23 (research ENUM value for a vehicle OEM)
    },
    "aarav-lifesciences": {
        P + "sells_within_maharashtra": True,             # F-17
    },
    "konkan-specialty-chemicals": {
        P + "sells_within_maharashtra": True,             # F-17
    },
}
ALL_PROJECTS = {
    "SwaadHarvest": "92ebc91d-e3e6-46ac-a5ce-46ef5ae240d4",
    "Aarav": "aarav-lifesciences",
    "VoltEdge": "voltedge-mobility",
    "Deccan": "deccan-microelectronics",
    "Konkan": "konkan-specialty-chemicals",
}
NEW_SCHEMES = ["SCH-0005", "SCH-0006", "SCH-0007", "SCH-0008", "SCH-0009", "SCH-0010"]


def main() -> None:
    apply = "--apply" in sys.argv

    from app.config import get_settings
    from app.store import get_store
    from app import schemes

    settings = get_settings()
    if settings.iris_demo_mode or not settings.supabase_configured:
        print("REFUSING TO RUN: real Supabase must be configured and IRIS_DEMO_MODE must be off.", file=sys.stderr)
        raise SystemExit(1)
    store = get_store()
    if type(store).__name__ != "SupabaseStore":
        print(f"REFUSING TO RUN: store is {type(store).__name__}, not SupabaseStore.", file=sys.stderr)
        raise SystemExit(1)

    print(("APPLY" if apply else "DRY RUN") + "\n\nFact delta (existing -> proposed):")
    total = 0
    for pid, facts in DELTA.items():
        if store.get_project(pid) is None:
            print(f"  [{pid}] MISSING — skipped", file=sys.stderr)
            continue
        before = store.get_project_facts(pid)
        changed = {k: (before.get(k, "<unset>"), v) for k, v in facts.items() if before.get(k, "<unset>") != v}
        for k, (b, a) in sorted(changed.items()):
            print(f"  [{pid}] {k}: {b!r} -> {a!r}")
        if not changed:
            print(f"  [{pid}] already satisfied")
        total += len(changed)
        if apply and changed:
            after = store.merge_project_facts(pid, facts)
            unrelated_before = {k: v for k, v in before.items() if k not in facts}
            assert {k: v for k, v in after.items() if k not in facts} == unrelated_before, f"unrelated fact changed for {pid}"
    print(f"\n{total} fact value(s) {'written' if apply else 'would be written'}.")

    # Matrix: persisted facts overlaid with the delta IN MEMORY (dry run) / read back (apply).
    cat = schemes.load_catalogue(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scheme-data"))
    assert not cat.errors, cat.errors
    print("\nScheme matrix (NON_PRODUCTION diagnostic; eligibility / application_status):")
    ids = ["SCH-0001", "SCH-0002", "SCH-0004"] + NEW_SCHEMES
    header = "".ljust(10) + "".join(n.ljust(38) for n in ALL_PROJECTS)
    print(header)
    rows = {}
    for name, pid in ALL_PROJECTS.items():
        facts = dict(store.get_project_facts(pid))
        if not apply:
            facts.update(DELTA.get(pid, {}))
        res = schemes.match_catalogue(cat, facts, mode="NON_PRODUCTION")["results"]
        rows[name] = {r["scheme_id"]: r for r in res}
    for sid in ids:
        cells = []
        for name in ALL_PROJECTS:
            r = rows[name][sid]
            cells.append(f"{r['outcome']} / {r.get('application_status') or '-'}".ljust(38))
        print(sid.ljust(10) + "".join(cells))
    print("\nDone." if apply else "\nDry run only — re-run with --apply to write.")


if __name__ == "__main__":
    main()
