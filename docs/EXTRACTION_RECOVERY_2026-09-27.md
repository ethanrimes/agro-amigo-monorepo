# Extraction recovery audit — 27 September 2026

This audit started from live failed/review/OCR asset records and downloaded the exact official originals again. It improves native extraction and retry selection without deleting historical observations or original documents. Local extraction results below are distinct from cloud publication verification.

## Fallback order

1. Select the native XLS or XLSX reader from the file signature. Use actual sheet headers, printed periods and literal numeric cells.
2. Try verified legacy layouts and PDF word coordinates: current/comparison month captions, mixed cell types, wrapped headings and font changes. Keep method, source locator, period and printed presentation.
3. Use the existing rendered-image OCR path only when native extraction fails on an image or unreadable font. Agreement, monetary-table/unit/date checks and provider request limits still apply. A readable percentage chart or prose bulletin is not an OCR candidate just because it yields no price-table rows.
4. Preserve ambiguous source evidence for review. Missing units, contradictory dates and conflicting prices cannot be repaired by guessing. Where row identities are independent, publish verified neighboring rows and withhold every conflicting identity.

Parser upgrades revalidate mutable URLs and retry stale OCR/review/failure records. Backfill prioritizes these repaired failures ahead of untouched files of the same family. Recent-file selection also retries outdated native parsers. Failures from the current parser retain cooldowns; a pending attempt interrupted during publication does not bypass its cooldown merely because its parser version is old.

PDF retries reuse retained text and tables only for the exact document SHA, page and extraction version. Missing pages are still extracted, changed documents stay independent, and OCR eligibility retains its own scan version. Successful native weekly PDF publication retires obsolete pending OCR tasks with an explicit retained-evidence reason. The OCR worker also checks the exact current-version completion checkpoint before accessing readings or calling a provider. This guard is deliberately limited to weekly PDFs; input PDFs can contain image pages alongside successfully parsed native rows.

## Reproduced failures and results

| Source family | Actual failure | Recovery and local evidence |
| --- | --- | --- |
| Monthly annex XLS | `Julio/junio de 2015` and `Enero 2016/diciembre 2015` were misdated | 17 previously failed originals now extract 6,906 prices; positive price and variation cells independently reconcile. Numeric text percentages and `Variación 12 meses` are retained with Excel scaling respected. |
| Legacy insumo XLS | Unrecognized categories and current-price/header variants | Explicit category aliases, unique current-month matching and irrigation layouts recover 120,868 prices across 15 originals. Three modern XLSX controls add 85,025 cells: 205,893 exact native cell/locator comparisons. |
| Legacy electricity XLS | Provider/stratum headers were ignored | Three originals each retain 114 tariffs plus literal subsidy/contribution values. Zero and absence remain distinct. No municipality or monetary unit is invented. |
| Insumo PDF | Mixed bold/plain headings, split words, missing comma whitespace | All eight failed originals now parse 60,790 rows natively. An 11-original stress set retains 71,982 rows: 71,975 valid and seven publisher-overprint reviews. Rendered pages verify unusual printed presentations. |
| Weekly XLS/XLSX/PDF | Cross-month caption, blank product cell, conflicting duplicate identities | Four failed originals retain 17,727 rows: 17,302 publishable candidates and 425 reviews. All 39,717 workbook price cells reconcile; 4,427 common PDF/companion keys have no numeric differences. The previous 12-original corpus retains identical price/identity/review projections for all 49,006 rows. |
| Weekly PDF overprinted headers | Exact overlapping glyphs yielded `MMíínniimmoo` instead of `Mínimo` | Native fallback recovers only header coordinates after normal detection fails. Body words remain untouched; overlapping body digits or incomplete headers still require OCR. The 4 September 2026 original yields 4,435 publishable prices and 132 unit reviews; all 130 recovered rows match 390 independent companion-workbook price cells. All 49,006 full records from the prior 12 originals remain identical. |
| Porkcolombia PDF zero terciles | A positive-only decoder raised before the existing zero-review guard | Literal zero cells now reach review without preventing neighboring valid prices from publication. Quincena 16/2026 retains 280 publishable quotes and 15 reviews: nine zero cells and six existing chronological conflicts. Negative/malformed prices and printed date conflicts remain rejected or reviewed. |
| Stale department/municipal OCR failures | Stored status referred to an older parser | Three freshly downloaded workbooks already parse natively. Scheduling/version checks make them eligible for native replay; extra OCR is unnecessary. |
| XLS context fallback | OLE workbook reached a ZIP-only reader | Signature-based native reading preserves cells and hyperlinks for XLS and XLSX. Unknown formats still fail explicitly. |

## Boundaries retained

