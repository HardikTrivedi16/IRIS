# sources/

Provenance substrate (Tranche 1). One `SRC-####.yaml` record per official
source document, loaded by `iris_engine.loader.RegulatoryDataset.load`.

**Intentionally empty.** See `authorities/README.md` for why.

Minimum record shape:

```yaml
source_id: SRC-####
title: "..."
publisher_authority_id: AUTH-####   # required, must resolve
document_type: GAZETTE              # e.g. GAZETTE | INDIA_CODE | OFFICIAL_WEBSITE
official_url: "https://..."
publication_date: "1974-03-23"      # optional where genuinely unavailable
retrieved_date: "2026-09-01"
archived_artifact_path: null        # optional — see note below
checksum_sha256: null               # optional — of the archived artifact, if present
source_status: AVAILABLE            # truthful status only, see note below
```

**No source archival mechanism exists in this repository yet.** A URL and a
retrieval date are NOT archived evidence. Do not set `source_status:
ARCHIVED` or populate `archived_artifact_path`/`checksum_sha256` unless a
real, checked-in artifact backs it — that capability is a separate future
pass, not part of this substrate.
