# Permanent Azure data ingestion

The Python Azure Functions app `agroamigo-data-9a04` runs in subscription
`9a04b64b-af19-4519-be50-56ec2acbd855`, resource group `agroamigo-demo-rg`.
It shares the existing Linux App Service plan and writes to the existing
`agroamigo` PostgreSQL database as the restricted `agro_ingestor` role.
For the path from a source adapter to its API and screen, see
[code navigation](../../docs/CODE_NAVIGATION.md).

- `DailyRefresh`: every day at **18:00 Colombia**, `0 0 23 * * *` UTC. Discovers
  official publications, refreshes current/previous-year DANE monthly prices and
  supply microdata, recent daily bulletins, FNC reference/factors/branches,
  agricultural input history, TRM, complete-year seasonal series, and registered
  official Colombian/international source roots. Schedules are remote Azure
  settings; `function_app.py` reads `DAILY_SCHEDULE` / `BACKFILL_SCHEDULE`.
- `HistoricalBackfill`: every hour at minute 15 UTC. Processes up to 100 queued
  assets and resumes from database checkpoints. A run stops starting new assets
  after 35 minutes. The Functions execution timeout is 45 minutes. Seasonal
  refresh has its own five-minute budget so it yields to fresh source files.
  Budget checks occur between atomic batches; an executing SQL statement still
  has the normal statement timeout.
  `queue_plan.py` gives each source kind its own slot, so archive indexes cannot
  starve PDF/workbook leaves. Fresh official files with an unknown observation
  date receive a bounded daily slot; parsing records their actual latest date.
  Discovery is retried by the hourly job when its last recorded completion is
  more than six hours old, independently of the nightly trigger. Discovery and
  historical loading are ongoing: a URL in the queue is not evidence that all its
  observations are already available in the app.
- `OcrRecovery`: every hour at minute 05 UTC. Resumes at most two image tasks
  under the same import lock and daily provider-request allowance. A separate
  timer prevents large native workbooks from consuming every recovery window.
- `PipelineWatchdog`: every hour at minute 45 UTC. Checks completed-run and
  discovery freshness, stalled runs and overdue recent sources; database
  connectivity alone does not establish that ingestion is healthy.
- A PostgreSQL advisory lock prevents concurrent imports; overlap attempts and
  progress heartbeats are recorded. Source-specific failures do not restart the
  whole daily run. Fatal invocation failures retain Azure's two five-minute
  retries; failed assets become eligible again after six hours. Database
  statements time out after five minutes, lock waits after ten seconds, and idle
  transactions after three minutes. Failed schemas remain visible with originals
  retained. Current sources and historical backfill have separate queue slots.
- A publisher workbook whose internal date disagrees with its link is retained
  with `status='review'`. Its prices are not assigned to an unverified date;
  reviewed originals can be explicitly requeued if the publisher corrects them.
- Sources are discovered from official links. Daily workbooks must contain a date
  matching their link. Missing days are not interpolated. Daily PDFs and Excel
  files are both archived and parsed where their layouts are supported; an
  available workbook has precedence when publishing the same daily quote.
  City ZIPs retain the ZIP and each PDF separately. Unsupported layouts and
  ambiguous source values remain visible for review.

## Source responsibilities

| Module | Sources / output |
| --- | --- |
| `worker.py` | DANE monthly/daily workbooks and PDFs, FNC, HTTP conditional requests, source archival, row persistence and application projections. |
| `inputs.py`, `input_references.py`, `pdf_sources.py` | Department and municipality input prices, input PDF grids, summaries and ancillary production-factor annexes. Non-price context remains reference data. |
| `city_reports.py` | All discovered informes por ciudades ZIPs, individual PDF members, source package/quantity/unit, rounds and category paths. |
| `dane_weekly.py` | Weekly SIPSA PDF/XLS/XLSX quotations, printed weekly min/max/mean and explicit units; separate official quote identities and review records. |
| `special_prices.py` | DANE raw milk at farm and rice/mill byproducts, with distinct physical products and price bases. |
| [`milk_macroregions.py`](milk_macroregions.py), [`milk_publication.py`](milk_publication.py) | Native milk-chart labels or narrowly targeted paired OCR; five named macroregions, printed observation months, independent municipal/chart completion and review handling. |
| `supply.py` | Full-source validation and resumable 250-identity batches of reported arrivals, newest month first. |
| `colombia_sources.py` | AgroNET cacao, Fedepalma statutory palm references, Fedegán cattle/milk, Porkcolombia and Corabastos. |
| `international_sources.py` | World Bank commodity benchmarks and USDA published flower market reports. |
| `official_sources.py` | Trusted adapter dispatch, child discovery, quote validation, separate official-price revisions/reviews and OCR publication bridge. |
| `official_catalog.py` | Persistent current official quotes, review invalidation, bounded recovery and resumable initial bootstrap; keeps full-history work out of frontend requests. |
| `resumable_inputs.py` | Full native validation, bounded source-row and exact-identity publication batches, with durable month/source completion checkpoints. |
| `retained_replays.py` | Bounded replay of superseded official originals after parser upgrades without changing the current URL pointer. |
| `audit_automation.py` | Read-only execution, source queue, retention, overlap and OCR diagnostics. |
| `ocr.py` | Detect failed native extraction, persist images, compare independent Gemini readings and publish only recognized literal layouts. |
| `workbook_preview.py` | Read-only paginated original Excel display for the app's source viewer. |

