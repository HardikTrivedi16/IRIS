# archive/

Genuinely retrieved, checked-in primary-source artifacts backing a
`Source` record's `source_status: ARCHIVED` and `checksum_sha256`
(see `../sources/README.md`).

A file in this directory is added only when it was actually downloaded from
an official host (the issuing authority's own site, an official Government
of India host, or the Gazette of India) and its SHA-256 was computed from the
saved bytes — never fabricated. The corresponding `SRC-####.yaml` record's
`archived_artifact_path` points at the file, and `checksum_sha256` is the
hash of that exact file.

| File | SRC record | SHA-256 |
|---|---|---|
| `SRC-004_Compendium_Licensing_Regulations_04_08_2021.pdf` | SRC-004 | `041ef7e7d3a4b6d11c084182217e0d7d9d73488490b6ff1484a4a41a5d906fd8` |
| `SRC-011_Order_13Mar2026_Revised_Turnover_Threshold.pdf` | SRC-011 | `5b28f6e8306dcfbfa957e709b6c8f51f44be485ebe9cf600c6b040f8b8280d90` |
| `SRC-012_FoSCoS_KindOfBusinessEligibility_02Apr2026.pdf` | SRC-012 | `d066f7e7284a600abe3438ad9a5ac3a2098e799433446e113b6f9288e4668c85` |
