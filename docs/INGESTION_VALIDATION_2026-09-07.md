# Azure ingestion and mobile validation — 7 September 2026

This is the initial checkpoint. See [current delivery and validation](VALIDATION_2026-09-08.md) for the expanded sources, later fixes and remaining queue.

The permanent ingestion service is deployed to the existing Azure subscription
`9a04b64b-af19-4519-be50-56ec2acbd855`, tenant
`148ba320-1a6d-4fd7-ba8b-2897083e7531`. It updates the existing AgroAmigo database.

## Deployed service

| Resource | Configuration |
| --- | --- |
| Resource group | `agroamigo-demo-rg` |
| Function app | `agroamigo-data-9a04`, Python 3.11, Functions 4, Always On |
| Compute | Existing `agroamigo-demo-plan` Linux B1 plan |
| Database | `agroamigo` on `agroamigo-demo-pg-9a04` |
| Source archive | Private `agroamigodata9a04/source-archive`, no lifecycle expiration |
| Daily refresh | 23:00 UTC / 18:00 Colombia, every day |
| Historical backfill | Hourly at minute 15 UTC, up to 100 queued assets per run |
| Database storage | 32 GiB, autogrow enabled; additional storage increases charges when needed |

Deployment includes Linux-compatible dependencies and verifies that the running
worker's SHA-256 matches the local release. The protected status endpoint queries
the real database. Credentials remain in ignored owner-only local files and Azure
app settings.

The app selects recent 12-month price views and five complete prior years for
seasonality. These queries do not remove historical records. Historical source
rows, original documents and published observation revisions are retained.
Database triggers reject deletion/truncation of historical stores and mutation
of immutable source/history tables. The cloud writer has no DELETE, TRUNCATE or
DDL privileges. Legacy importers no longer prune old observations.

## Historical coverage

The validation snapshot contains 1,575,801 source-level price records:

| Series | Records | Earliest | Latest |
| --- | ---: | --- | --- |
| DANE consolidated monthly prices | 753,676 | 2013-01-31 | 2026-07-31 |
| DANE monthly bulletins | 2,149 | 2012-07-31 | 2012-12-31 |
| DANE daily source rows, backfill continuing | 19,023 | 2012-06-12 | 2026-09-07 |
| DANE agricultural input history | 792,306 | 2018-01-31 | 2026-07-31 |
| FNC national daily coffee references | 8,647 | 2003-01-02 | 2026-09-06 |

Every publication month from July 2012 through July 2026 is represented in the
monthly series. This validates overall publication coverage; individual products
and markets naturally have different reporting periods. The different daily and
monthly product definitions remain distinct. Prices are not interpolated.

There are also 8,341 TRM records from 1991-12-02 through 2026-09-05. Supply now
includes the 14,175 aggregates for 2013 as well as 68,514 aggregates for 2025–2026.
The intervening supply years and remaining daily bulletins continue through the
hourly backfill queue.
The queue records failed assets explicitly and retries eligible failures.