See [official Colombian sources](../../docs/OFFICIAL_COLOMBIA_SOURCES.md) and
[official international sources](../../docs/OFFICIAL_INTERNATIONAL_SOURCES.md)
for original URLs, verified formats, historical limits and price semantics.
International benchmarks, statutory references, wholesale packages, live animals,
carcasses and farm prices are separate series. Their original currencies and units
are not silently converted into one Colombian wholesale price.

### Weekly SIPSA bulletins

`dane-weekly-index`, `dane-weekly-pdf` and `dane-weekly-xlsx` use the trusted
`official_sources.py` path. The observed inventory contains 1,453 files across
16 current/year indexes back to June 2012. Current/previous-year indexes and
recent 70-day leaves are rechecked; undated leaves receive bounded daily slots
and ordinary backfill. An unchanged URL with new bytes creates a new immutable
original and quote revision. PDF and Excel source viewers retain exact document
IDs and page or worksheet/row locators.

Quotes preserve the printed weekly minimum, maximum and **mean**, explicit
period, currency, unit and literal product/market. They are not daily prices or
computed midpoints. Missing unit declarations and conflicting product blocks
remain `official_source_review` evidence. Native extraction precedes PDF OCR;
only failed pages enter the cached-reading bridge. Image-only weekly workbooks
remain explicit layout review because the legacy workbook OCR publisher cannot
safely supply weekly period/basis semantics.

The [DANE source coverage audit](../../docs/DANE_SOURCE_COVERAGE_2026-09-27.md)
records 12-original native stress, current full-cell reconciliation, historical
visual checks and limits. It distinguishes registered links and locally validated
rows from cloud publication. Run focused checks with
`.venv/bin/python -m unittest pipelines.ingestion.test_dane_weekly pipelines.ingestion.test_dane_weekly_wiring`;
real-original and PostgreSQL fixtures require their documented local setup.

## File changes, checkpoints and OCR

`ingestion_asset` tracks one public URL. `fetch_asset` sends `If-None-Match` or
`If-Modified-Since` for previously successful files. A `304` advances the check
timestamp; a `200` hashes the actual bytes. New bytes are archived under a new
SHA-256 document ID before parsing. The current asset pointer may advance while
old originals and observations remain retained. Child discovery is recursive for
official report collections, attachments and archive pagination.

`worker.parser_version(kind)` identifies the expected processor. An outdated
selected asset bypasses HTTP validators so a publisher `304` cannot prevent a
parser repair. Check both the scheduler and parser revision identity when adding
a format: successful deployment alone does not mean an older completed asset was
selected for reprocessing. Use queue diagnostics below to verify progress. Recent
files and mutable reference roots need frequent revalidation; older successful
assets also receive a 30-day revalidation opportunity through backfill. Completed
assets with outdated processors are eligible immediately; stale review files are
rechecked after 30 days in case their publisher corrects them. Daily processing
reselects once after source roots, allowing newly linked files into the same run.
Discovery errors are isolated by source family and reported without abandoning
unrelated queued work.

Expected deadline deferrals keep their checkpoints and are eligible for the next
automatic invocation. They do not inherit the six-hour cooldown used for source
errors. The per-run processed set still prevents retrying the same URL twice.

FNC workbooks and PDFs are also evaluated once per Colombia calendar day. An
unchanged original can contain a price that becomes eligible tomorrow. An
`as-of:YYYY-MM-DD` checkpoint is written only after successful publication; HTTP
checks still detect a changed file later on the same day.

