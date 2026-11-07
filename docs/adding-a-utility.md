# Adding a utility

A utility is one module in `src/ph_energy_data/collectors/` plus one line in `collectors/registry.py`.

## 1. Research the source

- Find where the utility publishes monthly residential rates and what format it is (HTML table, text PDF, scanned PDF).
- Check `robots.txt` and the site terms.
- Note quirks in [data-gotchas.md](data-gotchas.md): what the figure includes, how periods are named, which files are duplicates.
- Save one real document as a test fixture under `tests/fixtures/<utility>/`.

## 2. Write the collector

Create `collectors/<utility_id>.py`:

```python
class MyCollector(Collector):
    utility = Utility(id="my-utility", name="...", type=UtilityType.ELECTRIC_COOPERATIVE)

    def discover(self, fetcher: Fetcher) -> Discovery:
        """URLs of the documents to collect (one page, or links scraped from a listing)."""

    def extract(
        self, document: FetchedDocument, reference_totals: ReferenceTotals
    ) -> list[ExtractedRate]:
        """Candidate rates. Raise ExtractionError if the layout is not recognised."""
```

Then add `MyCollector()` to the list in `build_collectors()` in `collectors/registry.py`.

- `id` is a lowercase slug and never changes.
- Use the fetcher passed in; it sends the user agent, honours robots.txt and rate-limits.
- Build rates with the right `extraction_method` and `rate_basis`.
- Raise `ExtractionError` for anything unexpected, including a number that does not parse. A document that raises is skipped and reported; the rest of the run continues.
- Parse by label, not by position, and add a cross-check where the document has redundancy (a total that equals a sum, a value printed twice).
- `Discovery.reference_totals` carries totals published elsewhere (by `YYYY-MM`) for `extract` to cross-check. Pass an empty mapping if there are none.
- For scanned PDFs keep OCR in `extraction/` and the table parsing in a pure function so tests can use saved OCR output. Pass the OCR object into the collector's constructor so tests can supply a fake.

## 3. Test

- Parser tests on saved fixtures: expected values, plus a test for every `ExtractionError` the parser can raise.
- `discover` against a saved listing page using `FakeFetcher` from `tests/conftest.py`.
- Tests never use the network, OCR or an LLM.

## 4. Run

```
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
uv run ph-energy collect my-utility
```

Then check the rates in `/docs` against the source by eye, and add what you learned to `data-gotchas.md`.