The start dates agree with [DANE's SIPSA price methodology](https://bibliotecadoctecnica.dane.gov.co/static/documentos/DIMPE/SIPSA_P/SIPSA_P_Ficha%20metodol%C3%B3gica.pdf).
Source discovery uses [DANE's monthly archive](https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/mayoristas-boletin-mensual-1)
and the other official source indexes documented in the ingestion worker.

## Cloud execution and data checks

- Cloud daily run `62ed1931-8a32-4257-9380-e63206c0eeb7` succeeded in 128 seconds:
  17 assets checked, 10 overlapping TRM records refreshed, no errors, zero new
  source rows. This verified idempotent updates on Azure.
- A later cloud daily run, `559c8afb-3e87-4053-b6ee-b3ef960de731`, succeeded in
  103 seconds: 29 assets checked and 2,194 additional source rows, no errors.
- Cloud backfill run `85654221-5bc0-4486-abc2-3a87f540aa5c` succeeded in 82.5 seconds:
  100 archive indexes processed and 4,372 source links discovered, no errors.
- Full 792,306-row agricultural input reprocessing completed on Azure. Subsequent
  backfill also ran automatically at 20:15 UTC, confirming the actual timer.
  These runs exposed older filename, Excel date-cell, blank-sheet and multirow
  header formats; the parser now handles them, with regression checks.
- The 2012-07-06 and 2012-07-09 archive links serve a workbook internally dated
  2012-07-05. Both originals are retained and linked with `status='review'`;
  their prices are not assigned to the conflicting link dates. This is an
  explicit publisher-data gap, not discarded historical content.
- All 166 daily archive indexes were discovered successfully after supporting
  the short filenames used in 2022–2023. The current queue includes 6,575 remaining
  daily/supply files. One official XLS link for 2012-10-23 returns HTTP 404; its
  available PDF is archived, but contains narrative rather than a supported
  price grid. That source gap remains visible, and available originals are kept.
- Live checks as the restricted ingestion role passed: future dates rejected,
  old dates accepted in a rolled-back transaction, deletion rejected, matching
  evidence present, and original bytes match their SHA-256 identifiers.
- Four independent source-value checks passed, covering 2003 FNC, 2012 daily and
  monthly DANE, and the first consolidated 2013 workbook.
- All 32 ingested original files at initial verification were present in private
  Blob Storage with matching sizes and SHA-256 metadata; database originals were
  hashed independently.
- The app's database reader cannot modify official reference data.
- Live API checks passed: 356 products, correct coffee/commodity units, 364 days
  of coffee history within the display window, 16 coffee delivery references,
  13 factors, positive TRM, and 373 daily quotes dated 2026-09-07.
- Eleven offline parser regression tests passed. Python compilation and whitespace
  checks passed.
- The older supply microdata layout was checked against the original 2013 file:
  14,175 monthly aggregates spanning January–December 2013. Header discovery
  supports the earlier spelling, column positions and semester worksheets as
  well as current workbooks. Supply years are queued before individual daily
  bulletins so the broad historical coverage is filled first.
- Final deployed code was verified using a fingerprint of all three ingestion
  modules. Cloud run `0fa2b611-f848-444b-bd5a-a9a8059dd242` archived the 2013 supply
  workbook and committed all 14,175 monthly aggregates on Azure. After the worker
  restart, run `8408b6c5-c337-48b8-8359-787b3ea7bf2d` resumed from the checkpoint
  and is continuing subsequent supply years. Previously committed history survived
  the restart.
  The function-key endpoint rejects unauthenticated requests with HTTP 401.
- Two Python execution threads keep status requests responsive while the database
  advisory lock permits only one ingestion job at a time. The protected status
  endpoint responded in 2.65 seconds while the resumed backfill was running;
  the shared web app's health endpoint returned HTTP 200.

## Simulator validation

Validation used rebuilt native wrappers against
`https://agroamigo-demo-9a04.azurewebsites.net`.

**iOS:** iPhone 17 Pro, iOS 26.1. Xcode build/run, Flutter analysis, navigation
unit test and both integration suites passed. Checks covered layout and safe
areas, navigation, favorites, farm state and weather, calculations and negative
inputs, daily filtering, saved offers after reload, failed API requests and retry,
PDF page 6/7 evidence and numerical text, native back navigation, scenario export,
and native sharing of the original June 2012 XLS workbook. The native share sheet
displayed the XLS file and its 105 KB size.

**Android:** Pixel 9 emulator, Android API 37. Debug APK build and Android lint
passed. The installed WebView app passed home layout, search/favorites, market
comparisons, coffee units and invalid inputs, latest daily data, farm/weather
persistence, budget arithmetic and saving, PDF pages/download/back, offer
arithmetic/reload, input catalog/source library, API failure/retry, and native
offline recovery. All 13 native scenarios passed with zero uncaught JavaScript
errors. The June 2012 XLS download also matched the database original
byte for byte (`0fb775628805cb72413852453abe63f4b09eba5c302bd5be377efed5328b68c1`).

The tests restored saved device/browser data. Android's saved emulator snapshot
was unresponsive and a system WebView update interrupted an early attempt;
cold boot and rerunning after the update resolved those environment issues.
iOS logged some failed Next.js prefetch requests with browser-navigation fallback;
the actual tested navigation and data operations passed.

The working tree also contains concurrent web UI changes. One existing browser
test expects national coffee for an invalid region; the deployed version returns
an empty list. That working-tree expectation did not pass against the deployed
version. The independent live-data checks and native suites above passed against
the deployed UI. This ingestion deployment does not publish those concurrent UI
changes or distribute new App Store/Play Store builds.

## Evidence and repeatable checks

Run commands and operational queries are in
[the ingestion README](../pipelines/ingestion/README.md).

- `artifacts/cloud-status-final.json`: protected cloud status snapshot and release.
- `artifacts/final-ingestion-coverage.json`: latest coverage, supply range and explicit source issues.
- `artifacts/cloud-configuration-validation.json`: timers, runtime and retention configuration.
- `artifacts/ingestion-validation.json`: data coverage, queue and source integrity checks.
- `artifacts/app-data-validation.json`: live app API assertions.
- `artifacts/source-archive-validation.json`: archived original checks.
- `artifacts/android-validation/report.json`: native Android scenario results and screenshots.
- `artifacts/ios-integration-validation.log`, `artifacts/ios-data-validation.log`: both iOS suites.
- `artifacts/ios-validation-historical-xls-share.png`: historical XLS native sharing.

Generated artifacts remain local and ignored by Git. Backfill counts continue to
change as scheduled runs complete; use the protected status endpoint or database
queue for current progress.
