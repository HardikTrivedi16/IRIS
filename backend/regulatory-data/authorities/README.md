# authorities/

Provenance substrate (Tranche 1). One `AUTH-####.yaml` record per regulatory
authority, loaded by `iris_engine.loader.RegulatoryDataset.load`.

**Intentionally empty.** No Authority record exists yet — the existing
Requirements and Rule Versions reference `authority_id` values
(`AUTH-MPCB`, `AUTH-MoEFCC`, `AUTH-CDSCO`, `AUTH-FSSAI`) as unresolved ID
references only. This directory exists so those references become
resolvable once verified research is integrated; adding a file here is a
deliberate, versioned act, not something to do to "fill" the directory.

Minimum record shape (see `docs/REGULATORY_PACK_INPUT_REQUIREMENTS.md`):

```yaml
authority_id: AUTH-####        # required, unique
name: "..."                    # required
level: STATE_REGULATOR         # required — CENTRAL | STATE_REGULATOR | STATUTORY_BODY | ...
jurisdiction: MAHARASHTRA      # required
parent_authority_id: null      # optional, must resolve to a real AUTH-#### if set
notes: >                       # optional
  ...
```

Do not rename the four existing authority ids above — see
`docs/REGULATORY_PACK_INPUT_REQUIREMENTS.md` for the compatibility note.