Current and previous-year annual milk workbooks are revalidated even when their
last imported observation is older than the recent monthly-file window. DANE
updates these URLs in place; an old observation date does not mean an old file.

Large input workbooks validate fully before committing native observations in
25,000-row batches. Each month is staged once, newest month first, then published
in batches of 250 exact input/location/date identities. Duplicate source rows
for an identity stay together; conflicting prices remain withheld. Each batch
and its checkpoint commit together. The month/source completion marker waits
until every group completes. A time-limited run resumes the exact original
before checking that mutable URL again. An unchanged business price keeps its
existing valid evidence; a newer corrected value retains both original versions.
Successful native publication closes only pending/deferred OCR tasks for that
document and source kind. Existing OCR readings and review decisions remain.

Input publication preserves structured-annex decimals when the same exact
observation is printed as a rounded whole-peso PDF value. This exception requires
matching identity, location, month and product metadata plus verified native
source rows; a filename is insufficient. A rounded duplicate cannot advance the
structured value's freshness watermark. Materially different prices retain the
normal revision rules and are not treated as rounding. `inputs.PUBLICATION_VERSION`
is part of the structured input processor identity, so completed workbooks resume
with new publication checkpoints after a repair. Raw rows and original files stay
immutable. See [`test_input_rounding_priority.py`](test_input_rounding_priority.py)
for rounding, conflicting-value, watermark and resumable-publication cases.

Supply validates the entire native workbook before publishing any values. It then
commits at most 250 complete market/food/month identities with each checkpoint,
newest month first. Reporting days, quantities and exact source rows stay together.
A pending validated source resumes its retained original; only all completed
batches permit `supply:complete`. Unchanged and stale values are excluded before
INSERT, while equal-valued newer revisions still advance provenance safely.

The bounded retained-original pass recovers older official reports overwritten
at a publisher URL. It processes at most two originals per recurring run, with
versioned completion/review checkpoints and retry cooldowns.

OCR runs only after normal extraction fails. PDFs with native headings but image
price tables are supported where the adapter can identify the required pages.
City reports and supported daily/monthly price matrices check actual parsed price
rows on each page. A readable title is insufficient when its price table is an
image. Only failed pages with a substantial image are added to this fallback;
readable price pages and small logos stay on native extraction. City OCR rebuilds
the complete document so continuation tables inherit its verified date, market
and preceding classification, while retaining their original page numbers.
Queued DANE daily/monthly pages recheck the same native-failure predicate before
using cached readings or calling Gemini. Obsolete decorative/non-price pages move
to review with an explicit no-OCR-needed reason; their original evidence stays.
Spreadsheet embedded images / failed native cells use the same persistent OCR
queue. `source_ocr_task` records pending, deferred, verified, published or review
work; two independent literal readings must agree. The daily request allowance is
shared by worker runs and recorded in `source_ocr_attempt`. An unsupported or
uncertain transcription does not become a price. Original documents, rendered
images and both readings remain available as evidence.

Milk cover charts are separate from municipal tables. The parser binds native
numeric labels to named regions using the actual legend and label geometry; it
never estimates prices from bar heights. When those labels are raster-only, just
the recognized chart is rendered and two complete readings must agree on all
five regions and both printed months. A municipal success does not imply chart
success, or vice versa. Each quote preserves its observation month and validated
bulletin month. Repeated observations prefer the later bulletin, then the newer
retained revision of that bulletin, regardless of backfill download order.
[`test_milk_publication.py`](test_milk_publication.py) covers independent completion
and withdrawal; [`test_milk_bulletin_precedence.py`](test_milk_bulletin_precedence.py)
covers matching current-cache and historical-view selection.

Workbook OCR inspection streams worksheet XML and stops immediately when native
cells are readable. It never materializes a 400 MB worksheet merely to look for
images. Supply parsing also releases row formatting/XML nodes as it streams,
and holds exact source row ranges in packed integers until each group is copied.
It reuses openpyxl's cell/date decoder, so the worker pins openpyxl 3.1.5; upgrades
must pass the full source/provenance regression before changing that pin.

## Permanent retention

No historical data is pruned. Many public app queries default to a recent 12-month
view; supported history filters and official reference histories can request older
observations. The stored records retain older dates. Planning selects the five most recent
complete years from a permanently retained seasonal table.

