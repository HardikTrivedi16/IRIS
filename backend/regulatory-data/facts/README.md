# facts/

Provenance substrate (Tranche 1). One `RF-####.yaml` Regulatory Fact record
— an atomic legal proposition — per file, loaded by
`iris_engine.loader.RegulatoryDataset.load`.

**Intentionally empty.** See `authorities/README.md` for why.

Minimum record shape:

```yaml
regulatory_fact_id: RF-####
statement: >                 # the atomic legal proposition, e.g.
  "Food processing units under Schedule 1 entry V with installed capacity
  more than 2 MT/day fall under Central licensing."
evidence_ids: [EVID-####]    # required, non-empty, must resolve — an RF must
                              # point to Evidence, never merely duplicate an
                              # unsourced statement
authority_id: AUTH-####      # required, must resolve
instrument_id: INST-####     # required, must resolve
verification_status: UNVERIFIED   # UNVERIFIED | VERIFIED
```

Rule Versions and Conditions already reference `RF-####` ids today
(`regulatory_fact_ids` / `grounding_regulatory_fact_ids`) — those
references are unresolved until a matching file exists here.
