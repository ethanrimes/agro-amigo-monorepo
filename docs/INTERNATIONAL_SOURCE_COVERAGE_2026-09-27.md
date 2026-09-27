# Expanded FNC / international / TRM source audit

Source-by-source outputs are in `source-output-matrix.json`; `expected-source-quotes.json` provides 275 exact DB/API checks with source hashes, quote keys, price bases, units, dates and locators. Download/replay scripts are read-only. No live database writes were made by this audit.

## Price coverage added

`coffee_sources.py` extracts all explicit positive numeric prices in the FNC workbook's six price sheets: national daily, sound bean, quality incentive, national monthly, monthly ex-dock, calendar-year ex-dock, coffee-year ex-dock, and all thirteen ICO group/market columns. The September workbook yields 20,218 observations; 11,551 are beyond the existing national daily series. The August workbook yields 20,198. National monthly history begins January 1944; ex-dock monthly begins January 1913. The coffee-year convention is October 1–September 30, explicitly documented by FNC: https://cauca.federaciondecafeteros.org/glosario/ano-cafetero/ . Incomplete/future periods and missing/zero cells do not become prices.

External prices printed in US cents per pound are divided by 100 and labeled USD per pound, retaining literal prices, literal units and normalization details. FNC ex-dock's explicit 453.6g-pound convention remains in its unit. The positive quality incentive is labeled a bonus, not the total coffee price. Cultivated area, production volume and total harvest value remain context in the original workbook and are never published as unit prices; separate structured context projection is not implemented here.

The current September 25 FNC PDF was visually checked on both pages: national FR94 COP2,105,000/125kg, thirteen yield factors, sixteen Almacafé branches. Newly extracted explicit references are NY contract C278.60USCent/lb (USD2.786/lb) and pasilla COP12,000/kg. NY futures are labeled separately from producer purchase prices. Printed FR94 narrative says6.14kg pasilla while its table says8.16kg; this upstream inconsistency is not silently reconciled or used to derive additional prices.

## Exhaustive registered international originals

All209 registered international leaf URLs were replayed, expanding the earlier119-file stress test. With international-v4,180 reports parse into43,176 publishable observations and one isolated quote for review;29 originals remain fail-closed orHTTP404. Exact per-file outcomes are in `all-registered-replays.json`. No OCR was needed for these native-readable files.

The newly isolated reviewed quote is Boston August5,2025 SOLIDAGO: the original prints10.00–14.00, then contradictory 'mostly13.00 mostly10.00'. Both qualifiers are preserved, this one quote receives no published price, and its34 valid sibling quotes remain publishable. Root owns suppression of any previously published version using the exact document/locator in `usda-ambiguous-published-quote.json`; no history is deleted.

All31,381 World Bank monthly agricultural/fertilizer prices (45series, January1960–August2026) were independently reconciled to workbook cells and monthly periods. The publisher's next scheduled monthly update isOctober2,2026: https://www.worldbank.org/en/research/commodity-markets . Energy/metals and tobacco import-unit-values are deliberately outside this agricultural price selection.

Nine actual rendered PDF pages were visually inspected: FNC current2; Miami current2; Boston current1; Miami May2024 pages1–2; Boston January2024 pages1–2. These checks include multi-column/page continuations, rose stem lengths, exact package units, country/variety distinctions, prices and mostly ranges. Images are in `coverage-visuals/` and `miami-current-{1,2}.png`.

## Native TXT archives implemented; cloud replay pending

International adapter v5 now discovers official PDF and TXT flower reports and strips URL fragments from child and pagination URLs. The saved 2018 archive fixtures produce 275 primary quotes: 187 publishable and 88 isolated review records whose inherited variety/origin/grade context or qualifiers cannot be safely resolved. All 396 literal primary/mostly/exceptional ranges were independently reconciled. Miami December17,2018 yields52 publishable+33 review; Boston November27,2018 yields135 publishable+55 review. Native text is decoded directly without PDF conversion or OCR. USDA origin codes are preserved literally rather than guessed as ISO countries. Exact source-line locators, identity keys, prices and reasons are in `expected-txt-quotes.json`; per-file evidence is in `txt-coverage.json`.

Saved originals and discovery evidence: `international-usda-{miami,boston}-index-last.html`, `miami-2018.TXT`, `boston-2018.TXT`. The code and regression tests are complete (commit166679b), while cloud rediscovery/publication remains pending and the historical gap is not yet claimed closed. Existing fragment-duplicate assets are preserved. ESMIS's newest releases are September2025; current AMS mutable PDFs cover September2026, while MyMarketNews archive access remains unavailable from the tested environment.

## TRM and derived seasonality

The official SFC endpoint returned8,355 positive TRM validity intervals, December2,1991 through September26,2026; the latestCOP3,306.86/USD is valid untilSeptember28. There are no gaps, overlaps or50,000-row limit truncation. Original JSON, SHA and complete validation results are in `trm-full.json` and `trm-verification.json`. Live incremental refresh archives can differ from the independently downloaded full-series SHA; expectations explicitly allow that.

Root owns fixes for the reviewed seasonality defects: grouping omitted price unit, and December's document_id was assigned to other months' locators. Root also owns source-timestamp guards for mutable coffee/monthly/factor projections and chronological source aliases. Those integration/deployment fixes are not claimed complete by this source-only audit.

Validation:44 focused international+coffee tests passed; new coffee module and tests pass full Ruff lint; international edits passF/E9/I and formatting. Entire new FNC workbook output was checked independently against exact source coordinates, not just aggregate counts.
