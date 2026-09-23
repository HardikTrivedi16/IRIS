"""
Idempotent real-Supabase seed — IRIS five-sector demo portfolio.

Projects (one per sector):
    swaadharvest             FOOD        reuses 92ebc91d-e3e6-46ac-a5ce-46ef5ae240d4 (presentation update; legacy Haridwar evidence retained)
    aarav-lifesciences       PHARMA      reuses the existing project (converted to a Maharashtra plant)
    voltedge-mobility        AUTO / EV   new
    deccan-microelectronics  ELECTRONICS new
    konkan-specialty-chemicals CHEMICALS new

DEFAULT IS A DRY RUN. Nothing is written unless --apply is passed.

    .venv/Scripts/python.exe scripts/seed_five_project_portfolio.py            # dry run
    .venv/Scripts/python.exe scripts/seed_five_project_portfolio.py --apply    # write

Safety:
  * refuses to run unless real Supabase is configured (never the MemoryStore, never IRIS_DEMO_MODE);
  * never deletes anything; facts are upserted on (project_id, fact_key) — unrelated facts untouched;
  * existing projects are only PATCHed on the listed presentation columns (name/activity/location/workers); ids and owner_id are never
    changed, except aarav-lifesciences (approved, synthetic demo project): owner_id is set to industry@ ONLY while it is
    still NULL — an already-owned project is never re-assigned;
  * new projects are created only if the id does not exist, owned by the existing industry@gmail.com user
    (looked up in user_profiles — no auth user is created or modified);
  * safe to run twice.

PROVENANCE CLASSES for every fact below (there is no table for this, so it lives here):
    "A"     EVIDENCE_SUPPORTED   backed by the committed synthetic reference dataset / existing project record
    "B"     SYNTHETIC_DEMO_FACT  deliberately authored fictional characteristic. NOT extracted from any document.
    "RESET" existing value is unsupported; written as JSON null (= UNKNOWN)
LEGACY EVIDENCE: the committed SwaadHarvest PDFs (Haridwar, Uttarakhand) and Aarav's 22 existing DOC-* documents /
document.* facts (Uttarakhand licence, UEPPCB consent, etc.) are HISTORICAL evidence of the prior Haridwar / Selaqui
facilities. They do not evidence the current Maharashtra locations, which are SYNTHETIC_DEMO_FACT. They are not
modified, renamed or deleted; Evidence Consistency may legitimately flag the old address for human review.

RESET facts are cleared with a JSON null (project_facts.fact_value is nullable jsonb; the engine treats null as UNKNOWN).
Negative (false) trigger facts are set ONLY for the three synthetic projects where they are part of the designed profile;
SwaadHarvest and Aarav leave unrelated sector triggers UNKNOWN.

FUTURE INTEGRATION BLOCKER (not fixed here): the regulatory dataset has no jurisdiction/state guard on several
Maharashtra-scoped requirements, so the Uttarakhand projects (SwaadHarvest, Aarav) can evaluate Maharashtra-scoped
rules diagnostically. No relocation to Maharashtra is invented.

Facts not listed are intentionally UNKNOWN (C) — e.g. boiler litres/pressure/certificate, most hazardous-waste
and groundwater facts — so IRIS asks for them instead of showing invented values.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

P = "project."
INDUSTRY_EMAIL = "industry@gmail.com"

# --- Project records --------------------------------------------------------
# mode "update": PATCH only these presentation columns on the existing row.
# mode "create": insert if the id is absent.
PROJECTS = {
    "92ebc91d-e3e6-46ac-a5ce-46ef5ae240d4": {
        "mode": "update", "key": "swaadharvest",
        "row": {
            "name": "SwaadHarvest Foods Private Limited",
            "activity": "Manufacture of processed fruit and vegetable products, sauces/condiments and "
                        "ready-to-eat packaged food",
            "location": "Supa MIDC, Pune district, Maharashtra",   # CURRENT facility — SYNTHETIC_DEMO_FACT
            "workers": 46,
        },
    },
    "aarav-lifesciences": {
        "mode": "update", "key": "aarav-lifesciences", "assign_owner_if_unowned": True,
        "row": {   # presentation converted from the legacy "Selaqui Formulations Plant" to a current Maharashtra plant
            "name": "Aarav Lifesciences Private Limited",
            "location": "Waluj MIDC, Chhatrapati Sambhajinagar, Maharashtra",   # CURRENT — SYNTHETIC_DEMO_FACT
        },
    },
    "voltedge-mobility": {
        "mode": "create", "key": "voltedge-mobility",
        "row": {
            "name": "VoltEdge Mobility Private Limited",
            "industry": "automobile-ev",
            "activity": "Assembly of electric two- and three-wheelers and battery-pack assembly (synthetic demo company)",
            "location": "Chakan MIDC, Pune, Maharashtra",
            "stage": "operation", "scale": "medium", "workers": 240,
            "characteristics": {"waterUse": True, "wastewater": True, "airEmissions": True,
                                "hazardousWaste": True, "chemicalStorage": True, "hazardousChemicals": False},
        },
    },
    "deccan-microelectronics": {
        "mode": "create", "key": "deccan-microelectronics",
        "row": {
            "name": "Deccan Microelectronics Private Limited",
            "industry": "electronics-esdm",
            "activity": "PCB assembly and electronics manufacturing sold under own brand (synthetic demo company)",
            "location": "Ranjangaon MIDC, Pune, Maharashtra",
            "stage": "operation", "scale": "small", "workers": 120,
            "characteristics": {"waterUse": True, "wastewater": True, "airEmissions": True,
                                "hazardousWaste": True, "chemicalStorage": True, "hazardousChemicals": False},
        },
    },
    "konkan-specialty-chemicals": {
        "mode": "create", "key": "konkan-specialty-chemicals",
        "row": {
            "name": "Konkan Specialty Chemicals Private Limited",
            "industry": "chemicals",
            "activity": "Manufacture of specialty organic chemicals and intermediates (synthetic demo company)",
            "location": "Mahad MIDC, Raigad, Maharashtra",
            "stage": "operation", "scale": "medium", "workers": 62,
            "characteristics": {"waterUse": True, "wastewater": True, "airEmissions": True,
                                "hazardousWaste": True, "chemicalStorage": True, "hazardousChemicals": True},
        },
    },
}

# --- Facts: key -> (value, provenance class) --------------------------------
FACTS = {
    # NOTE: every SwaadHarvest / Aarav fact below is a CURRENT-Maharashtra SYNTHETIC_DEMO_FACT. Where a value was
    # carried over from the legacy Haridwar / Selaqui material (worker counts, power, effluent, prepack, licence) it is
    # a carried-forward assumption, NOT evidence about the current Maharashtra facility.
    "swaadharvest": {
        P+"industry": ("FOOD", "B"),
        P+"food_subsector": ("OTHER_FOOD_PROCESSING", "B"),   # facility_profile.subsector: fruit & veg + packaged foods
        P+"annual_turnover_inr": (400000000, "B"),             # 40 crore INR -> current FSSAI State-licence band
        P+"worker_count": (46, "B"),                           # facility_profile.employees_total
        P+"manufacturing_process_uses_power": (True, "B"),     # electricity_load_kva 320
        P+"likely_to_discharge_sewage_or_trade_effluent": (True, "B"),   # wastewater_generation_kld 36 + ETP
        P+"prepacks_commodities_for_retail_sale": (True, "B"), # branded pouch products (products.json)
        P+"state": ("MAHARASHTRA", "B"),                        # current facility state (not consumed by any current rule)
        P+"location_state": ("MAHARASHTRA", "B"),               # consumed by the Maharashtra scheme conditions
        P+"plant_located_in_air_pollution_control_area": (True, "B"),   # Maharashtra-wide APCA (research RF-0002); jurisdictional derivation
    },
    "aarav-lifesciences": {   # existing evidence: project row + 22 DOC-* documents
        P+"industry": ("PHARMACEUTICAL", "B"),
        P+"pharma_activity_type": ("FORMULATIONS", "B"),                   # project.activity: tablets, oral powders
        P+"manufactures_drugs_for_sale_or_distribution": (True, "B"),
        # legacy SCHEDULE_H answers a different legal question than the corrected C/C1/X ENUM, and the Aarav
        # evidence lists only Schedule H / OTC products (not proof that NO product is C/C1/X) -> cleared to UNKNOWN.
        # The historical SCHEDULE_H value in the 0005 seed migration / documents is untouched.
        P+"drug_schedule_classification": (None, "RESET"),
        P+"holds_drug_manufacturing_licence": (True, "B"),                 # DOC-REG-001 licence UK/DL/2019/00417
        P+"worker_count": (85, "B"),                                       # project.workers
        P+"manufacturing_process_uses_power": (True, "B"),
        P+"likely_to_discharge_sewage_or_trade_effluent": (True, "B"),     # existing fact, unchanged
        P+"msme_classification": ("MEDIUM", "B"),
        P+"udyam_registered": (True, "B"),
        P+"state": ("MAHARASHTRA", "B"),                        # current facility state (not consumed by any current rule)
        P+"location_state": ("MAHARASHTRA", "B"),               # consumed by the Maharashtra scheme conditions
        P+"plant_located_in_air_pollution_control_area": (True, "B"),   # Maharashtra-wide APCA (research RF-0002); jurisdictional derivation
    },
    "voltedge-mobility": {
        P+"industry": ("AUTOMOBILE_EV", "B"),
        P+"manufactures_motor_vehicles_for_sale": (True, "B"),
        P+"places_batteries_on_market": (True, "B"),       # AU-02 trigger: own-brand vehicles containing batteries
        P+"worker_count": (240, "B"),
        P+"manufacturing_process_uses_power": (True, "B"),
        P+"likely_to_discharge_sewage_or_trade_effluent": (True, "B"),   # paint shop
        P+"plant_located_in_air_pollution_control_area": (True, "B"),    # Maharashtra-wide APCA (research RF-0002)
        P+"generates_or_handles_scheduled_hazardous_waste": (True, "B"), # paint sludge / spent thinners
        P+"groundwater_abstraction_m3_per_day": (0, "B"),                # municipal supply only
        P+"prepacks_commodities_for_retail_sale": (False, "B"),
        P+"located_in_notified_industrial_area": (True, "B"),            # MIDC
        P+"msme_classification": ("NOT_MSME", "B"),
        P+"udyam_registered": (False, "B"),
        P+"state": ("MAHARASHTRA", "B"),
        P+"location_state": ("MAHARASHTRA", "B"),
        P+"manufactures_schedule1_eee": (False, "B"),
        P+"sells_schedule1_eee_under_own_brand": (False, "B"),
        P+"msihc_schedule3_chemical_at_or_above_threshold": (False, "B"),
    },
    "deccan-microelectronics": {
        P+"industry": ("ELECTRONICS_ESDM", "B"),
        P+"manufactures_schedule1_eee": (True, "B"),
        P+"sells_schedule1_eee_under_own_brand": (True, "B"),
        P+"places_batteries_on_market": (False, "B"),
        P+"manufactures_motor_vehicles_for_sale": (False, "B"),
        P+"worker_count": (120, "B"),
        P+"manufacturing_process_uses_power": (True, "B"),
        P+"likely_to_discharge_sewage_or_trade_effluent": (True, "B"),   # PCB wet-process line
        P+"plant_located_in_air_pollution_control_area": (True, "B"),
        P+"generates_or_handles_scheduled_hazardous_waste": (True, "B"), # etchants / solder dross
        P+"groundwater_abstraction_m3_per_day": (12, "B"),
        P+"located_in_notified_industrial_area": (True, "B"),
        P+"msme_classification": ("SMALL", "B"),
        P+"udyam_registered": (True, "B"),
        P+"state": ("MAHARASHTRA", "B"),
        P+"location_state": ("MAHARASHTRA", "B"),
        P+"msihc_schedule3_chemical_at_or_above_threshold": (False, "B"),
    },
    "konkan-specialty-chemicals": {
        P+"industry": ("CHEMICALS", "B"),
        P+"msihc_schedule3_chemical_at_or_above_threshold": (True, "B"),   # CH-02/CH-03 trigger (worksheet result)
        P+"worker_count": (62, "B"),
        P+"manufacturing_process_uses_power": (True, "B"),
        P+"likely_to_discharge_sewage_or_trade_effluent": (True, "B"),
        P+"plant_located_in_air_pollution_control_area": (True, "B"),
        P+"generates_or_handles_scheduled_hazardous_waste": (True, "B"),  # spent solvents / residues
        P+"groundwater_abstraction_m3_per_day": (30, "B"),
        P+"prepacks_commodities_for_retail_sale": (False, "B"),
        P+"located_in_notified_industrial_area": (True, "B"),
        P+"msme_classification": ("MEDIUM", "B"),
        P+"udyam_registered": (True, "B"),
        P+"state": ("MAHARASHTRA", "B"),
        P+"location_state": ("MAHARASHTRA", "B"),
        P+"manufactures_motor_vehicles_for_sale": (False, "B"),
        P+"places_batteries_on_market": (False, "B"),
        P+"manufactures_schedule1_eee": (False, "B"),
        P+"sells_schedule1_eee_under_own_brand": (False, "B"),
    },
}
# Deliberately NOT set anywhere (UNKNOWN): boiler_volumetric_capacity_litres, boiler_design_gauge_pressure_kg_cm2,
# holds_boiler_certificate, export_share_of_turnover_pct, pharma_activity_type (non-pharma), and — for
# SwaadHarvest — msme_classification, udyam_registered, groundwater split, hazardous-waste handling.


def main() -> None:
    apply = "--apply" in sys.argv

    from app.config import get_settings
    from app.store import get_store

    settings = get_settings()
    if settings.iris_demo_mode or not settings.supabase_configured:
        print("REFUSING TO RUN: real Supabase must be configured and IRIS_DEMO_MODE must be off.", file=sys.stderr)
        raise SystemExit(1)
    store = get_store()
    if type(store).__name__ != "SupabaseStore":
        print(f"REFUSING TO RUN: store is {type(store).__name__}, not SupabaseStore.", file=sys.stderr)
        raise SystemExit(1)

    owners = store._get("/user_profiles", {"select": "supabase_auth_uid", "email": f"eq.{INDUSTRY_EMAIL}"})
    if not owners:
        print(f"REFUSING TO RUN: no user_profiles row for {INDUSTRY_EMAIL}.", file=sys.stderr)
        raise SystemExit(1)
    owner_id = owners[0]["supabase_auth_uid"]
    print(("APPLY" if apply else "DRY RUN") + f" — owner for new projects: {INDUSTRY_EMAIL} ({owner_id})\n")

    for pid, spec in PROJECTS.items():
        key = spec["key"]
        existing = store.get_project(pid)
        before_facts = store.get_project_facts(pid) if existing else {}
        facts = {k: v for k, (v, _cls) in FACTS[key].items()}
        changed = {k: (before_facts.get(k, "<unset>"), v) for k, v in facts.items() if before_facts.get(k, "<unset>") != v}

        if existing is None and spec["mode"] == "update":
            print(f"[{pid}] MISSING but expected to exist — skipping.", file=sys.stderr)
            continue
        action = "CREATE" if existing is None else ("PATCH presentation" if spec["row"] else "no project-row change")
        assign = bool(existing) and spec.get("assign_owner_if_unowned") and existing.get("owner_id") is None
        if assign:
            action += f" + owner_id None -> {owner_id!r} (industry@)"
        elif existing and spec.get("assign_owner_if_unowned") and existing.get("owner_id") not in (None, owner_id):
            print(f"    WARNING: {pid} is owned by another user — ownership left unchanged.", file=sys.stderr)
        print(f"[{pid}] {action}; facts to upsert: {len(changed)}/{len(facts)}")
        for k, (b, a) in sorted(changed.items()):
            print(f"    {k}: {b!r} -> {a!r}")
        if not apply:
            continue

        if existing is None:
            store.create_project({"id": pid, **spec["row"], "owner_id": owner_id})
        else:
            patch = dict(spec["row"])
            if assign:
                patch["owner_id"] = owner_id
            if patch:
                store._patch("/projects", {"id": f"eq.{pid}"}, patch)
        unrelated_before = {k: v for k, v in before_facts.items() if k not in facts}
        after = store.merge_project_facts(pid, facts)
        assert {k: v for k, v in after.items() if k not in facts} == unrelated_before, \
            f"unrelated fact changed for {pid} — aborting"

    print("\nDone." if apply else "\nDry run only — re-run with --apply to write.")


if __name__ == "__main__":
    main()
