# Data dictionary

## rate (API: `/v1/rates`, table `rate_observation`)

| Field | Type | Meaning |
|---|---|---|
| `id` | integer | Row ID |
| `utility_id` | string | Utility slug, e.g. `meralco` |
| `period` | string | Billing month, ISO 8601 `YYYY-MM` |
| `customer_class` | enum | `residential` (only value for now) |
| `rate_per_kwh` | number | PHP per kWh, 4 decimals. See "What the rate means" |
| `rate_basis` | enum | `published_total`: the source prints the per-kWh total. `summed_components`: computed by us from published components (reserved; no current source) |
| `generation_charge_per_kwh` | number or null | PHP per kWh generation charge, when the source gives it. Blank for most CAPELCO months; see data gotchas |
| `currency` | string | `PHP` |
| `extraction_method` | enum | `html_parser`, `pdf_parser`, `ocr_parser`, `llm`, `manual` |
| `status` | enum | `published`, `flagged` (failed a soft rule, needs review), `rejected` (failed a hard rule) |
| `flags` | list of string | Rule codes that fired, e.g. `mom_change_exceeds_threshold` |
| `created_at` | datetime | When we stored the row |
| `source` (detail only) | object | `url`, `fetched_at`, `content_type`, `sha256` of the raw document |

Internal columns not in the API: `extractor_version`, `model`, `confidence`, `source_document_id`. A value is stored once per (utility, month, value); a changed value for a month becomes a new row.

## utility (`/v1/utilities`)

| Field | Meaning |
|---|---|
| `id` | Stable slug |
| `name` | Full name |
| `type` | `private_du`, `electric_cooperative`, `supplier` |
| `psgc_code` | Philippine Standard Geographic Code (not filled yet) |
| `aliases` | Other names |
| `erc_id`, `nea_id` | Agency identifiers (not filled yet) |

## What the rate means

- Meralco: the overall rate printed for 200 kWh of residential consumption, all charges and taxes included.
- CAPELCO: `TOTAL RATE PER KWH (Corrected)` for residential. It equals the sum of the printed per-kWh components; VAT is shown separately, so it appears to be pre-VAT.
- BENECO: `Total Php/kWh` for residential from the monthly breakdown table, at 4 decimals. Components include VAT, so it appears to be all-in.

These are not interchangeable. See [data gotchas](data-gotchas.md).

## Validation rules

| Rule | Outcome |
|---|---|
| Rate outside 5 to 40 PHP/kWh | rejected (`rate_out_of_range`) |
| Change from previous month over 30% | flagged (`mom_change_exceeds_threshold`) |
| Generation charge not below total | rejected (`generation_not_below_total`) |
| Extractor confidence below 0.8 | flagged (`low_confidence`) |

Thresholds are settings (`PH_ENERGY_RATE_MIN` and so on). Parsers also reject whole documents that fail their own cross-checks.

## Exports

`/v1/exports/rates.csv` and `.json` contain published rates only, with `observation_id`, the fields above, and `source_url`, `source_fetched_at`, `source_sha256`.
