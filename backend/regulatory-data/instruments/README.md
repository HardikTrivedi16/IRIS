# instruments/

Provenance substrate (Tranche 1). One `INST-####.yaml` record per legal
instrument (Act/Rule/Regulation), loaded by
`iris_engine.loader.RegulatoryDataset.load`.

**Intentionally empty.** See `authorities/README.md` for why.

Minimum record shape:

```yaml
instrument_id: INST-####
short_title: "..."
full_citation: "..."
issuing_authority_id: AUTH-####   # required, must resolve
year: 1974
currency_status: IN_FORCE         # IN_FORCE | REPEALED | TRANSITIONAL | SUPERSEDED
effective_start_date: "1974-03-23"
effective_end_date: null          # optional
supersedes_instrument_id: null    # optional, must resolve if set
superseded_by_instrument_id: null # optional, must resolve if set
last_currency_check: "2026-09-01" # required — when currency_status was last confirmed
notes: >
  ...
```

`currency_status` is about the INSTRUMENT (has the law itself been
repealed/superseded?) — distinct from a Rule Version's own `status`
(DRAFT/ACTIVE/SUPERSEDED/RETIRED), which is IRIS's own interpretation
lifecycle. An ACTIVE Rule Version referencing a currently REPEALED or
SUPERSEDED instrument fails the dataset validator's ACTIVE promotion gate
unless the Rule Version's own `effective_end_date` falls within the
instrument's former validity window (see `iris_engine/validate.py`).
