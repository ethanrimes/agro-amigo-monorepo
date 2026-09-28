# Recurring source ingestion

This Azure Functions service discovers official agricultural publications, retains original bytes, extracts typed observations and updates application projections. Current sources and historical backlog share durable queues and bounded execution.

## Structure

| Module | Responsibility |
|---|---|
| [function_app.py](function_app.py) | Timers, authenticated entry points and health reporting |
| [worker.py](worker.py), [queue_plan.py](queue_plan.py) | Discovery, parser versions, queue eligibility and execution budgets |
| [resumable_inputs.py](resumable_inputs.py), [retained_replays.py](retained_replays.py) | Durable batches and retained-original replay |
| [official_sources.py](official_sources.py) | Official reference validation and publication |
| [official_catalog.py](official_catalog.py) | Current eligible reference read model |
| [ocr.py](ocr.py) | Images, independent readings and typed fallback dispatch |
| [schema.sql](schema.sql), [migrations](migrations) | Source, queue, checkpoint and publication structures |

A shared advisory lock serializes writers. Deadlines defer remaining work without declaring incomplete originals complete. Checkpoints commit with the corresponding publication work so subsequent runs can resume. Parser/publication versions determine whether an older result is eligible for replay.

## Source families

| Family | Native path and meaning |
|---|---|
| DANE daily/monthly | Workbook and supported PDF monetary tables; reporting dates and units remain explicit |
| City ZIP/PDF | Per-member dates, market, classification, package and price rounds |
| DANE weekly | Native PDF/XLS/XLSX weekly means and ranges, distinct from daily/monthly series |
| Inputs | Department/municipality commercial identities, plus separately typed ancillary tables |
| Milk/rice | Municipal farmgate milk and mill rice prices with appropriate units |
| Milk macroregions | Separate monthly chart means; not municipality observations |
| Supply | Streaming workbook rows grouped by food, market and month with exact source-row ranges |
| FNC | Coffee reference history, factors, branch values and source-specific supplementary series |
| Colombian/international references | Publisher adapters preserving currency, unit, market, period and price basis |

See [source semantics](../../docs/DATA_SOURCES.md), [Colombian references](../../docs/OFFICIAL_COLOMBIA_SOURCES.md) and [international references](../../docs/OFFICIAL_INTERNATIONAL_SOURCES.md).

## Original evidence and publication

A changed file at the same URL creates a new SHA-256 original. Raw observations and old parser versions stay retained. Source locators identify workbook sheets/rows or PDF pages/rows. Alternative files and historical-query responses preserve their own identity and parent relationships rather than impersonating a missing original.

Publication validates source dates, identities, positive price cells and units. Reviews can coexist with valid sibling rows. Source chronology and family-specific precedence prevent an older replay from replacing a newer eligible observation. A source-matching whole-peso PDF input value does not discard the precision of its structured annex; materially conflicting values are not labelled as rounding differences.

Original storage, parsing, projection and current-catalog refresh are distinct stages. Official quote/review changes mark affected catalog keys dirty; bounded refresh rebuilds eligible latest/previous values. The frontend reads that current model while historical quotations remain available.

## Native extraction and OCR

Native cells or PDF text/geometry are tried first. Supported failed layouts select required images, retain two independent readings and pass them through a typed parser before publication. Source dates, units, original locators and uncertainty remain mandatory.

Daily/monthly monetary PDFs, city PDFs, weekly PDFs, supported Pork reports, milk macroregion charts and certain workbook kinds have specific fallback paths. This does not imply universal OCR support. Scanned input PDFs and municipal milk PDFs lack a typed OCR price-publication path; image-only weekly workbooks remain unsupported. Generic images/readings can be retained without publishing prices. Decorative pages, narrative context and percentage-only tables are not monetary observations.

Milk publication coordinates municipal rows and macroregion charts independently. Chart observations retain their printed month, region and COP/litre basis; paired OCR reads literal labels rather than estimating bar heights. Bulletin-period precedence preserves revised chart observations without erasing old originals.

## Development entry points

Use Python 3.11 or later and install the service dependencies from the repository root:

```sh
python3 -m venv .venv
.venv/bin/pip install -r pipelines/ingestion/requirements.txt
```

Adapters can be exercised locally with original fixtures. Database publication requires a configured restricted writer; deployment is implemented by [deploy_ingestion.py](../../infra/deploy_ingestion.py). Secrets and cached originals remain outside Git. Runtime schedules and provider limits are supplied through configuration.

For application query and UI paths, see [code navigation](../../docs/CODE_NAVIGATION.md).
