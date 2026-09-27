# Extraction recovery audit — 27 September 2026

This audit started from live failed/review/OCR asset records and downloaded the exact official originals again. It improves native extraction and retry selection without deleting historical observations or original documents. Local extraction results below are distinct from cloud publication verification.

## Fallback order

1. Select the native XLS or XLSX reader from the file signature. Use actual sheet headers, printed periods and literal numeric cells.
2. Try verified legacy layouts and PDF word coordinates: current/comparison month captions, mixed cell types, wrapped headings and font changes. Keep method, source locator, period and printed presentation.
3. Use the existing rendered-image OCR path only when native extraction fails on an image or unreadable font. Agreement, monetary-table/unit/date checks and provider request limits still apply. A readable percentage chart or prose bulletin is not an OCR candidate just because it yields no price-table rows.
4. Preserve ambiguous source evidence for review. Missing units, contradictory dates and conflicting prices cannot be repaired by guessing. Where row identities are independent, publish verified neighboring rows and withhold every conflicting identity.

Parser upgrades revalidate mutable URLs and retry stale OCR/review/failure records. Backfill prioritizes these repaired failures ahead of untouched files of the same family. Recent-file selection also retries outdated native parsers. Failures from the current parser retain cooldowns; a pending attempt interrupted during publication does not bypass its cooldown merely because its parser version is old.

## Reproduced failures and results

| Source family | Actual failure | Recovery and local evidence |
| --- | --- | --- |
| Monthly annex XLS | `Julio/junio de 2015` and `Enero 2016/diciembre 2015` were misdated | 17 previously failed originals now extract 6,906 prices; positive price and variation cells independently reconcile. Numeric text percentages and `Variación 12 meses` are retained with Excel scaling respected. |
| Legacy insumo XLS | Unrecognized categories and current-price/header variants | Explicit category aliases, unique current-month matching and irrigation layouts recover 120,868 prices across 15 originals. Three modern XLSX controls add 85,025 cells: 205,893 exact native cell/locator comparisons. |
| Legacy electricity XLS | Provider/stratum headers were ignored | Three originals each retain 114 tariffs plus literal subsidy/contribution values. Zero and absence remain distinct. No municipality or monetary unit is invented. |
| Insumo PDF | Mixed bold/plain headings, split words, missing comma whitespace | All eight failed originals now parse 60,790 rows natively. An 11-original stress set retains 71,982 rows: 71,975 valid and seven publisher-overprint reviews. Rendered pages verify unusual printed presentations. |
| Weekly XLS/XLSX/PDF | Cross-month caption, blank product cell, conflicting duplicate identities | Four failed originals retain 17,727 rows: 17,302 publishable candidates and 425 reviews. All 39,717 workbook price cells reconcile; 4,427 common PDF/companion keys have no numeric differences. The previous 12-original corpus retains identical price/identity/review projections for all 49,006 rows. |
| Stale department/municipal OCR failures | Stored status referred to an older parser | Three freshly downloaded workbooks already parse natively. Scheduling/version checks make them eligible for native replay; extra OCR is unnecessary. |
| XLS context fallback | OLE workbook reached a ZIP-only reader | Signature-based native reading preserves cells and hyperlinks for XLS and XLSX. Unknown formats still fail explicitly. |

## Boundaries retained

- `Anexo-SipsaLeche_dic_2020.xlsx` literally prints November 2020. Its December archive association remains a date conflict.
- Broken daily XLS links remain publisher download failures. Four corresponding PDF originals are readable prose: 13 pages, zero price grids, 113 dollar mentions. These are not 113 independently validated table observations. PDFs/text stay retained; OCR cannot replace a missing structured table. New zero-grid processing records an explicit coverage diagnostic.
- This patch does not introduce a general narrative-price parser, infer missing units, or claim that every queued historical source has completed.
- Original files and ambiguous rows remain retained. No database capacity or retention change is part of this deployment.

## Validation and operational evidence

Evidence is under ignored `artifacts/extraction-robustness-2026-09-27/`: source hashes, literal-cell oracles, rendered pages, per-file counts, database tests and cloud replay results. Subdirectories `weekly`, `inputs-pdf`, `inputs-xls`, `monthly`, `references` and `daily` separate source evidence from operational reports.

The first combined regression run executed 398 tests: 315 passed and 83 opt-in database tests were skipped. Separate private PostgreSQL runs passed the 12-test worker/scheduling suite and all three input-PDF version-precedence tests. Focused tests cover HTTP 304, changed bytes, parser upgrades, cooldowns, OCR eligibility, original retention and isolated deployment-package imports. Deployment and cloud publication results will be recorded after verification.

## Code navigation

- `worker.parse_monthly_summary`: monthly matrix, dates and percentages.
- `inputs.parse_inputs`: legacy/current input headers; `prepare_input_stage`: verified PDF version precedence.
- `pdf_sources.parse_input_pdf`: native word geometry and review-only unresolved headings.
- `dane_weekly`: weekly periods, workbook/PDF layouts and per-identity reviews.
- `input_references`: electricity/context extraction with native format selection.
- `queue_plan`: current/historical retry eligibility; `verify_scheduler`: real PostgreSQL queue checks.
- `test_*fallbacks.py`, `test_input_pdf_recovery.py`, `test_daily_pdf_narrative.py`: evidence-based regressions.
