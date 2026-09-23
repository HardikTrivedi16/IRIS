"""
Idempotent demo seed — Evidence Consistency, real Supabase-backed project.

Populates the ONE thing the existing persistence model actually supports for
this demo: the project's confirmed Project Facts (document.business_name /
document.location) and its document register (metadata only — name,
storage_path, status). Uses only existing store methods
(get_project_facts/merge_project_facts/list_documents/create_document) —
no new table, no schema change, no new subsystem.

There is NO existing persistence path for per-document "candidate"
observations (a second, differing value for the same field, attributed to a
specific document) — the `documents` table is metadata-only by design (see
supabase/migrations/0001_iris_application_schema.sql's own comment: "No
OCR/extraction pipeline is implemented in this pass") and `project_facts`
holds exactly one current value per (project_id, fact_key). That is why the
candidate-side values (Plot 20, "Swaad Harvest...", 500 g, expired date)
still have to be supplied through the existing ManualEntry UI on
/consistency at check time, exactly as they were for the in-memory demo —
this script does not change that, and does not invent a table to avoid it.

Usage (from backend/, with the real Supabase env configured in .env — do
NOT set IRIS_DEMO_MODE):

    .venv/Scripts/python.exe scripts/seed_swaadharvest_demo_evidence.py

Safe to re-run: Project Facts are upserted (merge_project_facts is already
an upsert on (project_id, fact_key)); documents are only created if a
document with the same name doesn't already exist for this project. Nothing
is deleted. No unrelated Project Facts are touched.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROJECT_ID = "92ebc91d-e3e6-46ac-a5ce-46ef5ae240d4"

# Verified FOOD-ENT-003 values (GST Registration Certificate) — the same
# values already confirmed against the real PDF text in the prior pass. Not
# re-derived, not invented here.
_REFERENCE_FACTS = {
    "document.business_name": "SwaadHarvest Foods Private Limited",
    "document.location": "Plot No. 18, Sector 11, IIE SIDCUL, Haridwar, Uttarakhand - 249403",
}

# The 5 documents (of the dataset's 28) already selected and verified for
# this demo — see reference-data/swaadharvest-evidence/README.md. Metadata
# only: name + storage_path + status, matching the documents table's actual
# columns. storage_path points at the file already archived in this repo.
_DOCUMENTS = [
    {
        "name": "GST Registration Certificate (FOOD-ENT-003)",
        "storage_path": "reference-data/swaadharvest-evidence/documents/FOOD-ENT-003.pdf",
        "status": "extracted",
        "linked_requirement_ids": [],
    },
    {
        "name": "Address Proof — Electricity Bill (FOOD-ENT-006)",
        "storage_path": "reference-data/swaadharvest-evidence/documents/FOOD-ENT-006.pdf",
        "status": "extracted",
        "linked_requirement_ids": [],
    },
    {
        "name": "Factory Licence (FOOD-FAC-001)",
        "storage_path": "reference-data/swaadharvest-evidence/documents/FOOD-FAC-001.pdf",
        "status": "extracted",
        "linked_requirement_ids": [],
    },
    {
        "name": "Product Label — Mango Fruit Pulp (FOOD-REG-011)",
        "storage_path": "reference-data/swaadharvest-evidence/documents/FOOD-REG-011.pdf",
        "status": "extracted",
        "linked_requirement_ids": [],
    },
    {
        "name": "Water Quality Test Report (FOOD-FAC-004)",
        "storage_path": "reference-data/swaadharvest-evidence/documents/FOOD-FAC-004.pdf",
        "status": "extracted",
        "linked_requirement_ids": [],
    },
]


def main() -> None:
    from app.config import get_settings
    from app.store import get_store

    settings = get_settings()
    if not settings.supabase_configured:
        print(
            "REFUSING TO RUN: SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are not "
            "both configured — this script only targets the real Supabase-backed "
            "project and must not silently fall back to the in-memory store.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    store = get_store()

    project = store.get_project(PROJECT_ID)
    if project is None:
        print(f"REFUSING TO RUN: project {PROJECT_ID} does not exist.", file=sys.stderr)
        raise SystemExit(1)
    print(f"Target project: {project['id']} — {project.get('name')!r} (owner_id={project.get('owner_id')})")

    before = store.get_project_facts(PROJECT_ID)
    unrelated_before = {k: v for k, v in before.items() if k not in _REFERENCE_FACTS}
    after = store.merge_project_facts(PROJECT_ID, _REFERENCE_FACTS)
    unrelated_after = {k: v for k, v in after.items() if k not in _REFERENCE_FACTS}
    assert unrelated_before == unrelated_after, "an unrelated Project Fact changed — aborting"
    print("Project Facts (document.business_name / document.location) upserted:")
    for k in _REFERENCE_FACTS:
        print(f"  {k} = {after.get(k)!r}")
    print(f"  ({len(unrelated_after)} unrelated existing fact(s) left untouched)")

    existing_names = {d["name"] for d in store.list_documents(PROJECT_ID)}
    created, skipped = [], []
    for doc in _DOCUMENTS:
        if doc["name"] in existing_names:
            skipped.append(doc["name"])
            continue
        record = store.create_document({"project_id": PROJECT_ID, **doc})
        created.append(record["name"])
    print(f"Documents created: {created or '(none)'}")
    print(f"Documents already present, skipped: {skipped or '(none)'}")


if __name__ == "__main__":
    main()
