# evidence/

Provenance substrate (Tranche 1). One `EVID-####.yaml` record per bounded
excerpt of a Source, loaded by `iris_engine.loader.RegulatoryDataset.load`.

**Intentionally empty.** See `authorities/README.md` for why.

Minimum record shape:

```yaml
evidence_id: EVID-####
source_id: SRC-####          # required, must resolve
section_or_clause: "Section 25(1)(a)"
page: 4                      # optional
excerpt: "..."               # required — a bounded quote, not a full-text copy
verification_status: UNVERIFIED   # UNVERIFIED | VERIFIED
```

A research excerpt is a pointer/citation only. It becomes an Evidence
record (unverified) but is never an "archived" claim — see
`sources/README.md`.
