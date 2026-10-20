# PH Energy Rates

Open dataset answering one question: **how much does each Philippine electricity utility charge per kWh, month by month?**

The ~142 distribution utilities and electric cooperatives publish rates as web tables, scanned PDFs and Facebook posts, and no agency list shares an ID. This prototype collects, validates and serves rates for three utilities with three different source formats. Every rate links back to the raw document it came from (URL, fetch time, SHA-256, archived copy).

Code is MIT-licensed. The data is intended to be released under CC BY 4.0.

## Current coverage

| Utility | Source format | Method | Months |
|---|---|---|---|
| BENECO | HTML fragments | HTML parser, components cross-checked against the total | 2024-12 to 2026-09 (16 months; 7 rejected, see data gotchas) |
| Meralco | Text PDF | PDF parser, cross-checked against the bill table | 2025-11 to 2026-10 |
| CAPELCO | HTML summary table + scanned PDFs | Totals from the table; Docling OCR adds generation for the latest 12 months, and must match the table | 2018-01 to 2026-09 (105 months; generation for 10) |

Read [Data gotchas](docs/data-gotchas.md) before comparing utilities: the "rate per kWh" is not defined identically across sources.

## Quickstart

Needs Python 3.12+, [uv](https://docs.astral.sh/uv/) and PostgreSQL 16+ (developed on 18).

```
uv sync                       # add --extra ocr for scanned PDFs (large: PyTorch + models)
cp .env.example .env          # set PH_ENERGY_DATABASE_URL if your Postgres differs
docker compose up -d db       # Postgres 16 on 127.0.0.1:5432, or use any Postgres
uv run alembic upgrade head
uv run ph-energy collect beneco
uv run ph-energy collect meralco
uv run ph-energy collect capelco   # needs --extra ocr; about 25 s per PDF
uv run ph-energy serve
```

Open http://127.0.0.1:8000/docs for the interactive API.

Use `127.0.0.1` rather than `localhost` in the database URL: on Windows, Docker's IPv6 forwarding can make `localhost` connections stall for minutes.

| Endpoint | |
|---|---|
| `GET /v1/utilities`, `/v1/utilities/{id}` | Filter by `type`, `province` (PSGC prefix) |
| `GET /v1/rates` | `utility_id`, `from`, `to` (`YYYY-MM`), `status`, `limit`, `offset` |
| `GET /v1/rates/{id}` | Includes the source document (URL, fetch time, SHA-256) |
| `GET /v1/exports/rates.csv`, `.json` | Published rates with provenance |
| `GET /health` | |

## Development

```
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest        # no network, no OCR, no LLM
```

- [Data dictionary](docs/data-dictionary.md)
- [Adding a utility](docs/adding-a-utility.md)
- [Architecture decisions](docs/adr)
- [Scanner caveats](docs/scanner-caveats.md)

## Limitations

- Residential customers only; three utilities; about a year of history each.
- The `docker compose` database was tested (migration, collection, API) only on Docker Desktop for Windows.
- Older source documents were sampled, not checked. A document whose layout the parser rejects is skipped and reported in the run.
- CAPELCO generation charge is filled for only 10 of 105 months (see [data gotchas](docs/data-gotchas.md)); the rest have totals only.
- If a source revises a month, both values are stored; the API does not yet pick a latest one.
- No authentication or rate limiting on the API.

## Future work

- LLM fallback extractor (behind the same extractor interface) for scans the table parser rejects, with recorded responses in tests.
- Source configuration files for common patterns (listing page to PDFs) so most utilities need no Python.
- Facebook-only utilities via a validated manual-entry path (`extraction_method = manual`).
- PSGC codes and ERC/NEA IDs for utilities; province filtering depends on them.
- Component-level rates (generation, transmission, distribution, taxes) in a separate table.
- Scheduled collection, and an MCP server over the service layer.

## About

This project was started as a prototype for the [BetterGovPH Fellowship 2026](https://fellowship.bettergov.ph/) Energy challenge (one open energy data layer for the Philippines). It is an independent project and is not affiliated with or endorsed by BetterGovPH, DOE, or any government agency.
