# Recurring source ingestion

This Azure Functions service discovers official agricultural publications, retains original bytes, extracts typed observations and updates application projections. Current sources and historical backlog share durable queues and bounded execution.

## Structure

| Module | Responsibility |
|---|---|
| [function_app.py](function_app.py) | Timers, authenticated entry points and health reporting |
| [worker.py](worker.py), [queue_plan.py](queue_plan.py) | Discovery, parser versions, queue eligibility and execution budgets |
| [resumable_inputs.py](resumable_inputs.py), [retained_replays.py](retained_replays.py) | Durable batches and retained-original replay |
| [daily_discovery.py](daily_discovery.py), [daily_archives.py](daily_archives.py) | Historical daily links and typed workbook members inside official annex ZIPs |
| [daily_publication.py](daily_publication.py) | Validated daily prices, native percentage formats and retained corrections |
| [supply_summaries.py](supply_summaries.py), [supply_period_summaries.py](supply_period_summaries.py) | Daily, monthly and first-fortnight market summaries, kept separate from food microdata |
| [official_sources.py](official_sources.py) | Official reference validation and publication |
| [official_catalog.py](official_catalog.py) | Current eligible reference read model |
| [label_normalization.py](label_normalization.py), [shared lexicon](../../shared/label-normalization.json) | Reviewed spelling, accents and casing; bounded metadata cleanup and retained correction evidence |
| [ocr.py](ocr.py) | Images, independent readings and typed fallback dispatch |
| [schema.sql](schema.sql), [migrations](migrations) | Source, queue, checkpoint and publication structures |

A shared advisory lock serializes writers. Deadlines defer remaining work without declaring incomplete originals complete. Checkpoints commit with the corresponding publication work so subsequent runs can resume. Parser/publication versions determine whether an older result is eligible for replay.

## Source families

| Family | Native path and meaning |
|---|---|
| DANE daily/monthly | Workbook and supported PDF monetary tables; reporting dates and units remain explicit |
| City ZIP/PDF | Per-member dates, market, classification, package and price rounds |
| Daily annex ZIP | Original XLS/XLSX members: package ranges, daily matrices, individually dated published means and separate supply references |
| DANE weekly | Native PDF/XLS/XLSX weekly means and ranges, distinct from daily/monthly series |
| Inputs | Department/municipality commercial identities, plus separately typed ancillary tables |
| Milk/rice | Municipal farmgate milk and mill rice prices with appropriate units |
| Milk macroregions | Separate monthly chart means; not municipality observations |
| Supply | Streaming workbook rows grouped by food, market and month with exact source-row ranges |
| Supply summaries | Daily, monthly and first-fortnight market/group totals, shares and changes; precise workbook values and rounded PDF values keep their distinct originals |
| FNC | Coffee reference history, factors, branch values and source-specific supplementary series |
| Colombian/international references | Publisher adapters preserving currency, unit, market, period and price basis |

See [source semantics](../../docs/DATA_SOURCES.md), [Colombian references](../../docs/OFFICIAL_COLOMBIA_SOURCES.md) and [international references](../../docs/OFFICIAL_INTERNATIONAL_SOURCES.md).

## Original evidence and publication

A changed file at the same URL creates a new SHA-256 original. Raw observations and old parser versions stay retained. Source locators identify workbook sheets/rows or PDF pages/rows. Alternative files and historical-query responses preserve their own identity and parent relationships rather than impersonating a missing original.

Publication validates source dates, identities, positive price cells and units. Reviews can coexist with valid sibling rows. Contradictory input PDF continuation headings preserve their literal values for review without guessing a product or presentation. Source chronology and family-specific precedence prevent an older replay from replacing a newer eligible observation. A source-matching whole-peso PDF input value does not discard the precision of its structured annex; materially conflicting values are not labelled as rounding differences.

City report publication compares every stored price field, source locator and classification against the complete native PDF. A disagreement keeps the affected original available for consultation while withholding that PDF’s prices pending review. Each ZIP member is processed independently: a malformed file or an HTML error page named as a PDF is retained for review without preventing valid sibling reports from being published. Report rounds and package quantities remain explicit; the application uses the latest available round for the selected market, package and date.

Daily workbook variation uses the native cell format to distinguish a stored fraction from percentage points. A printed average remains the published average, rather than a midpoint calculated from its range. Supply summary totals are separately typed references and never added to the food-level microdata totals or published as prices.

Original storage, parsing, projection and current-catalog refresh are distinct stages. Official quote/review changes mark affected catalog keys dirty; the catalog drain refreshes at most twelve 100-key chunks or twenty seconds per stage, checking the deadline between chunks and pacing committed chunks for active readers. A SQL statement already running can exceed the time window, subject to its existing statement timeout. The summary reports processed work and whether more may remain, without changing the existing source and winner checks. The frontend reads the current model while historical quotations remain available.

Published labels use a shared, versioned lexicon grounded in the native DANE product selector and source classifications. Cleanup composes Unicode accents, removes formatting characters, collapses whitespace and standardizes recognized full labels. Input commercial names receive formatting cleanup only; brands, ICA registrations, formulations, quantities and varieties keep their identity. Unknown spellings remain literal rather than being matched by similarity.

Daily refresh and historical backfill automatically scan existing product metadata before and after publication using a bounded, durable cursor. Each metadata change commits with append-only evidence containing its previous label, corrected label and lexicon hash. The cursor and audit also identify the cleanup-rule version, so a rule upgrade rechecks existing labels while retaining earlier correction evidence. Original observations, files, IDs, prices, dates and source locators remain retained. Identity-changing PDF spacing and line-wrap repairs require native geometry or official geographic agreement in the source adapter; a display dictionary alone cannot merge products or markets.

The archived city-PDF scan reserves a small part of each batch for exact recognized food names whose words may have been joined during extraction. It selects these documents through indexed product/source identities while retaining the ordinary historical queue. Priority selection is only a review cue: publication still requires the retained original and a complete native comparison showing that only the supported name/identity changes. Prices, packages, dates and source row locators must agree. Completed reviews and retry cooldowns remain effective.

## Native extraction and OCR

Native cells or PDF text/geometry are tried first. Supported failed layouts select required images, retain two independent readings and pass them through a typed parser before publication. Source dates, units, original locators and uncertainty remain mandatory.

Weekly native geometry separates tightly printed mean and tendency columns and keeps unavailable market rows as explicit reviews. Printed dots, dash cells and missing-price zero means never become monetary quotes or attach a market name to the following market's price. A versioned repair can replay an exact registered native-readable original previously left in the OCR queue. Independently reviewed decorative page tasks can be retired only for their registered original bytes, URL, source kind and page; that review does not complete or certify the parent document.

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
