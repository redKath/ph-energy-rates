# Adding a utility

A utility is one module in `src/ph_energy_data/collectors/`. Nothing else needs editing: collectors are discovered automatically.

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

    def discover(self, fetcher: Fetcher) -> list[str]:
        """URLs of the documents to collect (one page, or links scraped from a listing)."""

    def extract(self, document: FetchedDocument) -> list[ExtractedRate]:
        """Candidate rates. Raise ValueError if the layout is not recognised."""


collector = MyCollector()
```

- `id` is a lowercase slug and never changes.
- Use the fetcher passed in; it sends the user agent, honours robots.txt and rate-limits.
- Build rates with the right `extraction_method` and `rate_basis`.
- Raise `ValueError` for anything unexpected. A document that raises is skipped and reported; the rest of the run continues.
- Parse by label, not by position, and add a cross-check where the document has redundancy (a total that equals a sum, a value printed twice).
- For scanned PDFs keep OCR in `extraction/` and the table parsing in a pure function so tests can use saved OCR output.

## 3. Test

- Parser tests on saved fixtures: expected values, plus a case where the layout is wrong and it must raise.
- `discover` against a saved listing page using `FakeFetcher` from `tests/conftest.py`.
- Tests never use the network, OCR or an LLM.

## 4. Run

```
uv run ruff check . && uv run ruff format . && uv run mypy && uv run pytest
uv run ph-energy collect my-utility
```

Then check the rates in `/docs` against the source by eye, and add what you learned to `data-gotchas.md`.
