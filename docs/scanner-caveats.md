# Scanned-PDF extraction caveats

Some utilities publish rates as scanned images (no text layer), e.g. CAPELCO. These need OCR/table recovery before parsing. Extracted output is a candidate value and always goes through validation.

## Options evaluated

| Option | Notes |
|---|---|
| Docling (MIT) | Tested on one CAPELCO page. Rebuilt the rate table as markdown with all residential values correct. Heavy install (PyTorch, OCR models), Python 3.12. |
| Vision LLM (direct image to JSON) | One API client, no local models. Costs per page, output not deterministic, needs an API key. Tests use recorded responses. |
| MinerU, Marker | Not tested. Reported by third-party comparisons as comparable or slower on CPU. |

Third-party rankings are mostly blog comparisons that disagree with each other; none cover these documents.

## Docling observations (one page, CAPELCO May 2026, page 1)

- All residential column values matched a manual read, including the total and generation rate. The "MAY 2026" heading was recovered.
- Merged cells can leak the row label into a value cell (seen on the OTCA(kW) row). Treat non-numeric cells as null.
- Signatures and stamps come back as image placeholders; ignore them.
- 96 s for one page on a laptop CPU including first-run model downloads; 22-28 s per page afterwards. GPU use not measured.
- Also run on CAPELCO pages from 2018, 2024, 2025 and 2026-09. All four parsed and passed the components-sum check; digits were not otherwise compared against the images.

## Rules for scan extractors

- Only parse pages that hold the rate table; skip supporting computation pages.
- Parse rows by label, not by position. Column order and spelling vary between months.
- Validate before publishing: components sum to the printed total; period in the document matches the period in the filename; value within the configured range.
- Fixed per-customer charges (PHP per month) are not per-kWh components and are excluded from the sum.
- A document that fails these checks is rejected and reported in the pipeline run. An LLM fallback extractor is not implemented.
- Only four CAPELCO months were sampled (2018-01, 2024-06, 2025-03, 2026-09). Other months may use layouts the parser rejects; check before widening the backfill.

## Packaging

- OCR dependencies are an optional extra so the base install and CI stay light.
- Tests use saved extractor output as fixtures; they never run OCR or call an LLM.
