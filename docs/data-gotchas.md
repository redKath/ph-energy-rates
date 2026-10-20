# Data gotchas (prototype sources)

Source quirks the collectors and validators must handle. Observed October 2026; sources can change layout without notice.

## BENECO (Benguet Electric Cooperative)

- Source: `https://www.beneco.com.ph/rates.php`. The page's JavaScript loads per-month HTML fragments from the same URL, and the collector uses those: `rates.php?q=month&monthyear=<Month YYYY>` returns a table for every customer type with all charge components and `Total Php/kWh` at 4 decimals. `rates.php?q=month` returns the month selector (129 months, February 2016 onward, newest first). The collector reads the 24 newest.
- The static table on `rates.php` itself is a 12-month, 2-decimal summary of the same totals and is not used. `rates.php?q=generation` returns a 12-month generation chart and links to monthly generation-rate PDFs; not used.
- The selector lists months before BENECO has published them (October 2026 had no table); those yield no rates.
- Residential generation charge and total come from the `Residential` row, located by column header.
- The printed total does not always equal the sum of the per-kWh components: it differs by 0.003 to 0.03 in some months. The cross-check tolerance is 0.05.
- Some tables contain source errors and are rejected: November 2025 shows `VAT Php/kWh` 7.9249 (looks like a misplaced decimal), and 2024-11, 2025-05 to 2025-08 and 2025-10 differ from their component sums by more than the tolerance. Those months are missing from the dataset.
- No `robots.txt` (server returns an HTML page).

## Meralco

- Source: HTML archive listing `https://company.meralco.com.ph/news-and-advisories/rates-archives` (`?page=N`, four months per page) linking to PDFs on S3.
- Use the "Typical Consumption Levels" PDFs (`*_residential_bills*.pdf`). They have a text layer.
- Take PDF links from the listing; do not construct URLs. Names vary (`..._residential_bills_v2.pdf`). Other PDFs on the listing (schedule of rates, generation charge) are not used.
- Each PDF has two tables for non-lifeline customers: a bill in pesos per consumption level, and the same rows per kWh. The per-kWh row for 200 kWh ends with the overall rate (e.g. 15.0615 for October 2026), which matches Meralco's announced rate. Its first value is the generation charge per kWh.
- The PDF text layer has stray spaces inside some numbers (`1 ,940.64`, `9 .2504`, `1 3.1145`) and column sets differ by month. The extractor repairs the known patterns and requires the per-kWh row to agree with the bill row (total / 200); otherwise the document is rejected.
- The billing month heading is `October 2026` in most files and `Jul-26` in some.
- Older months were not checked; the collector reads the three most recent listing pages (about a year).
- The separate "Summary Schedule of Rates" PDF lists charge components only (parentheses are negative refunds) and is not used.
- No `robots.txt`.

## CAPELCO (Capiz Electric Cooperative)

- Source: listing page `https://capelco.com/official/power-rates/`. It has two kinds of data:
  - A **summary table** (`Period | Residential | Low Voltage | High Voltage | Link`) with the residential total for every month from 2018-01 to the latest, at 4 decimals. The period is `26-Sep` style. No generation charge. This is the source of every month's total.
  - One scanned PDF per month, 2018 onward (104 links). Only the 12 most recent are OCRed, for the generation charge. The OCR total must equal the summary table's total for the month, otherwise the PDF is rejected.
- If a month has both, the PDF-derived row (with generation) is stored first and the table row is skipped as a duplicate. If the PDF arrives later than the table row, it is stored as a second row for that month because it adds the generation charge.
- The summary table's `Link` column and the PDF links are the same files. The listing page is fetched twice per run (once for discovery, once as a document).
- Documents are scanned images. Some have an embedded OCR text layer (2018-2022, 2025-03) that is unreliable (`LOWVOLTAGE`, `ToAll`); others have none (2024-06, 2026-09). The extractor ignores embedded text and OCRs page 1 itself.
- Page count varies (1 page in most files, 8 in 2026-05). Page 1 holds the rate table; the rest are supporting computations.
- Filenames: `Sept` not `Sep`, `June`/`July` in places, and `_opt` copies (`2025-Rates-May_opt.pdf`). The upload folder (`/2026/03/`) is not always the rate month. The period comes from the filename and must match the "month of MAY 2026" heading in the PDF.
- Layout drift between years: merged header cells read twice (`RESIDENTIAL RESIDENTIAL`); negatives as `-0.0758` or `(.0918)`; generation either one row ("Adjusted Generation Rate + OGA") or two (adjusted rate plus a separate OGA row). Generation per kWh is the sum of the generation rows.
- A label can be repeated in a value cell after OCR (OTCA(kW) row); non-numeric cells are ignored.
- The residential total (`TOTAL RATE PER KWH (Corrected)`) equals the sum of the per-kWh component rows above it. Excluded: the fixed `Retail Customer Charge` (PHP per month), kW-based demand rows, and the memo rows below the total (which show VAT portions, e.g. generation 0.5034). Documents where this does not hold are rejected.
- Known failures: `2026-Rates-Jul.pdf` is linked but returns 404, and OCR cannot read the total cell in `2026-Rates-Aug.pdf`. Both months still have totals from the summary table, without generation. Each run reports these two and ends as `failed`.
- The WordPress API (`/wp-json/wp/v2/`) lists uploaded files with upload dates (`media`) and news posts (`posts`). Posts titled `BILLING RATE FOR <MONTH YEAR>` (29, from 2024-02) are free text or images, not tables, so they are not a structured source and are not used. The December 2025 post quotes an announced rate of 13.3940 per kWh and a generation charge of 7.2147 (matching the OCR value) while the summary table gives 12.4308 for that month, which suggests the table excludes VAT. Seen in one month only.
- **Generation charge is blank for most CAPELCO months.** It exists only in each month's scanned PDF, and only the 12 newest PDFs are OCRed, which gave 10 months (2025-10 to 2026-06 and 2026-09). The other 95 months (2018-01 to 2026-08) have a total from the summary table and no generation. OCRing the older PDFs works (2018, 2024 and 2025 samples parsed) but takes about 25-50 s per PDF; raise `MAX_MONTHS` in `collectors/capelco.py` and re-collect to fill more, after clearing the CAPELCO rows so the table-only rows are not stored beside the new ones.
- `robots.txt` returns 404.

## Cross-source

- "Rate per kWh" is not defined identically across utilities. Meralco's overall rate is all-in (generation through taxes, at 200 kWh). CAPELCO's printed total equals the sum of its per-kWh component lines, with VAT shown as separate memo rows below it, so it appears to be pre-VAT (inferred, not stated). BENECO's total includes VAT components and appears to be all-in. Do not rank utilities by this column without checking the definitions.
- `rate_basis = summed_components` is reserved for sources that publish components only; no current source needs it.
- Rates are billed in month M using costs from month M-1; `period` is the billing month.
