"""
Narrow, idempotent showcase-text cleanup (real Supabase). DRY RUN by default; --apply writes.

Replaces development-fixture text on two SYNTHETIC showcase records. Each update is guarded by the EXACT
current junk value in the PATCH filter, so it can only ever change that value once (a second run matches
zero rows) and never overwrites anything else. No status, history, timestamp, actor, or linkage is touched.

    grievances.description    (GRV-E08007FA)  'TEST TEST TEST TEST TEST TEST'  -> professional clarification text
    grievances.resolution_note (GRV-E08007FA) 'TeST TEST test'                 -> professional resolution text
    applications.applicant_name (APP-00003)   'IRIS Supabase Smoke Test'       -> 'SwaadHarvest Foods Private Limited'

NOT changed: grievance_history (append-only by grant; its 'TeST TEST test' note on the RESOLVED transition
cannot be edited), application ids/titles/stages/timestamps, actors, any other row.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CHANGES = [
    {
        "table": "grievances", "key": ("grievance_number", "GRV-E08007FA"),
        "field": "description", "old": "TEST TEST TEST TEST TEST TEST",
        "new": "Clarification requested regarding the additional information sought during application review.",
    },
    {
        "table": "grievances", "key": ("grievance_number", "GRV-E08007FA"),
        "field": "resolution_note", "old": "TeST TEST test",
        "new": "Clarification provided to the applicant regarding the information requested during review.",
    },
    {
        "table": "applications", "key": ("application_id", "APP-00003"),
        "field": "applicant_name", "old": "IRIS Supabase Smoke Test",
        "new": "SwaadHarvest Foods Private Limited",
    },
]


def main() -> None:
    apply = "--apply" in sys.argv
    from app.config import get_settings
    from app.store import get_store

    settings = get_settings()
    if settings.iris_demo_mode or not settings.supabase_configured:
        print("REFUSING TO RUN: real Supabase required, IRIS_DEMO_MODE must be off.", file=sys.stderr)
        raise SystemExit(1)
    store = get_store()
    if type(store).__name__ != "SupabaseStore":
        print(f"REFUSING TO RUN: store is {type(store).__name__}, not SupabaseStore.", file=sys.stderr)
        raise SystemExit(1)

    print(("APPLY" if apply else "DRY RUN") + "\n")
    for c in CHANGES:
        kcol, kval = c["key"]
        rows = store._get("/" + c["table"], {"select": f"{c['field']}", kcol: f"eq.{kval}"})
        cur = rows[0][c["field"]] if rows else "<row missing>"
        state = "TO CHANGE" if cur == c["old"] else ("already clean / different value — no change" if rows else "row missing")
        print(f"{c['table']}.{c['field']} [{kval}]: {cur!r}  ->  {c['new']!r}   ({state})")
        if apply and cur == c["old"]:
            r = store._client.patch(
                "/" + c["table"],
                params={kcol: f"eq.{kval}", c["field"]: f"eq.{c['old']}"},
                json={c["field"]: c["new"]},
                headers={"Prefer": "return=minimal"},
            )
            assert r.status_code < 400, f"{c['table']} patch failed: {r.status_code} {r.text}"
    print("\nDone." if apply else "\nDry run only — re-run with --apply to write.")


if __name__ == "__main__":
    main()
