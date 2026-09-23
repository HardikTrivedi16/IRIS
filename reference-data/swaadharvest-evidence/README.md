# SwaadHarvest evidence subset (Evidence Consistency demo integration)

5 of the 28 PDFs from `reference-data/SwaadHarvest_Foods_IRIS_Synthetic_Dataset.zip`
(`source_data/documents/`), extracted here because they are the minimum set
needed for the 4 Evidence Consistency demo findings documented in
`scenarios.json` (copied alongside for reference, along with
`company.json`, `products.json`, `facility_profile.json`,
`documents_manifest.json`). The remaining 23 PDFs are unused by this pass —
loading all 28 was unnecessary for the 4 findings requested.

All documents are explicitly labelled synthetic/fictional inside the PDFs
themselves ("SYNTHETIC DATA — IRIS PROTOTYPE — NOT A GOVERNMENT DOCUMENT").

| File | Used for | Real extracted text confirms |
|---|---|---|
| `FOOD-ENT-003.pdf` | GST Registration Certificate — SwaadHarvest's confirmed project record (seeded into `document.business_name` / `document.location`) | "SwaadHarvest Foods Private Limited", "Plot No. 18, Sector 11, IIE SIDCUL, Haridwar, Uttarakhand - 249403" |
| `FOOD-ENT-006.pdf` | Address-proof electricity bill — company-name variation finding | "Swaad Harvest Foods Pvt Ltd" (vs FOOD-ENT-003's "SwaadHarvest Foods Private Limited") |
| `FOOD-FAC-001.pdf` | Factory licence — premises-address mismatch finding | "Plot No. 20, Sector 11..." (vs FOOD-ENT-003's "Plot No. 18") |
| `FOOD-REG-011.pdf` | Product label — pack-size mismatch finding | "Declared Net Weight: 500 g" for Mango Fruit Pulp (vs `products.json` product master `pack_size: "200 g"` for the same product, IRIS-FOOD-PRD-0001) |
| `FOOD-FAC-004.pdf` | Water Quality Test Report — expired-evidence finding | "Valid Upto: 2025-11-14 (EXPIRED)" |

Text above was read directly from the PDFs via the backend's existing
PyMuPDF text-extraction dependency (no OCR/Ollama needed — these are
born-digital PDFs with a real text layer), not copied from `scenarios.json`
alone — `scenarios.json`'s claims were independently confirmed against the
actual PDF content before anything was wired into the app.