`source_document` stores immutable source bytes keyed by SHA-256. The private
`source-archive` container in `agroamigodata9a04` also holds downloaded originals
under SHA-256 filenames. There is no expiration lifecycle policy.
PostgreSQL storage autogrow is enabled; the audited allocation on 26 September
2026 is 64 GiB.
Additional capacity can increase storage charges as the permanent archive grows.

`historical_price` preserves source-level observations, original product/market
names, units, exact row/cell/page locators and revisions. Conflicting source rows
are retained; conflicting product/market/month keys are excluded from publication.
Daily predominant-variety bulletins and annual named-variety series remain distinct.
`retained_record` preserves versions of application observations and planning
references. Database triggers reject deletion/truncation of historical stores and
updates to immutable stores. The worker has no DELETE, TRUNCATE or DDL privileges.

`official_price_quote` and `official_source_review` retain separate official-source
results. `published_official_price` chooses the latest valid dated quote for an
exact identity that includes product, series, market, currency, unit, basis and
additional source dimensions. `published_price_observation` and the published
input views keep invalidated data out of current app results while preserving its
original evidence. `regional_price` / `regional_classification` retain package and
classification details from the city PDFs.

The official SIPSA daily archive starts on **12 June 2012**, monthly bulletin
publication starts in July 2012, and the consolidated monthly workbooks start in
2013. The FNC workbook includes daily national reference prices from 2003. TRM
has a separate longer history. These are different series and units.

## Milk municipal tables and macroregional charts

`special_prices.py` reads municipal milk tables; `milk_macroregions.py` reads
the separately labeled five-region chart. `milk_publication.py` coordinates their
publication without treating a regional average as a municipality. The chart
series is `dane-milk-macroregion`, denominated in COP per litre, with the printed
month, region, monthly mean basis and original PDF page attached to each quote.

Native tables and vector chart labels take precedence. Vector labels are bound
to their region and month by their position and the printed legend colors;
bar height never supplies a price. A raster chart is queued only after native
extraction has failed for that chart. Two complete readings must agree on all
ten printed values and their month/region assignments. Missing labels, unit,
dates or uncertainty keep that chart under review. The original PDF, rendered
crop and provider readings are retained independently.

The milk worker version includes both municipal and macroregion parser versions,
so an upgrade makes previously processed originals eligible for the recurring
backfill. Municipal rows can remain published while a chart awaits OCR. Parent
record counts are recomputed from municipal completion and retained chart rows;
retries do not increment an old count. Archive/report date conflicts block chart
publication, including its prior-month column. A pending or reviewed chart is
not evidence that all of the PDF's price data has been extracted.

Focused tests are `test_milk_macroregions` (literal labels, native-first behavior,
OCR agreement and original-source parity) and `test_milk_publication` (publication,
checkpoint, status and replay behavior). Real-provider and app checks have their
own dated artifacts; passing mocked OCR tests alone does not validate a provider
response. The configured request allowance remains in force during audits.

## Run, deploy and inspect

```sh
.venv/bin/pip install -r pipelines/ingestion/requirements.txt
.venv/bin/python -m unittest pipelines.ingestion.test_worker pipelines.ingestion.test_pdf_layouts pipelines.ingestion.test_ocr pipelines.ingestion.test_colombia_sources pipelines.ingestion.test_international_sources pipelines.ingestion.test_runtime pipelines.ingestion.test_city_ocr_fallback pipelines.ingestion.test_special_layouts pipelines.ingestion.test_supply_layouts
.venv/bin/python -m pipelines.ingestion.stress_sources
```

These parser tests replay local fixtures without publishing prices. The stress
runner needs downloaded cache files; inspect skipped/missing fixtures when
interpreting coverage. Database integration and operational commands are separate:

```sh
.venv/bin/python -m pipelines.ingestion.verify_revision
.venv/bin/python -m pipelines.ingestion.verify_scheduler
.venv/bin/python infra/deploy_ingestion.py --database-only
.venv/bin/python -m pipelines.ingestion.worker discover
.venv/bin/python -m pipelines.ingestion.worker backfill --limit 100
.venv/bin/python -m pipelines.ingestion.worker daily
.venv/bin/python infra/deploy_ingestion.py
.venv/bin/python infra/deploy_ingestion.py --code-only
.venv/bin/python -m pipelines.ingestion.verify
.venv/bin/python -m pipelines.ingestion.verify_app
```

