# 3. Extracted values are candidates until validated

## Context

PDF text layers have garbled digits and OCR misreads tables. A wrong number published as fact is worse than a missing one.

## Decision

Extractors return candidate rates. Two layers check them:

- Parsers cross-check the document against itself and reject it on disagreement: Meralco's printed rate against its bill total, CAPELCO's OCR total against its summary table and against the sum of its components, and the period in the document against the one in the filename.
- Rules in `validation/` then decide `published`, `flagged` or `rejected` for each rate (range, month-over-month change, generation below total, confidence).

A failing document is skipped and reported in the pipeline run; the rest of the run continues.

## Consequences

- Misreads are caught instead of published, at the cost of missing months (seven BENECO months and two CAPELCO generation values in the first live runs).
- Docling is the default for scans because it is free and reproducible. An LLM fallback is planned behind the same interface; its output would go through the same validation.