- `Anexo-SipsaLeche_dic_2020.xlsx` literally prints November 2020. Its December archive association remains a date conflict.
- The 29 November 2012 daily XLS contains positive prices under genuinely blank merged market headings. Sixty prices lack market labels; another 178 have explicit labels. The original is retained but this whole file remains unpublished. A neighboring file's different market roster cannot establish the missing identities. Partial publication of its labelled columns is not implemented in this patch.
- Broken daily XLS links remain publisher download failures. Four corresponding PDF originals are readable prose: 13 pages, zero price grids, 113 dollar mentions. These are not 113 independently validated table observations. PDFs/text stay retained; OCR cannot replace a missing structured table. New zero-grid processing records an explicit coverage diagnostic.
- This patch does not introduce a general narrative-price parser, infer missing units, or claim that every queued historical source has completed.
- Original files and ambiguous rows remain retained. No database capacity or retention change is part of this deployment.

## Validation and operational evidence

Evidence is under ignored `artifacts/extraction-robustness-2026-09-27/`: source hashes, literal-cell oracles, rendered pages, per-file counts, database tests and cloud replay results. Subdirectories `weekly`, `inputs-pdf`, `inputs-xls`, `monthly`, `references` and `daily` separate source evidence from operational reports.

The final combined ingestion/infra regression run executed 428 tests: 345 passed and 83 opt-in database tests were skipped. Separate private PostgreSQL runs passed the 12-test worker/scheduling suite and all three input-PDF version-precedence tests. Focused tests cover HTTP 304, changed bytes, parser upgrades, cooldowns, OCR eligibility, interrupted-page repair, original retention and isolated deployment-package imports.

The first 27 real Azure replays completed successfully, including all 17 failed monthly annexes. Read-only reconciliation checked all 73,489 price rows against fresh native extraction, 425 retained weekly review rows, and 114 electricity tariffs. Each original downloaded through the public evidence endpoint matched its database SHA and Azure Blob bytes. Frontend history API samples matched stored prices and dates for every replay. Department values identical to an earlier retained source correctly kept that source attribution. Workbook evidence previews returned successfully.

The 64-page March 2014 PDF exposed redundant retention work during its 405-second cloud replay. A subsequent local cache test of the same original completed the page-retention step in 0.054 seconds with zero native text/table extraction calls, while still dispatching OCR eligibility checks. This is a page-retention measurement, not a full pipeline benchmark.

The 92-page June 2013 PDF completed in Azure with 9,860 retained rows in 342 seconds. Both long PDF requests exceeded the HTTP client's wait, but their durable cloud runs finished successfully; verification waited for the ingestion lock and checked the final run and asset records rather than treating the client timeout as a pipeline failure.

The final deployment (`8028d12094d57464b447cd948517e4210acdf149d8fadaa2fd9e45163d7ea52b`) also recovered the overprinted September weekly PDF and Porkcolombia report, and rechecked the cross-month weekly control. The cumulative proof covers **29 distinct originals, 78,204 exact price rows, 572 retained review rows and 114 electricity tariffs**. Every original matched its database and Azure Blob SHA, and every source had a successful frontend history sample. The weekly report's two pending OCR tasks changed to review with a native-success explanation; both images remain retained, with zero provider attempts and zero OCR readings before and after.

Azure status and function inventory returned HTTP 200 for the final package; Always On and all timers remain enabled. Daily refresh is at 23:00 UTC (18:00 Colombia), historical backfill at minute 15 hourly, OCR at minute 05 hourly, and the watchdog at minute 45. The final restart was coordinated with the existing advisory lock after active ingestion finished; the 19:15 backfill invocation could not overlap deployment. The existing HistoricalBackfill function was explicitly started at 19:22:24 UTC after validation. By 19:22:55 it had processed 15 assets / 1,212 rows without errors and was continuing into another source.

History is still in progress. The 19:23 metadata snapshot contained 6,870 pending assets and 19 current-version issue records: four broken downloads, one missing-market-heading failure, eleven source-date reviews and three workbooks awaiting a verifiable publication date. Other failure/review/OCR entries still carried older parser versions and require the ongoing replay before their outcome can be assessed. These counts describe queued source metadata, not a claim of complete historical coverage.

## Code navigation

- `worker.parse_monthly_summary`: monthly matrix, dates and percentages.
- `inputs.parse_inputs`: legacy/current input headers; `prepare_input_stage`: verified PDF version precedence.
- `pdf_sources.parse_input_pdf`: native word geometry and review-only unresolved headings.
- `pdf_sources.extract_pages`: immutable native-page cache and independent OCR scanning.
- `dane_weekly`: weekly periods, workbook/PDF layouts and per-identity reviews.
- `official_sources.process`, `ocr.drain`: obsolete weekly OCR retirement after verified completion.
- `input_references`: electricity/context extraction with native format selection.
- `queue_plan`: current/historical retry eligibility; `verify_scheduler`: real PostgreSQL queue checks.
- `test_*fallbacks.py`, `test_input_pdf_recovery.py`, `test_daily_pdf_narrative.py`: evidence-based regressions.