Local commands default to the owner-only `.azure-local/database.json`; cloud
runs receive `DATABASE_URL` and `AzureWebJobsStorage` through encrypted app
settings. `verify_revision` uses rolled-back database fixtures and a local HTTP
server to test changed bytes and `304` behavior; it does not upload artificial
fixtures to Blob. `verify` also performs controlled retention/date-guard probes.
Deployment installs Python 3.11 Linux wheels into `.python_packages`,
includes them in the ZIP, disables remote rebuilding, and mounts the complete
package with `WEBSITE_RUN_FROM_PACKAGE=1`. Always On is enabled so
Dedicated-plan timers work without web traffic. The database firewall allows
only the app's listed outbound IP addresses and existing approved clients.
Use `--code-only` for runtime updates when the schema and restricted role are
already current; this avoids unnecessary DDL locks. Apply actual schema changes
with `--database-only` or the full deployment. The deployer fingerprints the
packaged bytes and rejects source mutations during packaging or before upload.

Production settings are owned remotely. `infra/app_settings.py` fills missing
defaults while preserving operator-managed values. `GEMINI_API_KEY`,
`GEMINI_OCR_MODEL` and `GEMINI_OCR_DAILY_REQUESTS` belong only to the ingestion
environment. `SOURCE_STORAGE_ACCOUNT` configures the web app's managed-identity
Blob access; `SOURCE_WORKBOOK_API_URL` can select its read-only workbook service.
The server proxies originals and paginated workbook data to the app. Keys and
database URLs are never exposed as `NEXT_PUBLIC_*` values or included in ZIPs.

Inspect `ingestion_run` for start/end/status/summary, `ingestion_asset` for queue
progress and failures, and `historical_price` for coverage. The function-key
protected `GET /api/status` checks database connectivity and returns the exact
release, recent runs, queue and OCR counts. It does not scan historical price
tables during health polling. `?coverage=1` requests cached coverage with a
five-second database timeout; unavailable coverage is null. Protected
`POST /api/run-check` runs at most four queued assets, stops starting work after
two minutes and skips provider OCR requests, for bounded deployment validation.
For a registered `asset_url`, an explicit `time_budget` of up to 2100 seconds
allows validation of a large annual workbook through the same checkpoint path.
The HTTP caller can time out before that job finishes; use the durable run and
source-completion state to determine its outcome. Unscoped checks stay bounded
to 120 seconds, and provider OCR remains disabled for these checks.
Never put the function key in a committed file or public URL.

Connectivity and automation health are separate: `status.automation` is degraded
when no run has completed for three hours, discovery is over eight hours old,
a running job exceeds fifty minutes, or recent dated publications remain
unprocessed for more than a day. `PipelineWatchdog` checks this at minute 45
hourly and emits `INGESTION_AUTOMATION_DEGRADED` to Azure logs. This is a log
signal, not a configured email/SMS alert. Run a read-only audit with
`python -m pipelines.ingestion.audit_automation --output /tmp/agro-audit.json`;
`--since YYYY-MM-DD` narrows run history. The default is the last thirty days.
See the [September automation audit](../../docs/AUTOMATION_AUDIT_2026-09-26.md)
for observed failures, validation evidence and unresolved publisher exceptions.

```sql
SELECT mode,status,started_at,finished_at,summary
FROM ingestion_run ORDER BY started_at DESC LIMIT 10;
SELECT kind,status,count(*) FROM ingestion_asset GROUP BY kind,status;
SELECT series,count(*),min(observed_on),max(observed_on)
FROM historical_price GROUP BY series;
SELECT url,status,error FROM ingestion_asset WHERE status IN ('failed','review');
SELECT status,count(*) FROM source_ocr_task GROUP BY status;
SELECT publisher,series,currency,unit,count(*),min(observed_on),max(observed_on)
FROM published_official_price GROUP BY publisher,series,currency,unit;
SELECT kind,status,processor_version,count(*)
FROM ingestion_asset GROUP BY kind,status,processor_version;
SELECT count(*) FROM official_source_review;
```

Adding support for an old publisher format requires a parser check before its
failed assets are reset to `pending` with `checked_at=NULL`. A successful build
or registered timer alone is not execution verification: invoke the function and
check a completed run plus the database and app responses.

