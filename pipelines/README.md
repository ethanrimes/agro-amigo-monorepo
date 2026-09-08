# Azure data pipeline

The [permanent Azure ingestion service](ingestion/README.md) runs daily refreshes and an hourly historical backfill. Historical records and source originals are never deleted. Use that service for unattended updates; the commands below remain manual reference importers.

These importers replace the retired Supabase pipeline. Use Python 3.11+ and the owner-only `.azure-local/database.json` produced by `infra/provision.py`. Network access to the Azure PostgreSQL firewall and official data hosts is required.

```sh
python3 -m venv .venv
.venv/bin/pip install -r pipelines/requirements.txt
.venv/bin/python pipelines/demo/import_data.py
.venv/bin/python pipelines/planning/fetch_references.py
.venv/bin/python pipelines/planning/import_references.py
.venv/bin/python pipelines/planning/import_costs.py
.venv/bin/python pipelines/planning/import_daily.py 2026-09-04
.venv/bin/python pipelines/planning/methodology.py
.venv/bin/python pipelines/demo/verify_database.py
.venv/bin/python pipelines/planning/verify.py
```

Run from the repository root. The demo importer creates `apps/web/.env.local` using the restricted application account. Repeat the initial importer with `--cached` for an idempotency check before running `demo/verify_database.py`.

## Reproducible source snapshots

`planning/reference-downloads.json` records the checked reference URLs, including EVA/calendar snapshots, costs, daily bulletin and input history. `fetch_references.py` downloads these, retrieves SIPRA municipal statistics in department batches, and retrieves the public soil sample fields. Cached responses and a complete URL manifest live under `planning/cache`; the import archives used files in Azure with SHA-256 identifiers. Caches are not committed.

The daily importer takes an ISO date and expects corresponding `daily-YYYY-MM-DD.xlsx` and `.pdf` files in its cache. It deliberately keeps the bulletin's predominant-variety names separate from the monthly price series. Download both official files and extend the manifest before importing a different day. The current demo explicitly uses 2026-09-04.

`import_references.py --prices-only` refreshes the price evidence and seasonal series; `--farms-only` refreshes municipal references. `import_costs.py --publications-only` updates document/advisory references without rereading the large input workbook. Review official source schemas and reference years before adopting newer publications. A source that disappears or changes schema must fail visibly; don't substitute invented observations.

## Retention and traceability

- Historical observations are retained permanently. Public queries use `(today in America/Bogota minus 12 months, today]`; database guards reject only future observations. Imports never prune old records.
- `seasonal_year` retains complete historical calendar years by product and market; planning queries select the five complete prior years. It stores all 12 original monthly values and source row locators. Four conflicting DANE market-years are explicitly excluded in `seasonality-exclusions.json`.
- EVA 2025, calendars 2024, UPRA cost publications and other older references are reference data, not current quotes. Their publication periods remain visible.
- Source originals, generated price extracts and methodology PDFs are stored in `source_document.content` (PostgreSQL `bytea`). A SHA-256 key identifies immutable bytes; aliases point to current versions. Exact observation links use hashes.
- Updating data and regenerating evidence are one refresh workflow. Do not publish a price update while leaving its previous document attached.
- The application can read public data and append public forecast snapshots. It cannot edit prices, reference documents, or publish buyer offers.

## Adding crops and models

Maintain physical state, variety, region, season, units and reference year. Paddy is not milled rice; cane is not panela; coffee cherry is not parchment. Cost templates must reconcile to the source's total and preserve whether the model covers a cycle, a producing year or establishment. Multi-year cost studies are archived without flattening them into one-year budgets. Soil sample aggregates are regional context only.

The Azure ingestion service refreshes official prices, exchange rates, inputs and supply data on a schedule. Older agronomic publications still require schema and methodology review through the manual reference importers; weather is requested and cached when a user opens their farm. Model assumptions live in `apps/web/src/lib/planning-math.ts`, `CropBudget.tsx`, and the archived methodology PDF.

## Spanish-language news research

The separate [news collector](news/README.md) discovers Spanish articles from a diverse Colombian and international catalog, preserves publication evidence and a durable backlog, and accepts reviewed category/relevance/expiry decisions. It does not modify official price observations or publish news to the app. Its subscription-funded daily Luna cloud task is prepared but not scheduled; see [activation status](../docs/automation/README.md).