On 8 September 2026 UTC, a read-only audit found enabled retention/immutability
triggers, no ingestion-role DELETE/TRUNCATE privileges, no Azure Storage lifecycle
management policy, and a Blob matching every one of 937 documents then marked
`retention='permanent'`. Downloaded ZIP, PDF, CSV and XLSX samples matched their
database SHA-256 and byte size. The combined parser/OCR/source suite passed 68
tests. The subsequent scheduler/health/revision/OCR fixes passed 77 tests and a
real PostgreSQL scheduler regression using only a temporary queue table.
The later city/matrix OCR fallback suite passed 84 tests. Its real PDF fixture
contains a readable native price page, an image-only table with a native title,
and a logo-only notes page. Only the failed table page was queued. Two real
Gemini 3.5 Flash readings agreed and the ordinary city parser reconstructed both
pages with the original date, market, classification and package prices. These
synthetic fixture observations were never published to the database. Four real
city PDFs (323 observations) also matched the native parser exactly and queued
no OCR. Evidence is retained under `artifacts/city-ocr-fallback-*`.
The subsequent grouped-milk and text-date supply fixes pass 100 tests. Both 2022
milk annexes now yield 208 municipality prices across 25 departments each, using
their explicit pesos-per-litre label and sheet month. Their 416 recovered prices
were replayed and verified in the published view and frontend full-history API.
All 88 completed milk/rice originals still produce the same 67,209 observations.
The 2020 supply workbook's 1,813,661 readable rows reconcile to 33,981 monthly
groups across 29 markets, 177 foods and all twelve months, totaling
6,308,398,393.95 kg. Its dates are literal day/month/year text; no OCR is required.
See `artifacts/milk-2022-layout/`, `artifacts/supply-2020-validation.json` and
`artifacts/supply-2020-production-memory.json` for dated evidence.
The memory/host-capacity regression suite then passed 107 tests. Full-source
parsing preserves an identical canonical digest for every group and source range
while reducing measured peak RSS from 996,065,280 to 232,652,800 bytes. The shared
Linux App Service plan is B2 ([two cores, 3.5 GB RAM](https://azure.microsoft.com/en-us/pricing/details/app-service/linux/)); this provides room for the
web app, ingestion and large historical workbooks. `infra/provision.py` preserves
the existing SKU unless `AGRO_APP_SERVICE_SKU` explicitly requests another one.
The private `run-check?asset_url=...` repair operation selects only an already
registered source, using the same advisory lock, archive and normal parser.
These are dated validation observations, not a claim that the historical
queue is complete or that every possible publisher layout is supported.

The audited worker release `b77bbef7cafe2f34ef0eba36fa4c04fd2e74ec22e5f8276308f28a200f9e2f0a`
was deployed and verified on 8 September 2026 UTC. Its status check returned in
0.468 seconds; DANE and World Bank read-only workbook previews returned HTTP 200
in 0.784 and 0.854 seconds. Cloud run `9de51a9e-50cb-4d20-b528-46cb1ef5cb49`
processed three source assets and 2,483 observations with no errors, archiving a
city ZIP plus 48 original PDFs. All 49 new Blobs were downloaded and matched
their database SHA-256 and byte size. The 120.3-second run finished its current
file, then stopped starting new files
at the validation time boundary. See `artifacts/ingestion-deployment-verification.json`
and `artifacts/ingestion-final-state.json` for evidence and dated queue counts.
The later OCR-fallback release
`fbe2be323f90cee3b2e8721818a76b5ef7188991311515d6594dc382d91e6f37`
passed the same deployed checks. Run `80e8a234-ba62-4302-8a0a-741ccfff6ae5`
processed four real source assets and 2,195 rows in 88.9 seconds with no errors.
Two new original files were downloaded from Blob and matched their database
SHA-256 and size. Corabastos published history increased by 350 observations.
One previously completed city ZIP was replayed successfully with `city-v3`;
the remaining 35 completed ZIPs with `city-v2` remain eligible for replay.
At 02:49:53 UTC the archive contained 1,443 documents including 1,066 originals,
and the queue contained 481 complete, 76 archived, 9,198 pending, four failed
and three review assets. These counts include newly discovered files.
See `artifacts/city-ocr-fallback-verification.json` and
`artifacts/city-ocr-fallback-final-state.json`; prior release evidence is retained.
An additional archived-PDF replay recovered 444 omitted Porkcolombia market/date
observations by correcting source locators that previously identified a row but
omitted its market column. The publisher's available quotes rose from 282 to 726;
all published Porkcolombia and Corabastos quotes now preserve source pages.

The final deployed worker release
`ab7f1e15da716a8f68baa3d1a1ba3f7b127589f0029756b809a86d71a7bc7ab4`
completed the real 95,409,078-byte 2020 supply workbook in Azure. Run
`1194ade3-f1ad-4603-b84b-1f2ebe1d57e2` ran from 03:25:34 to 03:30:38 UTC
on 8 September 2026: 304.4 seconds, one file, 33,981 published monthly groups,
zero errors and zero OCR requests. Database totals matched the independent full
source reconciliation, and a fresh Blob download matched the original SHA-256
and byte size. The HTTP caller timed out before completion; the durable run
record and final published observations prove success. No exact per-stage timing
was instrumented. Azure's one-minute app memory samples peaked at 422,081,877
bytes during this run; these sampled values are not a precise process peak.
The shared plan's corresponding sampled maxima were 66% memory and 72% CPU.

At 03:38:21 UTC the final snapshot showed 1,443 retained documents including
1,066 originals, 39,384 published official-reference observations, and a queue
of 484 complete, 76 archived, 9,198 pending, one failed and three review assets.
Daily and hourly timers were enabled with monitoring and Always On. Status
returned HTTP 200 in 0.415 seconds; DANE and World Bank read-only Excel previews
returned HTTP 200 in 0.548 and 0.441 seconds. Both recovered 2022 milk annexes
and the 2020 supply workbook are complete under the repaired processors.
The one failed file is the publisher's missing 23 October 2012 daily workbook.
The three review files retain contradictory dates: the 6 and 9 July 2012 daily
links both contain 5 July, and the December 2020 milk link contains November.
These originals remain retained; their contradictory dates are not guessed.
The 902 queued city ZIPs and 35 completed ZIPs awaiting the newer city parser
remain resumable through the hourly queue, so historical loading is ongoing.
See `artifacts/supply-2020-cloud-verification.json`,
`artifacts/supply-2020-cloud-memory-final.json`,
`artifacts/supply-2020-plan-metrics-final.json`, and
`artifacts/final-memory-layout-state.json`. Earlier proof files remain intact.

### Source review and resumable official quotes

`coffee_sources.py` extracts explicit FNC price columns with separate currencies,
periods and price bases; national daily values retain their existing projection.
`dane_context.py` discovers audited explanatory PDFs without inventing monetary
observations from charts or percentages. `seasonality.py` requires compatible
complete years and preserves original documents for each month.

Official quote sources validate every row before publishing 2,000-row batches.
Immutable primary keys make interrupted batches idempotent. The durable
`official:complete` checkpoint is written only after the entire source succeeds;
a superseded original with partial rows remains eligible for retained replay.
Review-aware publication views withhold ambiguous observations without deleting
them. See the dated DANE, Colombia and international coverage matrices in `docs/`
for actual source tests and boundaries between structured prices and context.

The scheduled `OcrRecovery` job runs at minute05 each hour (`OCR_SCHEDULE`),
with a ten-minute budget, at most two OCR tasks and the existing daily provider
request cap. It uses the same ingestion lock. Due exchange-rate and seasonal
refreshes run before large native assets. Seasonal work yields after its
independent five-minute allowance, retaining committed complete-year batches.
This protects fresh sources; eventual completion of every seasonal year still
requires observing that repeated comparison work fits the available allowance. Daily discovery and historical catch-up remain independently
scheduled; all schedules are configured remotely in Azure App Settings.

Current official references are computed during ingestion into
`official_catalog_current`; request handlers do not reconstruct the catalog from
all historical revisions. Migration `20260927_007_official_catalog.sql` adds the
derived table, review/quote invalidation triggers and missing identity stubs.
Initialize an existing database with `official_catalog.bootstrap(db,
batch_size=100)`, which commits independently resumable batches. Run boundaries
refresh up to100 dirty identities; each completed official source refreshes its
affected identities and completion marker together. A reviewed identity with no
eligible quote becomes a tombstone. Raw observations and evidence are retained.

Native extraction recovery and its evidence are documented in
`docs/EXTRACTION_RECOVERY_2026-09-27.md`. The order is native file cells,
verified alternate headers/PDF geometry, then rendered-image OCR only when
native extraction fails. Contradictory or absent source evidence stays in
review. Parser upgrades retry stale OCR/error records before untouched files
within the same backfill family, while preserving current-parser cooldowns.
