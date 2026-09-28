# AgroAmigo app data spot-check matrix — 2026-09-27

This is the execution checklist for the current web application and the actual installed Android and iOS apps. It inventories **27 page routes, 14 API route files, their displayed data, calculations, filters, sources and persistence** at repository revision `ce91111`. The inventory was prepared from the repository, then desktop Chromium execution began against the deployed Azure application. The execution snapshot below distinguishes complete checks, partial assertions and confirmed failures. Earlier ingestion, Blob, API, responsive-browser or native-suite results do not populate platform cells automatically.

The inventory aims to cover every reachable data-bearing surface and contract. Numerical spot checks use the deterministic samples below; they do not claim to compare every retained historical cell. A route that currently omits a requested capability is a gap to investigate, not a reason to silently remove that check.

## Source completeness companion

[Every source kind and PDF layout family](APP_SOURCE_INVENTORY_2026-09-27.md) is tracked separately from the original313 screen-level checks and ten new read-only-reference checks. It reconciles the parser registry, adapter discovery and live metadata, including archived/context-only PDFs, unsupported layouts, static planning sources, spatial/weather records and unconnected repository collectors. Source-family sign-off requires its own exact date/value/unit/provenance and revision samples; a screen PASS cannot fill it automatically.

## Execution snapshot (DANE first)

At the user’s latest direction, DANE SIPSA takes priority: city packages/rounds, daily/monthly prices, all input categories/scopes/history, milk, rice mills, supply and their originals. Remaining publisher/planning checks stay in the matrix and are deferred until the DANE failures are resolved. A passed assertion is narrower than a passed matrix row.

The preserved baseline used Azure release `b1c203968cc3430591fd9339e8aa60e7`. Prior DANE browser execution used release **`917f33984edb4d8fb35e4d2fb8714d65`**, Chromium153.0.8010.12, at desktop1440px and mobile browser390px/412px. Every viewport executed the **same 88 scenarios / 610 assertions** from the immutable `web/captured-dane-610-917f3398.json`. Each baseline produced609 passing assertions, one incorrect electricity raw-precision expectation and zero blocked cases. A separate focused rerun at each width passed all **4 scenarios / 15 assertions**, correcting that expectation and waiting for fully enabled Supply month controls. The final scoped result is610/610 assertion contracts satisfied at all three browser widths; this does **not** certify all313 matrix rows or native apps.

Evidence: `web/final-desktop-917f3398/report.json`, `web/final-390-917f3398/report.json`, `web/final-412-917f3398/report.json` and `web/focused-{1440,390,412}-917f3398/report.json`. Each retains exact release, manifest SHA, predicates, observed values, response statuses and screenshots. The captured baseline is never overwritten by a harness correction.

- Independent daily original: all **431** Sept25 product/market prices and all **431** percent/null values match retained workbook cells and displayed daily cards. Source SHA `5fc9d3a1d7814c9393b8e8d719b7f338a528586b019d4cdb7374f60922c84a70`; sheet/cell coordinates in `web/daily-original-oracle.json`. This particular grid declares prices per kg.
- DANE breadth includes25 commercial input identities across20 categories, seven municipal inputs,94 monthly Iniciador observations since2018, three rice/mill tonne→kg examples, monthly tomato/farmgate milk, city packages/rounds/classification, comparison constituents, weekly published mean, daily/auxiliary/source originals and reviewed milk identities. Passing these samples does not certify every source row or all category histories.
- Supply: all24 retained2019/2020 months were selected and checked at all three browser widths. ArmeniaJanuary2019, January2020 and August2026 totals have independent source-row reconciliation; Papa superiorAugust2026 is983500kg/25reporting days with exact original row-range evidence.
- Actual browser original downloads cover XLS, XLSX, PDF, JSON and parent ZIP with exact SHA/Azure Blob proof. The large electricity XLSX is **63,509,333bytes** and completed in **29.848seconds** after fixing the old20second streaming abort; exact SHA, Azure header and206range prefix passed (`web/large-original-917f3398/report.json`). Native downloads and CSV/TXT/OCR-image still need separate audit evidence.
- Reproduced baseline defects WEB-01 monthly tomato503, WEB-02 ignored inputfullhistory, WEB-03 wrong city sourceperiod and WEB-04 unscaled Excelpercentage are fixed and their focused DANE browser cases now pass at all three widths. Milk geometry corrections exclude72 incorrect old identities while retaining raw evidence; eight milk revision/source scenarios pass. Rows below remain **PARTIAL** where the scenario covers only part of the wider assertion.
- Workbook source rendering intentionally preserves raw native precision for ordinary numeric cells: tariff503.96 displays503,96. Declared percentage formatting applies scaling/precision: raw−0.5952237758733023 with`0%` displays−60%. The earlier504 expectation was a test error, not a price defect.

Reproducible runner: `scripts/qa/run-browser-matrix.cjs`. `QA_CASES='DANE'` selects the priority core scenarios. Each new deployment/viewport must use a new output directory. JSON includes actual predicates, observed fields, screenshots, response statuses and manifest hashes. Test-harness corrections (wrong media-type assumption, literal label and locale expectations, hydration timing) remain in baseline reports and are not counted as app failures. The workbook percentage issue was only confirmed after inspecting its original Excel number format; the earlier raw-decimal predicate is superseded.

## Latest browser regression: 8a8baf2

The sequential desktop1440px, mobile390px and412px Chromium runs on **`8a8baf2c65b74cb79d70f8c6ef546ade`** each passed **90 scenarios /618 assertions**, with zero failed/blocked cases, JavaScript errors or API responses≥400. This repeats the corrected88/610 DANE suite and adds four source-help assertions plus four neutral equipment-illustration assertions. It preserves the old immutable baseline and its corrections. Exact summary: `web/final-stable-summary-8a8baf2.json`; reports/screenshots: `web/final-stable-{1440,390,412}-8a8baf2/report.json`. Source FAQ history/credits and equipment imagery were also visually inspected at all widths (`web/source-help-final-visual-8a8baf2`). Native results below remain their own release-specific evidence.

The three additional unscoped city-history scenarios also passed18/18 assertions at all three widths on8a8baf2 (`web/unscoped-{1440,390,412}-8a8baf2/report.json`). The distinct browser footprint is therefore **93 scenarios /636 assertions per viewport**. The independent raw-row/Decimal oracle at22:58:30UTC reconciled every date, mean and market count: limón24kg634dates/current89500; mora2.5kg611dates/current22000; mora12.5kg653dates/current80375COP. Maximum arithmetic difference3.34×10⁻¹²COP (`web/unscoped-city-final/oracle.json`). Portable checks allow newly imported dates/markets while preserving prior dates and complete current API/table/graph agreement. They do not freeze an old aggregate against legitimate later market additions.

## Actual native execution snapshot

The installed Android app on emulator5554 and installed Flutter iOS app/WKWebView separately executed the same DANE scenarios on web release`917f33984edb4d8fb35e4d2fb8714d65`. Android's immutable88case baseline recorded607/610 assertions (two Supply readiness checks plus the electricity expectation); iOS recorded609/610 (electricity expectation). The corrected four-case manifest passed15/15 on **each actual native app**, resolving all three harness discrepancies without changing their data assertions. These results establish610 scoped DANE field assertions per native platform, not whole-family or313-row certification. Original settings were restored.

Native evidence: `native/android-final-dane-917f3398`, `native/android-final-dane-corrections-917f3398`, `native/ios-dane-final`, `native/ios-dane-focused`. iOS also ran29 broader scenarios:79 assertions passed in the baseline, with two asynchronous JavaScript harness interruptions; the two corrected scenarios then passed20/20, giving **29 scenarios /95 distinct scoped assertions** after replacement. Evidence: `native/ios-other-final` and `native/ios-other-focused`. Android independently passed the same 29 broader scenarios /95 assertions after its own focused reruns (`native/android-portable-merged-917f3398.json`). Its separate 30-case native suite still exposed 10 route/data failures despite 20 passing groups; those fixes need the next release regression. These broader results do not close unrelated DANE extraction gaps or the later unscoped city-history timeout under investigation.

`executed-matrix-field-crosswalk.json` maps every executed check to its exact scenario, predicate expectation, observed fields, route and screenshot. **PARTIAL** cells mean only those listed fields passed; every other clause in that matrix row remains open. Source-family rows in the companion inventory stayNR. The compact iOS evidence copy omits the large encoded screenshot arrays while retaining result fields; original reports/screenshots are preserved.

Latest native follow-up: iOS independently passed90/618 on8a8baf2 (`native/ios-stable90-8a8baf2/report.json`). Android's supplemental6/28 on8a8baf2 verified the three unscoped city histories, milk image, source help and neutral equipment illustration; its separate full native integration resolved30/30 through29full groups plus the unchanged case18 quiet rerun (`native/android-final-data-corrections-8a8baf2c/report.json`, `native/android-integration-merged-8a8baf2c.json`). The earlier610 DANE Android assertions remain their recorded release evidence; repeated checks are not double-counted. The Mi finca replacement has its separate release-specific proof below.

## Read-only Mi finca regression: de491dcc

On **`de491dcc9cf04603874ff12230083743`**, the same **5 scenarios /21 assertions passed** in actual Chromium at1440,390 and412px, with zero failures or blocked cases. These checks cover the Pitalito EVA2025 crop values, all12 Huila UPRA2024 calendar percentages, four printed Huila2023 bean cost components and8231655COP/ha sum, exact source links, FNC monthly historical values/12 independently computed seasonal indices, an explicit unknown-farm state and storage preservation while changing reference crop. Reports: `mifinca-review/deployed-{1440,390,412}-de491dcc/report.json`.

Separate real browser navigation passed at all three widths: Home → Mi finca → Huila bean reference → rendered original PDF page13 → close → Mi finca. The new farm header, nominal cost table and actual original page were visually inspected; no page overflow or JavaScript errors occurred (`mifinca-review/deployed-visual-de491dcc/report.json` and screenshots). Android independently passed the same5/21 on this release, with original settings restored (`native/android-final-farm-references-de491dcc/report.json`). Actual iOS WKWebView independently passed9 scenarios /41 assertions on the same release: the5/21 replacement checks,3/18 unscoped city-history checks and1/2 milk-image checks, with settings restored and identical release before/after (`native/ios-mifinca-history-de491dcc/report.json`). Its focused native16–24 tail also passed GPS/location, workbook/electricity, supply history, weather, removed-calculator and source/storage assertions (`native/ios-farm-sources-de491dcc/report.json`). That tail logged six recoverable RSC prefetch warnings during programmatic navigation; all routes and assertions completed, so this is not a zero-console-message claim. Whole AGR rows remain PARTIAL where broader invalid-ID, physical-state, storage/reload or entry-path cases are only covered by local fixtures or have not been executed on that platform. No source-family row is completed by these checks.

The actual iOS catalog regression also passed on de491dcc (`native/ios-catalog-de491dcc/report.json`):24-card geometry through both scroll directions, saved identities/filter return, World Bank retained history, flowers and all24 supply months2019/2020. The normal installed Flutter app was then restored; a separate committed Maestro flow passed all10 commands including a native left-edge return from coffee detail to the product catalog (`native/ios-normal-edge-de491dcc.json`). Its initial generic readiness selector was corrected to the observed FNC heading without changing app code. This proves that specific normal-app gesture/navigation path; it does not certify every back-stack combination. Android independently passed the five targeted native groups on de491dcc, including map layers, read-only source/native Back and crop navigation/storage preservation (`native/android-final-release-de491dcc.json`).

## DANE source follow-up begun September 28 UTC

The source recovery is tracked independently from the platform results above.
The 27-target compact-unit city ZIP cohort now has 26 complete archives and one
source-date review. It appended 9,531 immutable price rows; all 44,658 prior-row
fingerprint checks across the replay batches were unchanged. These repeated
per-archive checks are not a distinct-row census. The reviewed Villeta member
literally prints October 21, 2023 while its archive and filename say October 20;
five rows remain unpublished rather than being assigned a guessed date. Evidence:
`planning/city-compact-units/FINAL_RECOVERY.md` and `date-review/review.json`.

The actual scheduled daily run at September 27 23:00 UTC completed at 23:15:20
with 29 assets, 22,060 processed records and zero errors. Its `partial` status
records a durably checkpointed large input workbook, not lost progress. These are
processed records, not a claim of net new inserts. The separate automatic 00:05
OCR run also completed; two decorative presentation pages were retained in review.
Their actual rendered pages exposed an eligibility defect being corrected:
short native section titles with only logos should not consume OCR requests.

The December 2015 input PDF replay validates all 8,285 native rows and corrects
53 wrapped municipality names. The original 8,285 raw rows remain alongside the
new parser revision. Subsequent structured-annex recovery preserves the literal
Excel price 92,416.66666666667 rather than its rounded PDF duplicate 92,417 COP
per 50 kg; all 8,375 existing raw-row fingerprints for the recovered month and
8,694 whole-original checkpoints remained unchanged. This is a narrow proven
rounding equivalence, not a blanket preference based on file extension.
The source remains eligible for automatic replay under its new publication
version. Evidence: `three-source-followup/de-viboral/`.

The December 2014 replay separately validates 6,575 native PDF rows and corrects
40 wrapped municipality names while preserving the old raw rows. Its more
precise Excel observation remains 69,666.66666666667 COP per 50 kg. The public
input API no longer offers the truncated `de Viboral` municipality; the complete
El Carmen de Viboral histories retain the correct 2014 and 2015 sources.
Evidence: `three-source-followup/de-viboral/dec2014-cloud-replay.json` and
`precision-recovery.json`.

Two actual cloud-created milk-chart images passed paired OCR after native
extraction failed: all 20 independently read labels, named regions, observation
months, COP/litre units, published-mean basis and source locators matched.
Four provider calls were used under the unchanged 40-request daily cap. The
original PDFs and actual crop PNGs passed full Azure Blob SHA checks. The May
2026 native chart separately supplied ten labels without OCR. Later-bulletin
precedence is now explicit for overlapping milk observations, and all 30 existing
quote fingerprints survived the view/cache migration. The remaining 16 modern
chart originals and final cross-platform checks are still in progress; this
paragraph does not sign off that larger cohort. Evidence:
`planning/milk-macroregions/cloud-task-smoke.json` and
`artifacts/milk-macroregion-publication/precedence-cloud-migration.json`.

## Execution and evidence rules

- `RETIRED` = removed manual-tool interaction; retained evidence is historical and no current-platform PASS is implied. `NR` = not run; `PARTIAL` = listed field assertions passed but other clauses remain open; `PASS` = observed assertion passed on the named platform/release; `FAIL:<issue>` = reproducible discrepancy; `BLOCKED:<reason>` = could not execute; `N/A:<reason>` = demonstrably inapplicable, approved in the evidence record. Keep stable IDs unchanged after fixes.
- **WEB**: run the deployed website at desktop 1440×900 plus mobile browser widths 390 and 412. Record browser/engine. **ANDROID**: installed APK in an actual Android emulator/device and its Android WebView. **IOS**: installed Flutter app in an actual iOS Simulator/device and WKWebView. Mobile browser emulation never counts as native evidence. A shared API success never alone passes any UI column.
- Record exact web release, APK/app build and commit, OS/device/browser versions, Bogotá and UTC snapshot times, selected sample IDs and all filters. A changing upstream source is not automatically an app defect: compare the archived document version and API response actually used by that screen.
- For each executed ID, save `{id, platform, release, sample, route, query, action, expected, observed, source_document_id, source_locator, evidence_paths, outcome}` under `artifacts/app-data-audit-2026-09-27/<platform>/<ID>/`. Include an actual screenshot and API/native-log evidence where relevant. For a visual bug, capture before and after; for arithmetic, retain operands and an independent calculation. Do not put credentials or private production state in evidence.
- Snapshot and restore original local storage, selected farm/crop, favorites, permissions and network state. Use clearly named disposable QA farm/offer/scenario records. Never delete real user records or historical source data. Local test controls may inject bounded errors into a QA session; do not break production services.
- Source truth hierarchy: **archived original at exact SHA and printed page/cell/JSON row → approved native extraction/review decision → eligible published row/API → visible UI**. A parser and the API agreeing is insufficient when both could repeat the same mistake. Visually read selected PDF pages and compare spreadsheet cells or JSON records independently.
- Preserve null, zero, missing, reviewed, stale and future values as distinct states. Missing quotes are not zero; a midpoint is not a published mean; municipal/departmental/national scopes and currencies must never silently merge.
- Numeric oracle: compare source decimals before UI rounding. COP whole-peso widgets may round at display; official references allow up to two COP/four other-currency decimals; quantity widgets generally use one decimal. Match the documented widget formatter and retain exact raw operands. Do not accept a relative tolerance large enough to hide a unit conversion error.
- Every `P0` check is a release gate. Complete `P1` checks for breadth; `P2` covers low-frequency and legacy cases. A fix requires rerunning its failed check on the affected platform and the shared data assertion on all three platforms; neighboring regression checks are named in the issue evidence.
- Serialise heavy cold API checks against the shared database. Record actual latency and timeout/error behavior; do not turn a warm retry into a claimed cold-load success. Let the scheduled importer continue for the writer-load checks; coordinate maintenance with the parent operator.

## Route and implementation inventory

The exact route files live under `apps/web/src/app`; dynamic IDs below must be resolved from the audited API/sample manifest.

| Route | Reachable data/function | Main implementation / related checks |
|---|---|---|
| `/` | Home unified search, product cards, farm invitation | app/page.tsx; HOM, CAT, NAV |
| `/products` | Unified DANE/FNC/official product catalog | CatalogView, ProductCard; CAT |
| `/product/[id]` | Filtered prices, history, markets, sources, supply; FNC special case | product/[id]/page.tsx, CoffeeDetail; PRD, COF, SUP |
| `/coffee` | Coffee detail entry point | CoffeeDetail; COF |
| `/saved` | Saved catalog identities and filtered recovery | CatalogView savedOnly; CAT, STA |
| `/markets` | Markets list, search, department, map/comparison | markets/page.tsx; MKT, MAP |
| `/market/[id]` | Market identity, expandable prices and supply | MarketPrices, SupplyPanel; MKT, SUP |
| `/compare/markets` | Exact-basis market/national comparison | ComparisonWorkspace; CMP |
| `/insumos` | Grouped input catalog, municipal/department coverage, complementary references | insumos/page.tsx; INP, AUX |
| `/insumo/[id]` | Input scope/location prices, history, map, comparison | insumo/[id]/page.tsx; INP, MAP, CMP |
| `/compare/inputs` | Input comparison preserving presentation/brand/registration | ComparisonWorkspace; CMP |
| `/references` | Official references filter/search/pagination | references/page.tsx; REF |
| `/references/[id]` | Official and summary identity history/source detail | references/[id]/page.tsx; REF |
| `/daily` | Latest daily bulletin product/market quotes and variation | daily/page.tsx; DLY |
| `/regional` | Latest city report per market, packages and rounds | CityPrices; CTY |
| `/data-references` | Input summaries, electricity tariffs, monthly wholesale summaries | data-references/page.tsx; AUX |
| `/farm` | Saved exact pin, weather, spatial layers and crop references | LocationWorkspace, ZoneExplorer, CropOptions; LOC, WEA, GEO, CRP |
| `/farm/[id]` | Same workspace scoped to a retained farm record | LocationWorkspace farmId; LOC, STA |
| `/plan` | Read-only crop, calendar, cost and historical price references; compatible old budget links | CropReferences, SeasonalChart; AGR, CRP, CAL |
| `/offers` | Private quotes, net sale value and purchase cost | offers/page.tsx, offerResult; OFF |
| `/sources` | Source descriptions, retained source library, help/privacy | sources/page.tsx, SourceLibrary; EVI, NAV |
| `/evidence/[id]` | Original PDF, spreadsheet, text, JSON and row-level evidence | EvidenceContent, PdfViewer, WorkbookViewer; EVI |
| `/credits` | Image title/author/license/origin and navigation | credits/page.tsx, image-library.json; NAV |
| `/android` | Demo APK download, version/platform/privacy claims | android/page.tsx; NAT |
| `/auth` | Redirect to /saved; no invented account login | auth/page.tsx; NAV |
| `/settings` | Redirect to /sources | settings/page.tsx; NAV |
| `/map` | Redirect to /markets; actual maps are overlays | map/page.tsx, ColombiaMap; NAV, MAP |

API route inventory (14 files; resources and query branches each require the checks below):

| API | Key parameters / contract and truth |
|---|---|
| `/api/catalog` | `region`; unified identity, exact detail href, currency/basis/unit, regional exclusions; `catalog.ts`, monthly snapshot, regional names, official catalog current view. |
| `/api/products/[id]` | `region,series,market,presentation,units,history`; `price-quotes.ts`, eligible `price_observation`, `regional_price` and `regional_classification`. |
| `/api/coffee` | FNC price/date/history, delivery branches, factors and exchange; original FNC/Superfinanciera documents. |
| `/api/compare/[kind]` | `markets`/`inputs`; A/B/national, series, scope, dates, product and history; `comparisons.ts`, `comparison-math.ts`. |
| `/api/references` | List filters/pagination or `id`; official latest cache plus canonical history and monthly-summary adapter. |
| `/api/data-references` | `kind=summary/electricity/wholesale,q,category,date,page`; `input_reference_row` or monthly summary originals. |
| `/api/planning/[resource]` | `municipalities,farm,seasonality,inputs,weather,regional,daily,library`; exact parameters in route implementation. |
| `/api/explore/[resource]` | `markets,market,input,supply,map`; preserve location, month, scope, price identity and history parameters. |
| `/api/location/[resource]` | `layers,point,grid,tile`; `lat,lon,layer,month,step,bbox`; archived spatial/model response. |
| `/api/location/search` | Place query and returned coordinates/labels; selecting a suggestion must not masquerade as an exact farm measurement. |
| `/api/evidence/[id]` | Locator/page/product/market/month/food/location selectors; original metadata, parents, records and review notes. |
| `/api/evidence/[id]/content` | Original bytes, MIME, filename and Azure storage proof; exact SHA identity. |
| `/api/evidence/[id]/workbook` | Sheet/start controls; native cells, cached formula results, `readOnly`, total/displayed rows/columns. |
| `/api/health` | Deployed API/database availability; diagnostic only, never a substitute for screen assertions. |

Shared inventory: `market-types.ts`, `catalog-types.ts`, `comparison-types.ts`, `explore-types.ts`, `official-types.ts`, `planning-types.ts`, `location-types.ts`, `farm-types.ts`; `Preferences`, `FarmContext`, `useData`, `AppliedFilters`, `SearchBox`, `Overlay`, `CropPicture`, `PriceChart`, `MarketList`, `ComparisonSources`, `QuoteEvidence`, `SeasonalChart`, `EvidenceProvider` and `EvidenceLink`. Native shells are `apps/android/app/src/main/java/co/agroamigo/demo/MainActivity.java` and `apps/ios/lib/main.dart`.

`CleanSheet.tsx` and `CropBudget.tsx` were removed after the manual tools were retired; `CropReferences.tsx` preserves published references without rewriting local farm/scenario storage.

`WeeklyPlan.tsx` and its weather/advisory rules exist but have no current route import. WeeklyPlan reachability and rule coverage are recorded only in the nonexecuted-component appendix; they are excluded from platform totals. Do not claim native execution by mounting a browser-only harness. `FarmEditor` and its `FarmLocation`/`FarmMap` are now retained legacy components without a route import. The source-reference screen handles an empty profile with a municipality selector; old budget/scenario storage is retained and private offers remain separately accessible.

## Deterministic sample manifest

Create `artifacts/app-data-audit-2026-09-27/samples.json` before execution. Save exact IDs, URL filters, source hashes/locators, dates and expected values. Select each row from the live deployed API and eligible source at snapshot time; a current-date source may change later. Reuse the same immutable examples across platforms.

| Pack | Required specimens and selection rule |
|---|---|
| P | At least 12 distinct product identities: FNC pergamino; aguacate Hass; tomato; banana/plantain as separate names; one city-only product; egg per unit; oil/juice per litre; a package with quantity not 1 (e.g. 24kg); farmgate milk; rice mill; one historical-only product. Include first/middle/last catalog pages and two same-name quotes with different unit/currency/market. |
| I | Every returned input category: at least first/middle/last identity, plus fertilizer, pesticide, veterinary/animal input, planting material if present. Include exact same product/presentation across two departments and two municipalities; a brand/ICA-registration collision; no-match reference; oldest/latest retained period. Do not invent a missing category. |
| M | At least six markets in four departments, including Bogotá/Corabastos, a secondary market, milk municipality reference and mill location. Select three with shared comparable identities and one with no comparison overlap; one without coordinates if present. |
| R | At least one identity from every available official publisher and series family, plus all currencies/units/bases. Required families if available: cacao, FNC alternatives, cattle method break, pork mean and each tercile, palm regulatory/reference basis, Corabastos quality, World Bank, USDA flowers/bananas, weekly SIPSA and monthly summaries. Expand the pack for additional returned families. |
| H | For each price family choose newest eligible, previous distinct observation, oldest retained, one middle-era and one revised-source date. For supply choose latest partial month, all 12 months of 2019 and 2020 where retained, and a cross-year boundary. Absence must be documented rather than treated as zero. |
| E | Actual PDF, XLS, XLSX, CSV, JSON, TXT, retained ZIP and OCR PNG; multi-sheet workbook, long filename, reviewed source, corrected-date source, ZIP member/parent, OCR-recovered source, and exact locator beyond first page/100 rows. Known anchors below assist selection. |
| F | Disposable farm A at an exact Pitalito-area pin and farm B in a different department, with distinct municipalities/crops. Include a manual crop, a matched cost-template crop, a crop with no comparable price/template, and absent soil/map coverage. Snapshot all pre-existing storage first. |
| W | Same archived weather response shared across UI assertions: normal full record, null field, current data older than 30min, observation older than 60min, retained response older than 24h, error/retry and changed pin. Fault/stale fixtures run only in isolated QA sessions; label them synthetic. |
| N | Installed Android and iOS app with version/device captured; permission allow/deny, keyboard open, app background/resume, native back/share/download and offline/recovery. No substitutions by browser user-agent strings. |

Known retained source anchors are starting points, not fresh PASS evidence:

- Corrected February11,2014 Excel: `09bcafd697b554afe4bac3953bd5459140dcf356b95f70c42bf569beebac3043`; literal typo “febrera” remains in original while verified date note says2014-02-11.
- November29,2012 partial-market Excel: `3dcd94a82ca334bf3600170f4e9ffb97b8df8daa719ac078ec09dd6faec89554`; previously verified178 explicit price quotes and60 reviewed cells. Revalidate current review count.
- Reviewed December2020 link with November workbook contents: `bc9e16af972eac40d3cb876c494d38581f61927e52b8a18f645e5ee5c0447c69`; preserve original month and review. September2021 milk PDF: `f9787aa7e94848bd7dc0c69d12511919cc49c4751898f14acbdf4fab3416874e`.
- April18,2013 archived daily-query JSON: `396dc7d5fbfb55b84b5b35ac2a56e30cb186477c19e0ef75fd7cf02826c251be`; `JSON resultset[0]; PROMEDIO/MINIMO/MAXIMO`, Carne de cerdo, brazo con hueso / Armenia, Frigocafé, mean=min=max8,500 COP/kg;1,675 original response rows.
- June30 Miami PDF: `d493eb464e68742e1b84095f710dd5ee1ea2995088483b32b06c2b1313a3d4cb`; March21 Boston TXT: `1df030ec957e9c31ff7ed011b8dd6cd3cda9c56387dfa7943bce926ae86b9a53`; March28 Boston TXT: `3aad53490b84d1a7c662b3b792bab5af77b20dc85baa73ebb70305b176b6b9f9`. Previously visible review counts1/36/35 are separate originals, not a date-label guess.
- Weekly published-mean anchor: current audited Acelga / Bogotá Corabastos min333, max533, mean418 COP/kg; a midpoint433 would be wrong. Resolve its exact weekly document/period from the retained audit before use; do not assume it remains latest.

## Checklist

Each row has an independent platform status; unexecuted or partly covered scope remains `NR`. Record evidence even for a discrepancy found by static inspection; static inspection alone cannot pass a platform. Unless a row says otherwise, select from the named pack and use the source hierarchy above.

### NAV — Navigation, help and credits

AppShell, all27 routes, credits/image-library and redirect routes.

| Check ID | Priority | Action / data point | Exact assertion / oracle | WEB | ANDROID | IOS | Evidence / issue |
|---|---|---|---|---|---|---|---|
| NAV-01 | P0 | Visit all five main destinations from home and from credits. | Correct route, heading and active tab; taps work after scroll and after an overlay closes; no stale screen remains above the next route. | NR | PARTIAL | PARTIAL | IOS:6 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:6 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| NAV-02 | P0 | Open product, input, market, reference and source detail; use back. | Returns to the correct originating list/search context without changing the selected identity or losing all applied filters. | NR | NR | NR | — |
| NAV-03 | P0 | Move across each deep link and reload. | Route ID resolves to its own entity; missing/invalid ID gives an explicit not-found/error state, never another entity's cached data. | NR | PARTIAL | PARTIAL | IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:1 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| NAV-04 | P1 | Inspect desktop sidebar, mobile bottom bar and headers. | Same five destinations and correct labels; no safe-area/keyboard obstruction; last content can scroll clear of navigation. | PARTIAL | PARTIAL | PARTIAL | IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:1 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:1 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| NAV-05 | P1 | Visit /auth, /settings and /map. | Redirect to /saved, /sources and /markets respectively without loops, false login or dead links. | PASS | PARTIAL | PARTIAL | WEB desktop: core-baseline/report.json; all3redirects reached correct destination without loop. Native unrun. IOS:3 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:3 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| NAV-06 | P1 | Visit /coffee and /product/cafe-pergamino-seco. | Both resolve to the same FNC identity/data; distinct entry routes do not create conflicting saved state. | NR | NR | NR | — |
| NAV-07 | P1 | Follow source/help, logo/home and saved links from every shell placement. | Exact destination works; no overlay intercepts later navigation; focused control remains accessible. | NR | NR | NR | — |
| NAV-08 | P1 | Match every image-credit entry to image-library metadata. | Title, author, license text, license URL and origin URL match; imagery is labelled illustrative where applicable, not source proof of a variety. | PARTIAL | PARTIAL | PARTIAL | IOS:3 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:3 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:1 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| NAV-09 | P1 | Open external image/source links and return. | External target is the displayed publisher/license; app resumes without losing filters or becoming stuck on a loading overlay. | NR | PARTIAL | PARTIAL | IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:1 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| NAV-10 | P1 | Use keyboard/accessible names for search, tabs, selects and dialogs. | Actual control name matches the data edited; focus returns after close; status/error messages are reachable without guessing icons. | NR | NR | NR | — |

### HOM — Home and global search

Home, SearchBox, unified catalog/display helpers; packs P and R.

| Check ID | Priority | Action / data point | Exact assertion / oracle | WEB | ANDROID | IOS | Evidence / issue |
|---|---|---|---|---|---|---|---|
| HOM-01 | P0 | Open home with a fresh data request. | Four suggested card values/names/units/date/source match returned catalog identities; no hardcoded earlier release values. | NR | PARTIAL | PARTIAL | IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:1 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| HOM-02 | P0 | Search coffee, cacao, banana, rose/flower and one input-like nonproduct term. | Available product/reference families are reachable from unified catalog; absent product gives an honest empty search, not a fabricated suggestion. | NR | PARTIAL | PARTIAL | IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:1 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| HOM-03 | P0 | Tap a suggestion using the real touch target. | Correct href/identity opens; same-name official variants cannot resolve to the first unrelated product ID. | NR | PARTIAL | PARTIAL | IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:1 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| HOM-04 | P1 | Enter an accented, uppercase and whitespace-variant name. | Search behavior is consistent with displayed normalization; no duplicate suggestions caused by casing alone. | NR | NR | NR | — |
| HOM-05 | P1 | Submit free text instead of selecting a suggestion. | /products receives exact query and visible search/filter state; back returns usable home. | NR | NR | NR | — |
| HOM-06 | P1 | Compare home farm invitation to active stored farm. | Name/municipality-dependent prompt refers to selected farm, not a previously selected or placeholder record. | NR | NR | NR | — |
| HOM-07 | P1 | Break one image in an isolated session and reload. | Accessible fallback appears without changing price/name or covering neighboring cards; no browser broken-image text overlap. | NR | NR | NR | — |
| HOM-08 | P0 | Force catalog503 then retry home. | Error is visible; retry fetches and repopulates real data; no empty successful page or undefined-field exception. | NR | NR | NR | — |

### CAT — Unified product catalog and saved products

CatalogView, ProductCard, catalog.ts; packs P/R/H.

| Check ID | Priority | Action / data point | Exact assertion / oracle | WEB | ANDROID | IOS | Evidence / issue |
|---|---|---|---|---|---|---|---|
| CAT-01 | P0 | Reconcile complete unfiltered catalog identity set with API. | Every eligible family/name is reachable; load-more does not impose a hidden48-reference ceiling; distinct identity and saved_key remain unique. | NR | PARTIAL | PARTIAL | IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:1 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| CAT-02 | P0 | Inspect each P sample card and open its href. | Name, exact currency/unit/basis/market/date and price agree with the selected detail; monthly cards must not open default city-package prices. | NR | PARTIAL | PARTIAL | IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:1 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| CAT-03 | P0 | Compare same-name reference variants. | Different currency, unit, basis, quality/segment or market stay separate; no unsafe averaged card or overwritten React identity. | NR | NR | NR | — |
| CAT-04 | P0 | Apply a department and clear it. | Only geographically verified rows survive; excluded nonregional count/reason is truthful; global/international prices are not relabelled as departmental. | NR | NR | NR | — |
| CAT-05 | P1 | Combine category, currency, department and free text. | Visible chips/controls equal effective filters and result count; clearing one leaves others intact; dependent selections do not trap valid results. | NR | PARTIAL | PARTIAL | IOS:6 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:6 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| CAT-06 | P1 | Search all family/variety/package terms in manifest. | search_terms, presentation and units find expected identities without requiring navigation through a hidden source gateway. | NR | PARTIAL | PARTIAL | IOS:6 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:6 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| CAT-07 | P1 | Scroll first24 cards down/up repeatedly then load more. | Card image/body/price/footer rectangles stay inside their card; coffee/tomato cards do not paint stale content onto neighbors; inspect screenshots, not bounds alone. | NR | PARTIAL | PARTIAL | IOS:2 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:2 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| CAT-08 | P1 | Load all pages and compare distinct identity count. | No skipped/duplicated entries; displayed total equals filtered dataset, not merely currently rendered cards. | NR | PARTIAL | PARTIAL | IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:1 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| CAT-09 | P1 | Open a filtered detail then return. | Query/category/currency/department and usable scroll context restored; card price still corresponds to its exact href filters. | NR | NR | NR | — |
| CAT-10 | P0 | Save canonical DANE, FNC and official-reference cards. | Existing canonical saved IDs remain valid; official keys use distinct reference identity; heart state matches detail and /saved. | NR | NR | NR | — |
| CAT-11 | P1 | Toggle saves twice and restart the app/browser. | Original state restored; no duplicate favorite; one platform's local favorites are not claimed synced to another platform. | NR | PARTIAL | PARTIAL | IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:1 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| CAT-12 | P1 | Apply filters in /saved with one hidden favorite. | Empty filtered result explains filter mismatch; saved record is retained and returns when filter clears. | NR | NR | NR | — |
| CAT-13 | P0 | Check old-only product and monthly-summary-only product. | Both can be found and opened with a real source/date; retained data is not silently dropped because a recent canonical card is absent. | NR | NR | NR | — |
| CAT-14 | P1 | Inspect last-date and market-count labels. | They use correct selection/observation date and latest-day reporting count; do not imply every family was observed on global latestDate. | NR | NR | NR | — |
| CAT-15 | P1 | Fail a filtered request while prior catalog exists. | Loading/error state keeps requested filters visible; old prices are not presented as results for the new department. | NR | NR | NR | — |

### PRD — Product detail: current price, history and market list

filteredProduct, PriceChart, MarketList, classification and additional references; packs P/H/M.

| Check ID | Priority | Action / data point | Exact assertion / oracle | WEB | ANDROID | IOS | Evidence / issue |
|---|---|---|---|---|---|---|---|
| PRD-01 | P0 | For each monthly/city/milk/mill sample reconcile top card. | Price equals eligible latest-date selection for exact series/market/presentation/units/region; date and count come from that same set. | PARTIAL:WEB-01 fixed | PARTIAL | PARTIAL | 917f browser1440/390/412: exact monthly tomato3454, milk2120.98→2121,3city packages and3mill samples pass. Full product pack not yet signed off. ANDROID:22 scoped field checks; IOS:22 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:22 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| PRD-02 | P0 | Choose a city range with unequal min/max. | Current point is arithmetic midpoint of package range, labelled calculated; printed min/max stay literal and not confused with per-kg equivalents. | PARTIAL | PARTIAL | PARTIAL | ANDROID:12 scoped field checks; IOS:12 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:12 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| PRD-03 | P0 | Switch market while retaining same package/unit. | Top card, history, market list, map and source all change consistently; a slow old request cannot replace new selection. | PARTIAL | PARTIAL | PARTIAL | ANDROID:5 scoped field checks; IOS:5 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:5 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| PRD-04 | P0 | Change series and presentation, then units. | Dependent options reset safely; every selectable option has matching quotes; normalized whitespace/case never creates a dead choice. | PARTIAL | PARTIAL | PARTIAL | ANDROID:15 scoped field checks; IOS:15 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:15 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| PRD-05 | P0 | Select an explicit catalog link with region='' and history=all. | URL overrides stored department as intended and keeps exact source series/package; historical-only detail opens rather than showing unrelated recent data. | PARTIAL | PARTIAL | PARTIAL | ANDROID:12 scoped field checks; IOS:12 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:12 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| PRD-06 | P0 | Validate milk and rice units. | Milk remains COP/litre; mill's original COP/tonne price/min/max divide by1000 consistently for kg display; source retains original basis. | PARTIAL | PARTIAL | PARTIAL | ANDROID:12 scoped field checks; IOS:12 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:12 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| PRD-07 | P0 | Check classification for city sample. | Full stored category_path (e.g. Frutas > Cítricos) agrees with exact city PDF/classification; corrected classification is not replaced by stale category text. | PARTIAL | PARTIAL | PARTIAL | ANDROID:3 scoped field checks; IOS:3 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:3 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| PRD-08 | P1 | Open product with no classification record. | Honest category fallback; no invented hierarchy or borrowed neighboring-product classification. | NR | NR | NR | Earlier city-original history checks were mis-taggedPRD-08; remapped toPRD-09/10 without changing predicates. No missing-classification UI specimen has run. |
| PRD-09 | P0 | Compare all history points with API/source. | Dates are ordered chronologically in graph, no future rows, no mixing source series/package/currency or duplicate revised observations. | PARTIAL | PARTIAL | PARTIAL | ANDROID:22 scoped field checks; IOS:22 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:22 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| PRD-10 | P0 | Open Ver datos en tabla. | Values sort numerically descending; ties sort newest first; values/units/dates exactly match plotted observations after display rounding. | PARTIAL | PARTIAL | PARTIAL | ANDROID:17 scoped field checks; IOS:17 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:17 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| PRD-11 | P1 | Inspect empty, one-point, flat and long history. | No NaN/Infinity chart bounds or missing single point; available historical range is reachable and not a misleading truncated claim. | NR | NR | NR | — |
| PRD-12 | P1 | Touch/hover selected chart points and inspect accessible text. | Tooltip/title gives correct date/value for the touched point; no neighboring index mismatch on mobile. | NR | NR | NR | — |
| PRD-13 | P0 | Compare latest card to market list including older market dates. | Current mean uses reporting markets on current date only; older market entries are visibly marked as older, not averaged into today's card. | NR | NR | NR | — |
| PRD-14 | P1 | Sort markets high/low and expand/collapse beyond six. | Numeric order, row count and source links remain correct; no hidden duplicate/skipped markets. | NR | NR | NR | — |
| PRD-15 | P0 | Open source from current card and historical/market row. | Exact document/page/locator corresponds to displayed quote and date; not merely newest file for the product. | PARTIAL | PARTIAL | PARTIAL | ANDROID:2 scoped field checks; IOS:2 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:2 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| PRD-16 | P1 | Expand Más precios y fuentes disponibles. | Matched monthly summary/weekly/other published references remain reachable with their own currency/unit/basis; no unsafe merge into main current price. | NR | NR | NR | — |
| PRD-17 | P1 | Switch price/supply then return. | Price selection remains explicit; supply period has its own visible scope, not falsely constrained by a price presentation. | NR | NR | NR | — |
| PRD-18 | P1 | Inspect generic product detail actions. | Removed generic transport-cost calculator is absent; navigation/source/map controls remain usable without that panel. | PARTIAL | PARTIAL | PARTIAL | ANDROID:2 scoped field checks; IOS:2 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:2 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |

### COF — FNC coffee values and calculator

CoffeeDetail, /api/coffee, FNC bulletin/workbook and exchange; pack P/FNC.

| Check ID | Priority | Action / data point | Exact assertion / oracle | WEB | ANDROID | IOS | Evidence / issue |
|---|---|---|---|---|---|---|---|
| COF-01 | P0 | Compare FNC top price and history latest. | Exact published date and factor94 COP/carga125kg; per-kg value equals carga/125; no USD coffee index substitution. | NR | PARTIAL | PARTIAL | IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:1 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| COF-02 | P0 | Compare previous observation and change badge. | Previous distinct dated quote used; correct sign/percent; missing previous shown as missing, not0%. | NR | NR | NR | — |
| COF-03 | P0 | Check each branch in selected bulletin and expand list. | Branch price/date/name/source match FNC table; absent branches are not filled with national estimates; no older bulletin overwrites newer branch values. | NR | NR | NR | — |
| COF-04 | P0 | Select at least three published yield factors including94 and an endpoint. | Calculator selects the actual factor row and its date, with correct price; arbitrary unsupported factor cannot silently use another factor. | NR | PARTIAL | PARTIAL | IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:1 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| COF-05 | P0 | Calculate1carga,125kg and10arrobas. | All equal125kg; reference total equals quantity×unitKg/125×selected factor price. | NR | PARTIAL | PARTIAL | IOS:3 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:3 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| COF-06 | P0 | Enter positive buyer offer and costs. | Gross offer uses same 125 kg basis, net subtracts total costs once; above/below reference difference compares gross with gross and labels private input. | NR | NR | NR | — |
| COF-07 | P1 | Leave buyer offer blank. | Reference-before-costs and reference-less-costs remain clearly differentiated; blank offer is not a zero-price buyer quote. | NR | NR | NR | — |
| COF-08 | P1 | Try zero/negative/blank/too-large quantity, negative costs and invalid offer. | Validation suppresses invalid result; no negative unit conversion or stale valid total under invalid inputs. | NR | NR | NR | — |
| COF-09 | P0 | Inspect TRM source/date and coffee stale warning. | Exchange remains COP/USD and independently dated; quote older than declared threshold visibly stale, not current by fetch time. | NR | PARTIAL | PARTIAL | IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:1 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| COF-10 | P1 | Save coffee, open map and return from source. | Same coffee identity retained; source factor/branch pages correct; no general wholesale package applied to FNC. | NR | NR | NR | — |
| COF-11 | P1 | Open coffee supply tab with no comparable series. | Honest absence of pergamino arrivals, no substitution with unrelated roasted/cherry coffee. | NR | NR | NR | — |
| COF-12 | P1 | Compare buyer/factor disclaimers and cost reference. | National reference, actual Almacafé delivery quote, private offer and historical cost study remain distinct. | NR | PARTIAL | PARTIAL | IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:1 scoped field checks pass; executed-matrix-field-crosswalk.json. |

### INP — Input catalog, detail and historical coverage

Inputs, InputDetail, published_input_price and published_input_municipal_price; packs I/H.

| Check ID | Priority | Action / data point | Exact assertion / oracle | WEB | ANDROID | IOS | Evidence / issue |
|---|---|---|---|---|---|---|---|
| INP-01 | P0 | Enumerate all input categories and first/middle/last sample IDs. | Full eligible category/name set reachable after load-more/search; no silent cap or merging of distinct commercial products. | NR | NR | NR | — |
| INP-02 | P0 | Compare card name/presentation/brand/registration/product_line. | Identity matches archived row; ICA registration remains literal; missing brand/registration is not inferred from product name. | PARTIAL | PARTIAL | PARTIAL | ANDROID:51 scoped field checks; IOS:51 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:51 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| INP-03 | P0 | Compare department card price/date/previous. | Correct department mean and publication date; source/local decimal parsing and variation arithmetic correct. | PARTIAL | PARTIAL | PARTIAL | ANDROID:57 scoped field checks; IOS:57 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:58 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| INP-04 | P0 | Switch to municipal coverage and select location. | Municipality plus department shown; municipal price is not department average; scope persists into detail/map/comparison hrefs. | PARTIAL | PARTIAL | PARTIAL | ANDROID:7 scoped field checks; IOS:7 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:7 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| INP-05 | P0 | Open an input from a filtered card. | Top value, geography, presentation/brand and source agree with chosen card; no automatic switch to another department. | PARTIAL | PARTIAL | PARTIAL | ANDROID:25 scoped field checks; IOS:25 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:25 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| INP-06 | P1 | Apply name/category/department filters together. | Result count and chips match effective filters; clearing category or query does not silently reset location. | NR | NR | NR | — |
| INP-07 | P0 | Inspect two commercial variants sharing a name. | Presentation, brand, registration and product_line prevent unsafe consolidation; map/comparison choose same ID. | PARTIAL | PARTIAL | PARTIAL | ANDROID:25 scoped field checks; IOS:25 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:25 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| INP-08 | P0 | Reconcile history and table. | Same input and geography/scope across dates; graph chronological and table prices descending; no mixed package sizes. | PARTIAL | PARTIAL | PARTIAL | ANDROID:67 scoped field checks; IOS:67 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:67 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| INP-09 | P0 | Attempt oldest retained period/history deep link. | Historical data remains reachable or a concrete capability gap is recorded; do not mark pass if a hardcoded recent-only mode silently ignores history=all. | PASS | PARTIAL | PARTIAL | 917f browser1440/390/412: Iniciador full94months reaches2018; recent/full controls and descending history tested. WEB-02 fixed; prices manifest full-history case. ANDROID:10 scoped field checks; IOS:10 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:10 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| INP-10 | P1 | Expand all region/municipality comparisons and change order. | All reported locations appear with proper values/dates/units and source; no stale detail after selecting a new location. | NR | NR | NR | — |
| INP-11 | P1 | Switch scope where the chosen ID has no quote. | Honest empty result and recoverable controls; no zero price, forged municipality or hidden fallback to different scope. | NR | NR | NR | — |
| INP-12 | P0 | Open map and comparison from input detail. | Scope, department, municipality and commercial identity match visible detail; later changes visibly reflected. | NR | NR | NR | — |
| INP-13 | P0 | Open historical input source. | Exact archived PDF/workbook row includes product, presentation, location, price, month; link does not jump to unrelated current edition. | PARTIAL | PARTIAL | PARTIAL | ANDROID:32 scoped field checks; IOS:32 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:32 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| INP-14 | P1 | Test all returned nonchemical categories and service-like entries. | Units/basis remain literal; not every input is given a pesticide photo, dose recommendation or per-kg label. | PARTIAL | PARTIAL | PARTIAL | ANDROID:25 scoped field checks; IOS:25 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:27 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| INP-15 | P1 | Inspect missing registration/date/previous price. | Missing values are labelled, not zero-filled or converted to an invalid date. | NR | NR | NR | — |
| INP-16 | P1 | Navigate to complementary summaries and electricity then back. | Input filters remain usable; source summaries are not represented as sale prices for a specific municipality. | NR | NR | NR | — |

### MKT — Market lists and details

markets/marketDetail, MarketPrices; packs M/P.

| Check ID | Priority | Action / data point | Exact assertion / oracle | WEB | ANDROID | IOS | Evidence / issue |
|---|---|---|---|---|---|---|---|
| MKT-01 | P0 | Reconcile market identity set and list cards. | Name, city, department, product_count, last price date and supply date match API; no false coordinates or duplicate market IDs. | NR | PARTIAL | PARTIAL | IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:1 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| MKT-02 | P1 | Search accented city/market and apply department. | Count/filter chips reflect both conditions; exact same market opens from search, product list and map. | NR | PARTIAL | PARTIAL | IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:1 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| MKT-03 | P0 | Open six market details including nonstandard municipality/mill. | Header belongs to selected market; market-specific price rows preserve series, package, unit and date. | PARTIAL | PARTIAL | PARTIAL | ANDROID:1 scoped field checks; IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:1 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| MKT-04 | P0 | Expand full market price list. | All available rows accessible; numeric ordering stable; no arbitrary first-page cap presented as full list. | PARTIAL | PARTIAL | PARTIAL | ANDROID:1 scoped field checks; IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:1 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| MKT-05 | P0 | Follow product detail from a market quote. | Link preserves market, series, presentation, units and history basis, not just product ID. | PARTIAL | PARTIAL | PARTIAL | ANDROID:1 scoped field checks; IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:1 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| MKT-06 | P1 | Open a market with prices but no supply, then reverse. | Independent availability shown; absence of arrivals does not hide prices or imply closed market. | NR | NR | NR | — |
| MKT-07 | P1 | Open market map and inspect point. | Coordinates locate curated market/city, labels match; missing coordinates omitted/explained rather than plotted at0,0. | NR | NR | NR | — |
| MKT-08 | P0 | Launch A/B comparison from market. | Market A is the selected market; choices exclude incompatible series/identity and show effective selections. | PARTIAL | PARTIAL | PARTIAL | ANDROID:1 scoped field checks; IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:1 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| MKT-09 | P1 | Check source and supplier disclaimers. | Wholesale quotes are not live offers, stock or farmer payment guarantees; dates remain explicit. | NR | NR | NR | — |

### CMP — Market and input comparison arithmetic

ComparisonWorkspace/rows/sources, comparison-math.ts; packs M/I.

| Check ID | Priority | Action / data point | Exact assertion / oracle | WEB | ANDROID | IOS | Evidence / issue |
|---|---|---|---|---|---|---|---|
| CMP-01 | P0 | Select A and B with three known matching rows. | Only product ID+normalized presentation+units+unit+series+brand+registration+product_line matches are compared. | NR | NR | NR | — |
| CMP-02 | P0 | Independently calculate difference and percent for each matched sample. | Difference=B−A; percent=(B−A)/A×100; displayed wording/colors agree with direction and reference denominator. | PARTIAL | PARTIAL | PARTIAL | ANDROID:1 scoped field checks; IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:1 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| CMP-03 | P0 | Check an unmatched product from A. | B/difference/percent stay unavailable; row is not coerced to zero or omitted from unmatched count. | PARTIAL | PARTIAL | PARTIAL | ANDROID:1 scoped field checks; IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:1 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| CMP-04 | P0 | Check category/subcategory/all-product totals. | Simple mean of matched per-product percentages, not percent difference of incompatible totals; unmatched excluded; counts exact. | PARTIAL | PARTIAL | PARTIAL | ANDROID:2 scoped field checks; IOS:2 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:2 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| CMP-05 | P0 | Choose Promedio de Colombia. | Each comparable latest location contributes once; national mean has another location beyond A; sample evidence exposes included markets and date range. | PARTIAL | PARTIAL | PARTIAL | ANDROID:1 scoped field checks; IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:1 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| CMP-06 | P0 | Compare same-date vs latest-date modes. | Same-date mode requires exact observed dates; latest mode shows true mixed date range; older quotes not relabelled current. | PARTIAL | PARTIAL | PARTIAL | ANDROID:1 scoped field checks; IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:1 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| CMP-07 | P1 | Swap A/B and recompute. | Sign/value changes with new denominator; percent is not merely negated; visible names and sources swap correctly. | NR | NR | NR | — |
| CMP-08 | P0 | Filter category, presentation, units and text. | Displayed row summary/overall mean recomputes from visible comparable population, or clearly identifies any broader scope; chips match all active constraints. | PARTIAL | PARTIAL | PARTIAL | ANDROID:1 scoped field checks; IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:1 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| CMP-09 | P0 | Switch department and municipality input scope. | Locations, names and identity basis update; stale A/B from another scope cannot drive a false comparison. | NR | NR | NR | — |
| CMP-10 | P1 | Filter to one product via detail link. | Exact product preserved; clear-product control returns full available comparison without losing A/B. | NR | NR | NR | — |
| CMP-11 | P1 | Sort by difference, A price, B price, name and matched-only. | Numerical order verified independently; missing B handled consistently; table/card counts agree with active mode. | NR | NR | NR | — |
| CMP-12 | P1 | Expand comparison sources and per-row quote evidence. | Each A/B/national constituent has correct source, date, market, price, min/max where present; source buttons do not open the wrong side. | PARTIAL | PARTIAL | PARTIAL | ANDROID:2 scoped field checks; IOS:2 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:2 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| CMP-13 | P1 | Load remaining rows beyond initial limit. | Entire filtered set appears without duplicate identity or changing totals. | NR | NR | NR | — |
| CMP-14 | P0 | Compare kg vs litre/unit,25kg vs50kg, monthly vs city. | No match/average across incompatible bases; presentation normalization never changes physical quantity. | PARTIAL | PARTIAL | PARTIAL | ANDROID:1 scoped field checks; IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:1 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| CMP-15 | P1 | Force empty/error response and retry. | A/B and all filters remain visible; no stale successful summary under new selection; retry restores exact selected comparison. | NR | NR | NR | — |

### MAP — Price/supply map overlays

ColombiaMap, /api/explore/map, Overlay; packs P/I/M.

| Check ID | Priority | Action / data point | Exact assertion / oracle | WEB | ANDROID | IOS | Evidence / issue |
|---|---|---|---|---|---|---|---|
| MAP-01 | P0 | Open map from product with all active filters. | Requested/effective product, region, series, market, presentation, units/history appear in map chips and API. | PARTIAL | PARTIAL | PARTIAL | ANDROID:2 scoped field checks; IOS:2 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:2 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| MAP-02 | P0 | Tap a price marker/department feature. | Prices appear in a popup, not only a detached list; popup values, unit, date and source equal API points. | PARTIAL | PARTIAL | PARTIAL | ANDROID:1 scoped field checks; IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:1 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| MAP-03 | P0 | Compare package-priced and per-unit samples. | Popup retains correct package quantity or normalized basis; legend/currency cannot label a package price COP/kg. | NR | NR | NR | — |
| MAP-04 | P1 | Change series/presentation/units in overlay. | Options and colors/points refresh consistently; old popup removed before new points appear. | NR | NR | NR | — |
| MAP-05 | P0 | Open input map in both scopes. | Only selected commercial ID/location scope/category/search contributes; popup geography and price match detail. | NR | NR | NR | — |
| MAP-06 | P1 | Inspect multiple quotes in a popup. | Descending numeric values with matching market/source per row; scrolling works within mobile popup. | NR | NR | NR | — |
| MAP-07 | P1 | Select a region with no values. | Sin dato/empty explanation shown; no zero-filled heat-map color or fabricated point. | NR | NR | NR | — |
| MAP-08 | P1 | Switch price/supply mode. | Units change to arrivals/tonnes as appropriate; price presentation filters are not falsely described as constraining supply. | NR | NR | NR | — |
| MAP-09 | P0 | Check picker identities. | Unmapped official/global references are excluded from map-supported picker; no invented Colombian coordinates for international quotations. | NR | NR | NR | — |
| MAP-10 | P1 | Open source and market from popup, then return/close. | Correct quote/market reached, underlying page remains intact; closing returns focus and unlocks scrolling/navigation. | NR | NR | NR | — |
| MAP-11 | P1 | Pan/zoom repeatedly and rotate native device. | Map controls remain usable; popup is within visible area and safe inset; no blocking invisible overlay or leaked prior map. | NR | NR | NR | — |
| MAP-12 | P1 | Fail tiles/boundaries/data separately. | Clear recoverable error/no-data state; no claim a blank rendered basemap proves absence of prices. | NR | NR | NR | — |

### SUP — Supply quantities and full retained month selector

SupplyPanel, supply-sql/explore; packs H/M/P.

| Check ID | Priority | Action / data point | Exact assertion / oracle | WEB | ANDROID | IOS | Evidence / issue |
|---|---|---|---|---|---|---|---|
| SUP-01 | P0 | Open supply for a product and for a market. | Effective product/market and selected month explicit; API only returns matching arrivals, no price or stock claim. | PARTIAL | PARTIAL | PARTIAL | ANDROID:3 scoped field checks; IOS:3 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:4 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| SUP-02 | P0 | Recompute selected month total from all rows. | Displayed tonnes=sum(quantity_kg)/1000 with correct rounding; no double counting duplicates/revised originals. | PASS | PARTIAL | PARTIAL | WEB desktop: Jan2019/Jan2020/Aug2026Armenia displayedtonnes equal independentwhole-rowkg sums/1000. dane-native-originals-baseline. ANDROID:3 scoped field checks; IOS:3 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:3 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| SUP-03 | P0 | Select every retained2019/2020 month in manifest. | All twelve per year reachable when present; old month remains selected and returns correct source year rather than recent default. | PASS | PARTIAL | PARTIAL | 917f browser1440/390/412: all24graph month selections/date/totals/source links pass; focused15assertions confirm fully enabled month controls. Native evidence remains separate. ANDROID:27 scoped field checks; IOS:27 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:27 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| SUP-04 | P1 | Select earliest/latest/December/January periods. | Chronological bar data and reverse-chronological dropdown align; month never shifts by timezone or year boundary. | PARTIAL | PARTIAL | PARTIAL | ANDROID:3 scoped field checks; IOS:3 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:3 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| SUP-05 | P0 | Reconcile one selected row with original monthly source ranges. | Food, market, quantity_kg, first_reported_on, observed_on, reporting_days match; original row ranges retained. | PARTIAL | PARTIAL | PARTIAL | ANDROID:3 scoped field checks; IOS:3 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:3 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| SUP-06 | P0 | Select partial latest month. | Dates and days show actual coverage; totals not annualised or completed; note distinguishes partial reports. | NR | NR | NR | — |
| SUP-07 | P1 | Tap historical graph bar. | Bar highlight, dropdown, summary, list and source all switch to exactly that month. | PARTIAL | PARTIAL | PARTIAL | ANDROID:24 scoped field checks; IOS:24 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:24 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| SUP-08 | P1 | Inspect supply controls at390/412 and native keyboard state. | Month selector is full-width/readable; no hidden history toggle required to reach retained periods; active month shown during loading/error. | NR | NR | NR | — |
| SUP-09 | P0 | Open Comprobar cantidad for an old month. | Evidence uses exact document/food/market/month and matching quantity, not current-year generic source. | PARTIAL | PARTIAL | PARTIAL | ANDROID:1 scoped field checks; IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:1 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| SUP-10 | P1 | Query unsupported coffee/variety and zero-result period. | Honest no comparable series; no inference of zero stock and no substitution with broader variety. | NR | NR | NR | — |
| SUP-11 | P1 | Click product/market from a supply row. | Correct canonical mapping only when known; unmatched food remains literal text rather than wrong product link. | NR | NR | NR | — |

### REF — Official reference catalogs, identities and historical prices

official-references.ts, official catalog current view, OfficialPrice; pack R/H.

| Check ID | Priority | Action / data point | Exact assertion / oracle | WEB | ANDROID | IOS | Evidence / issue |
|---|---|---|---|---|---|---|---|
| REF-01 | P0 | Enumerate publishers, categories, series, units and currencies from full API. | Every returned family has at least one UI specimen; pagination/search can reach all eligible identities, not just first48. | NR | NR | NR | — |
| REF-02 | P0 | Compare official card to detail and raw original. | quote_key/name/market/basis/currency/unit, date and price agree; no COP conversion silently applied to USD or other currency. | PARTIAL | PARTIAL | PARTIAL | ANDROID:2 scoped field checks; IOS:10 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:2 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| REF-03 | P0 | Inspect current, previous, middle and oldest eligible dates. | History preserves same identity; correct latest original/parser review precedence; old replay cannot roll back current value. | NR | NR | NR | — |
| REF-04 | P0 | Verify min/max and statistic. | Published mean remains literal; midpoint label appears only when explicitly derived; weekly333/533/418 must never display433 as mean. | PARTIAL | PARTIAL | PARTIAL | ANDROID:1 scoped field checks; IOS:2 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:1 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| REF-05 | P0 | Verify weekly period bounds. | Start/end and weekly frequency match printed week; cross-month/year range is not coerced into daily/monthly date. | PARTIAL | PARTIAL | PARTIAL | ANDROID:1 scoped field checks; IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:1 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| REF-06 | P0 | Inspect cattle methodology boundary and pork terciles. | Mean/maximum and superior/medio/inferior bases remain separate clearly labelled identities; zero/blank terciles are reviewed, not zero prices. | NR | NR | NR | — |
| REF-07 | P0 | Inspect palm regulated reference and international indicators. | Basis explicitly distinguishes regulatory/reference/import/market indicator from Colombian farm transaction; currency/unit/source remain visible. | PARTIAL | PARTIAL | PARTIAL | ANDROID:1 scoped field checks; IOS:5 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:1 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| REF-08 | P0 | Inspect USDA ranges/quality/origin/variety/mostly values. | Exact literal dimensions preserved; range midpoint distinct from mostly interval; ambiguous clipped source text not presented as verified quote. | NR | NR | NR | — |
| REF-09 | P0 | Open all-history selector and table. | Graph/table contain retained dates for selected quote; descending-price/default and latest-date alternate sort are correct; old-source evidence links remain exact. | NR | PARTIAL | PARTIAL | IOS:4 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:4 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| REF-10 | P1 | Expand Fuente y método. | Published unit, quality, origin, grade, period, trend, note and methodology labels match details; hidden irrelevant object metadata does not leak implementation data. | NR | NR | NR | — |
| REF-11 | P0 | Inspect monthly-summary-only reference and standard product extra reference. | Synthetic summary identity is stable; product/city/unit/source match; exact literal starred names preserved without guessed variety mapping. | NR | NR | NR | — |
| REF-12 | P1 | Filter reference list by publisher, currency/category/search and change page. | Total/count/options and visible chips match; pagination resets after filter change; no duplicate/missing identities. | NR | NR | NR | — |
| REF-13 | P0 | Open reviewed/withdrawn quote or invalid key. | Excluded from published catalog; source review remains viewable without republishing invalid value; explicit404/error for absent identity. | NR | NR | NR | — |
| REF-14 | P1 | Save official detail and reopen from /saved. | reference-prefixed key maps to same quote, not canonical DANE ID; history controls remain usable. | NR | NR | NR | — |

### DLY — Daily bulletin screen

/daily and daily_price; pack P/H/E.

| Check ID | Priority | Action / data point | Exact assertion / oracle | WEB | ANDROID | IOS | Evidence / issue |
|---|---|---|---|---|---|---|---|
| DLY-01 | P0 | Compare header date to every displayed daily row. | Uses latest eligible report day; no mixed dates/future rows or misleading fetch-time date. | PASS | PARTIAL | PARTIAL | 917f browser1440/390/412: latestSep25 header and431 rows match original-source day; native columns require their own reports. ANDROID:1 scoped field checks; IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:1 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| DLY-02 | P0 | Check five product/market/unit price rows. | Exact native monetary value/unit/source page; egg/unit and litre exceptions not converted by assumption. | PARTIAL | PARTIAL | PARTIAL | 917f browser1440/390/412: all431literal product/market/kg prices match independent original oracle; this grid has no litre/unit exception, so those additional specimens remain NR. ANDROID:1 scoped field checks; IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:1 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| DLY-03 | P0 | Check positive, negative, zero and null variation. | Signs/percent values match official previous-market-day basis; null labelled Sin variación reportada, not0%. | PASS | PARTIAL | PARTIAL | 917f browser1440/390/412: all431variation/null fields and display match independent workbook oracle, with positive/negative/zero/missing cases. ANDROID:1 scoped field checks; IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:1 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| DLY-04 | P1 | Search product and filter plaza. | All matching rows counted; price order within product descending; selections remain visible and do not mix monthly variety series. | PARTIAL | PARTIAL | PARTIAL | ANDROID:4 scoped field checks; IOS:4 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:4 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| DLY-05 | P1 | Open daily source and supply bulletin link. | Both use correct daily document/alias/page; bulletin arrivals are not current stock. | PARTIAL | PARTIAL | PARTIAL | ANDROID:2 scoped field checks; IOS:2 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:2 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| DLY-06 | P1 | Retry failed daily request and follow regional/offers links. | Navigation works, selection/error state honest, no placeholder daily prices. | NR | NR | NR | — |

### CTY — City report screen and package equivalence

/regional, latestRegionalPrices, regional_classification; pack P/M/E.

| Check ID | Priority | Action / data point | Exact assertion / oracle | WEB | ANDROID | IOS | Evidence / issue |
|---|---|---|---|---|---|---|---|
| CTY-01 | P0 | Compare latest report of each selected city. | Each card has its own actualprinted date/round; not all relabelled to newest national ZIP date. | PARTIAL | PARTIAL | PARTIAL | ANDROID:2 scoped field checks; IOS:2 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:2 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| CTY-02 | P0 | Inspect product, full category path, presentation and quantity. | Exact printed classification and package retained; wrapped names/markets not truncated or joined with a neighbor. | PARTIAL | PARTIAL | PARTIAL | ANDROID:1 scoped field checks; IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:1 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| CTY-03 | P0 | Recompute displayed equivalent. | min/max divided by explicit package quantity only when unit known; no equivalence for ambiguous quantity/unit. | PARTIAL | PARTIAL | PARTIAL | ANDROID:1 scoped field checks; IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:1 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| CTY-04 | P0 | Inspect rounds including unpublished zero second round. | Valid positive rounds retained separately; all-zero unquoted round excluded from sale-price cards. | PARTIAL | PARTIAL | PARTIAL | ANDROID:2 scoped field checks; IOS:2 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:2 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| CTY-05 | P1 | Search, select market and load beyond36 ranges. | Counts and distinct source locator rows match all filtered data; no row losses at limit boundaries. | PARTIAL | PARTIAL | PARTIAL | ANDROID:2 scoped field checks; IOS:2 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:2 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| CTY-06 | P0 | Follow city product link. | Correct market, city series, presentation and quantity-unit open with matching package price; department preference cannot silently remove it. | PARTIAL | PARTIAL | PARTIAL | ANDROID:1 scoped field checks; IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:1 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| CTY-07 | P0 | Open corrected sibling-date source and retained review. | Original wrong-date member stays reviewed; verified alternate member priced on its own printed date; no blanket ZIP-date override. | NR | NR | NR | — |
| CTY-08 | P1 | Open PDF source at listed page. | Actual city PDF retained inside parentZIP; title/date/round and price match, with archive provenance accessible. | PARTIAL | PARTIAL | PARTIAL | ANDROID:1 scoped field checks; IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:1 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |

### AUX — Complementary monthly/input/electricity data

/data-references, input_reference_row/historical monthly summary; pack I/R/E.

| Check ID | Priority | Action / data point | Exact assertion / oracle | WEB | ANDROID | IOS | Evidence / issue |
|---|---|---|---|---|---|---|---|
| AUX-01 | P0 | Switch summary, electricity and wholesale kinds. | Visible heading, units/details/source basis change; date/category/page reset safely; no previous-kind rows under new title. | PARTIAL | PARTIAL | PARTIAL | ANDROID:4 scoped field checks; IOS:4 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:4 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| AUX-02 | P0 | Check input-summary min/max and location counts. | They are min/max of municipal averages and reported variation counts, not a retail quote; source columns remain distinct. | PARTIAL | PARTIAL | PARTIAL | ANDROID:1 scoped field checks; IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:1 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| AUX-03 | P0 | Check electricity supplier and every shown stratum. | Tariff, month, currency/kWh and subsidy/contribution labels match exact source; same provider's strata are not collapsed. | PARTIAL | PARTIAL | PARTIAL | ANDROID:6 scoped field checks; IOS:6 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:6 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| AUX-04 | P0 | Check monthly wholesale price and percent variation. | Product/city/unit/price/date exact; percent rows are not mistaken for monetary prices; negative/text decimal percentages retained accurately. | PARTIAL | PARTIAL | PARTIAL | ANDROID:2 scoped field checks; IOS:2 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:2 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| AUX-05 | P1 | Select older month across year boundary. | Explicit year respected, month list correct; no rollover inferred from today's year. | PARTIAL | PARTIAL | PARTIAL | ANDROID:1 scoped field checks; IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:1 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| AUX-06 | P1 | Page beyond60 rows then change query/category/month. | No duplicate/skipped records, total correct, page resets; latest revision per exact identity wins without losing source evidence. | PARTIAL | PARTIAL | PARTIAL | ANDROID:2 scoped field checks; IOS:2 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:2 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| AUX-07 | P0 | Open source for each kind and an older row. | Exact sheet/row/page/JSON details correspond to selected provider/stratum/product/city/month. | PARTIAL | PARTIAL | PARTIAL | ANDROID:6 scoped field checks; IOS:6 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:6 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |

### LOC — Mi finca location, farm records and geographic identity

LocationWorkspace, FarmContext, FarmEditor/FarmLocation; pack F/N.

| Check ID | Priority | Action / data point | Exact assertion / oracle | WEB | ANDROID | IOS | Evidence / issue |
|---|---|---|---|---|---|---|---|
| LOC-01 | P0 | Start without stored farm or pin. | No fabricated farm coordinates; municipal reference is distinct from exact pin; explicit instructions to choose location. | NR | NR | NR | — |
| LOC-02 | P0 | Choose two distinct exact map pins. | Stored/displayed coordinates equal selected point to stated precision; method=pin; new weather/spatial request uses new coordinates. | NR | NR | NR | — |
| LOC-03 | P0 | Use real native GPS permission allow/deny. | Allow preserves actual returned coordinates/accuracy/method; deny provides actionable manual/map alternative without resetting prior pin. | NR | NR | NR | — |
| LOC-04 | P0 | Change municipality for agricultural references with pin set. | Reference municipality updates but exact pin and retained farm administrative/crop/budget records are not silently moved/overwritten. | NR | NR | NR | — |
| LOC-05 | P1 | Pan map/search place without confirming a pin. | Explored center is not saved as farm; Volver a mi pin restores stored point and appropriate label. | NR | NR | NR | — |
| LOC-06 | P0 | Enter manual valid, partial, nonfinite and out-of-Colombia coordinates in reachable editor. | Both coordinates required; invalid inputs rejected; no NaN/0,0 default; explicitly stated geographic bounds enforced. | NR | NR | NR | — |
| LOC-07 | P1 | Verify place suggestions with same municipality name in different departments. | Correct ID/department/coordinates chosen; accented name search works; center remains described as reference. | NR | NR | NR | — |
| LOC-08 | P0 | Switch saved farm A/B and direct /farm/[id]. | Name, pin, accuracy, reference context and associated crops/budgets stay with correct ID; previous farm weather not flashed as current. | NR | NR | NR | — |
| LOC-09 | P1 | Reload/restart after changing location. | Same exact pin restored; six-decimal display consistent; saved-name/method visible; no duplicate farm created on every mount. | NR | NR | NR | — |
| LOC-10 | P1 | Open /plan with empty profile and submit editor. | Department/municipality, crop, variety, area, stage, planting/flowering, irrigation, elevation persist only after valid submit. | RETIRED | RETIRED | RETIRED | Legacy farm editor no longer routed; empty-profile reference selection covered in AGR. Original stored farm data remains retained. |
| LOC-11 | P1 | Validate area/elevation against declared bounds and allocated crops. | Area positive and not below allocated total; altitude0–6000m; invalid edits preserve previous valid record. | NR | NR | NR | — |
| LOC-12 | P1 | Test legacy/malformed storage in isolated profile. | Existing legacy copy retained; migration does not erase crops/plans; error explains unreadable/unwritable storage. | NR | NR | NR | — |
| LOC-13 | P1 | Switch zone and finance tabs after entering assumptions. | Within-session assumptions remain as documented; tabs do not unexpectedly reinitialize valid selections or change farm identity. | NR | NR | NR | — |
| LOC-14 | P1 | Verify location privacy statement against behavior. | Pin saved locally; coordinates sent only for requested public-data queries; no claim of cloud syncing farm/private assumptions. | NR | NR | NR | — |

### WEA — Current weather, hourly and daily forecast

FarmWeather, PointForecast, weather-data and archived Open-Meteo response; pack W/F.

| Check ID | Priority | Action / data point | Exact assertion / oracle | WEB | ANDROID | IOS | Evidence / issue |
|---|---|---|---|---|---|---|---|
| WEA-01 | P0 | Compare current temperature, apparent temperature, humidity. | Values and °C/% units match same current response; null shows Sin dato, not0; name/pin correct. | NR | PARTIAL | PARTIAL | IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:1 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| WEA-02 | P0 | Compare precipitation interval, amount, wind and gust. | Interval seconds divided by60 for displayed minutes; amount mm and wind/gust km/h not swapped or treated as daily totals. | NR | PARTIAL | PARTIAL | IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:1 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| WEA-03 | P0 | Inspect weather code/description/icon and day/night field. | Text matches code; missing/unknown status not presented as known sunny conditions; imagery does not contradict unavailable data. | NR | NR | NR | — |
| WEA-04 | P0 | Reconcile next24 hourly entries. | Future timestamps only, chronological and Bogotá timezone; corresponding temperature, probability, mm, wind and code use same array index. | NR | PARTIAL | PARTIAL | IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:1 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| WEA-05 | P0 | Reconcile next7 daily entries. | Dates≥Bogotá today; max/min°C, probability%, rainmm, max wind match indexed source; no UTC day shift near midnight. | NR | PARTIAL | PARTIAL | IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:1 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| WEA-06 | P1 | Switch hours/days and horizontally scroll. | No disappearing values, overlap or hidden final day/hour; units and horizon remain explicit. | NR | NR | NR | — |
| WEA-07 | P0 | Change exact pin while old request pending. | Old location's result never shown under new farm name/coordinates; request cancellation/remount prevents cross-farm data leak. | NR | NR | NR | — |
| WEA-08 | P0 | Inspect requested vs model coordinates and elevation in source. | Rounded/grid model point differentiated from exact farm pin; fetched_at/current observation time not confused. | NR | PARTIAL | PARTIAL | IOS:2 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:2 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| WEA-09 | P0 | Test30min fetch age/60min current-observation age/stale flag. | Outdated warning appears at stated thresholds; retained values labelled last available, not Ahora without warning. | NR | NR | NR | — |
| WEA-10 | P0 | Test retained response older than24h. | Current/forecast values hidden behind refresh message; no expired work guidance shown as current. | NR | NR | NR | — |
| WEA-11 | P1 | Tap refresh, background/resume and reconnect. | Refresh actually requests latest data; disabled state during request;15min cadence/visibility/online behavior does not create request storms. | NR | NR | NR | — |
| WEA-12 | P0 | Simulate failed refresh with existing data. | Error and outdated label shown together; previous reading not falsely fresh; retry restores normal state when successful. | NR | NR | NR | — |
| WEA-13 | P1 | Inspect absent current block but valid forecast. | Clear message, forecast still usable; no crash reading current.interval or missing array. | NR | NR | NR | — |
| WEA-14 | P0 | Open weather source. | Exact archived response, time, units, requested/model point and full JSON downloadable; source describes model estimates, not a station measured at farm. | NR | PARTIAL | PARTIAL | IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:1 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| WEA-15 | P1 | Change device timezone independently of Bogotá. | Same calendar day/hour in app and source interpretation; local device timezone does not move observations. | NR | NR | NR | — |

### GEO — Spatial maps: climate, soils, erosion, flood and risk

ZoneExplorer, LocationMap, spatialLayer/point/grid/tile; pack F/W/E.

| Check ID | Priority | Action / data point | Exact assertion / oracle | WEB | ANDROID | IOS | Evidence / issue |
|---|---|---|---|---|---|---|---|
| GEO-01 | P0 | Inspect all six layers:rain, temperature, risk, soil, erosion, flood. | Title, publisher, period, unit, note and legend correspond to selected layer, not leftover prior metadata. | NR | NR | NR | — |
| GEO-02 | P0 | Compare forecast vs habitual-month vs habitual-year mode. | Distinct horizons/years explicit; normal-climate raster is not current weather; forecast grid not long-term climatology. | NR | NR | NR | — |
| GEO-03 | P1 | Cycle all 12 habitual months and two year boundaries. | Correct month field/label/tile and point-query params; no off-by-one month or concatenated year error. | NR | NR | NR | — |
| GEO-04 | P0 | Inspect pin point and explored point separately. | Correct coordinate labels and matching source query; exploring does not overwrite saved pin. | NR | NR | NR | — |
| GEO-05 | P0 | Verify soil fields in an actual point response. | UCSuelo, paisaje, relieve, textura, profundidad, fertilidad, acidez, drenaje, pendiente/clima labels preserve literal source values/codes; no fabricated parcel lab result. | NR | NR | NR | — |
| GEO-06 | P0 | Verify erosion and flood readings. | tipo/clas/gra/susceptible values and units/scale match source; susceptibility is not an active disaster alert. | NR | NR | NR | — |
| GEO-07 | P0 | Inspect point with zero/multiple map units. | Zero means no coverage, not safe/apt; multiple polygons shown distinctly without choosing an arbitrary single record. | NR | NR | NR | — |
| GEO-08 | P0 | Independently calculate rain grid aggregation. | All-days value sums valid forecast daily rain; chosen day uses exact index; any missing required value yields no data rather than treating null as0. | NR | NR | NR | — |
| GEO-09 | P0 | Independently calculate temperature grid aggregation. | All-days value is maximum daily high, not mean/sum; chosen day correct; legend units°C. | NR | NR | NR | — |
| GEO-10 | P0 | Check severe-weather rule boundary fixtures. | Rain≥20mm or wind≥40km/h or high≥35°C or low≤2°C flags; null input yields no data; label explicitly planning rule, not official alert. | NR | NR | NR | — |
| GEO-11 | P1 | Change forecast step, day, opacity and viewport. | Grid/source queries use intended parameters; opacity affects drawing only, not numeric values; grid model point distinguished from query center. | NR | NR | NR | — |
| GEO-12 | P1 | Verify map legend/color and no-data category. | Numeric/color bins correspond to actual layer; null values not assigned low-risk/low-price color. | NR | NR | NR | — |
| GEO-13 | P0 | Open exact point/grid source and download. | Preserved response contains requestcoordinates, layer/month/step, time and actual records; map screenshots alone are insufficient provenance. | NR | NR | NR | — |
| GEO-14 | P1 | Fail tile and point services independently. | Error/no-coverage messages distinct; navigation/pin/other layers remain recoverable; no false scientific conclusions from a blank map. | NR | NR | NR | — |
| GEO-15 | P1 | Native touch pan/zoom/place search/GPS. | Map recognizes intended gesture; entering text does not pan/save a random pin; landscape/safe-area controls remain tappable. | NR | NR | NR | — |

### CRP — Crop, suitability and soil references

CropOptions/FarmData; UPRA/EVA, suitability and AGROSAVIA originals; pack F.

| Check ID | Priority | Action / data point | Exact assertion / oracle | WEB | ANDROID | IOS | Evidence / issue |
|---|---|---|---|---|---|---|---|
| CRP-01 | P0 | Reconcile selected municipality metadata. | Exact municipal ID/name/department, source and coordinates; duplicate names cannot join data from another department. | NR | PARTIAL | PARTIAL | IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:1 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| CRP-02 | P0 | Check crop/variety/cycle/physical-state/year. | Literal reported system preserved; permanent/transitory and production year distinguish current plan from historical reference. | NR | PARTIAL | PARTIAL | IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:1 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| CRP-03 | P0 | Compare plantedha, harvestedha, productiont and yieldkg/ha. | Numeric values match source; yield conversion handles tonnes×1000/harvestedha, null denominator not0/Infinity. | NR | PARTIAL | PARTIAL | IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:1 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| CRP-04 | P0 | Check high+medium suitability hectares and denominator. | Sum exact eligible classifications for correct crop-map keys; percentage denominator is mapped area, not whole finca or municipality by assumption. | NR | PARTIAL | PARTIAL | IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:1 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| CRP-05 | P0 | Test month/semester change for papa, maíz, cebolla. | Correct s1/s2 maps selected; banana export, Hass, rice secano distinctions preserved; unsupported system gets no fabricated suitability. | NR | NR | NR | — |
| CRP-06 | P1 | Change crop search and expand beyond first9. | Counts/order match suitableha then harvestedha; all eligible varieties remain reachable. | NR | NR | NR | — |
| CRP-07 | P0 | Compare soil sample count, pH sample count, median and central range. | Correct municipality/source/filter and sample population; median/quartiles not extrema; no claim these are tests of exact farm pin. | NR | PARTIAL | PARTIAL | IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:1 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| CRP-08 | P1 | Inspect oldest/newest soil analysis dates and missing soil. | Dates match samples; absence explicit; no fertility prescription/dose inferred from municipal data. | NR | PARTIAL | PARTIAL | IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:1 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| CRP-09 | P0 | Open crop, suitability, soil sources. | Exact source document, row/map/reference year and municipality selectors preserved; raw physical units visible. | NR | PARTIAL | PARTIAL | IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:1 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| CRP-10 | P1 | Select a crop to financial analysis. | Same crop code/variety/physical state carried over; cannot silently choose first different crop after async response. | RETIRED | RETIRED | RETIRED | Manual calculator interaction removed by user direction; prior execution is historical evidence only. Public data and preservation obligations continue in AGR/CRP/CAL/STA. |

### FIN — Retired manual clean-sheet costs and profitability

Former CleanSheet UI removed. Original numerical cases remain documented as retired; data-source obligations continue in AGR.

| Check ID | Priority | Action / data point | Exact assertion / oracle | WEB | ANDROID | IOS | Evidence / issue |
|---|---|---|---|---|---|---|---|
| FIN-01 | P0 | Enter area2ha, yield1000kg/ha, loss10%, price2000COP/kg. | Sale quantity1800kg and gross revenue3,600,000COP; labels distinguish per ha vs total. | RETIRED | RETIRED | RETIRED | Manual calculator interaction removed by user direction; prior execution is historical evidence only. Public data and preservation obligations continue in AGR/CRP/CAL/STA. |
| FIN-02 | P0 | Add costs300000+200000COP/ha, delivery100000, commission5%. | Production1,000,000;commission180,000;total1,280,000;profit2,320,000; break-even1,100,000/(1800×0.95)=643.2748538COP/kg before rounding. | RETIRED | RETIRED | RETIRED | Manual calculator interaction removed by user direction; prior execution is historical evidence only. Public data and preservation obligations continue in AGR/CRP/CAL/STA. |
| FIN-03 | P0 | Assign300000cost before harvest and200000 at harvest. | Cash before harvest600000COP; changing timing does not change total cost/profit. | RETIRED | RETIRED | RETIRED | Manual calculator interaction removed by user direction; prior execution is historical evidence only. Public data and preservation obligations continue in AGR/CRP/CAL/STA. |
| FIN-04 | P0 | Inspect cost/kg and margin. | Production cost/kg=1,000,000/1800;profit margin=2,320,000/3,600,000×100; do not substitute markup denominator. | RETIRED | RETIRED | RETIRED | Manual calculator interaction removed by user direction; prior execution is historical evidence only. Public data and preservation obligations continue in AGR/CRP/CAL/STA. |
| FIN-05 | P0 | Reconcile waterfall/table/summary. | Start revenue, each area-scaled cost, delivery and commission lead exactly to profit; negative outcome labelled loss; no area multiplication twice. | RETIRED | RETIRED | RETIRED | Manual calculator interaction removed by user direction; prior execution is historical evidence only. Public data and preservation obligations continue in AGR/CRP/CAL/STA. |
| FIN-06 | P0 | Load a matching nominal cost template then edit one item. | Correct crop, region, system, year, yield/source; per ha values retained; historical nominal study not claimed inflation-adjusted/current quote. | RETIRED | RETIRED | RETIRED | Manual calculator interaction removed by user direction; prior execution is historical evidence only. Public data and preservation obligations continue in AGR/CRP/CAL/STA. |
| FIN-07 | P0 | Mark benchmark comparable/uncomparable and change crop. | Eligibility/acknowledgment respected; unsupported system does not acquire benchmark comparison or wrong cost source. | RETIRED | RETIRED | RETIRED | Manual calculator interaction removed by user direction; prior execution is historical evidence only. Public data and preservation obligations continue in AGR/CRP/CAL/STA. |
| FIN-08 | P0 | Switch manual/history price mode. | Manual price is private assumption; historical mode requires comparable product/unit, market, month and explicit confirmation before results. | RETIRED | RETIRED | RETIRED | Manual calculator interaction removed by user direction; prior execution is historical evidence only. Public data and preservation obligations continue in AGR/CRP/CAL/STA. |
| FIN-09 | P0 | Test coffee, rice, cane, maize and bean matching. | FNC carga converted to pergaminoCOP/kg; paddy not milledrice, cane not panela, greenbean not drybean; no incomparable USD/litre/unit quote in kg budget. | RETIRED | RETIRED | RETIRED | Manual calculator interaction removed by user direction; prior execution is historical evidence only. Public data and preservation obligations continue in AGR/CRP/CAL/STA. |
| FIN-10 | P0 | Independently calculate historical seasonal projection. | For≥3complete 12-month years, ratios targetmonth/currentlatestmonth; interpolate25/50/75percentiles then multiply latest price; invalid/incomplete years excluded. | RETIRED | RETIRED | RETIRED | Manual calculator interaction removed by user direction; prior execution is historical evidence only. Public data and preservation obligations continue in AGR/CRP/CAL/STA. |
| FIN-11 | P0 | Apply discount10% and uncertainty20%. | Historical price reduced once; low/typical/high quantities scale0.8/1/1.2 and appropriate price quantiles; manual price stays manual without hidden historical discount. | RETIRED | RETIRED | RETIRED | Manual calculator interaction removed by user direction; prior execution is historical evidence only. Public data and preservation obligations continue in AGR/CRP/CAL/STA. |
| FIN-12 | P0 | Test missing/zero/negative/nonfinite numbers and100% loss/commission. | Invalid results suppressed; zero allowed where meaningful cost, not where positive area/yield/price required; no stale result or NaN/Infinity. | RETIRED | RETIRED | RETIRED | Manual calculator interaction removed by user direction; prior execution is historical evidence only. Public data and preservation obligations continue in AGR/CRP/CAL/STA. |
| FIN-13 | P1 | Test all0costs, one positive cost, extreme allowed inputs. | Behavior is explicit and consistent with declared validation; arithmetic remains finite; no implausible default silently inserted. | RETIRED | RETIRED | RETIRED | Manual calculator interaction removed by user direction; prior execution is historical evidence only. Public data and preservation obligations continue in AGR/CRP/CAL/STA. |
| FIN-14 | P1 | Change month/product/market with an in-flight history request. | Confirmation, source links and projected values reset correctly; no last market's price attached to next crop. | RETIRED | RETIRED | RETIRED | Manual calculator interaction removed by user direction; prior execution is historical evidence only. Public data and preservation obligations continue in AGR/CRP/CAL/STA. |
| FIN-15 | P0 | Export scenario JSON from valid result. | Inputs, computed values, sensitivity, municipality, crop/physical state, period, assumptions and source DIDs match displayed scenario; no stale source in manual mode. | RETIRED | RETIRED | RETIRED | Manual calculator interaction removed by user direction; prior execution is historical evidence only. Public data and preservation obligations continue in AGR/CRP/CAL/STA. |
| FIN-16 | P1 | Switch tabs and reload page after entering assumptions. | Within-session persistence works; reload behavior matches stated session-only promise; not falsely represented as saved/cloud-synced budget. | RETIRED | RETIRED | RETIRED | Manual calculator interaction removed by user direction; prior execution is historical evidence only. Public data and preservation obligations continue in AGR/CRP/CAL/STA. |
| FIN-17 | P1 | Compare crop permanent vs transitory period. | Annual productive period vs single cycle is labelled; establishment not treated as annual operating return. | RETIRED | RETIRED | RETIRED | Manual calculator interaction removed by user direction; prior execution is historical evidence only. Public data and preservation obligations continue in AGR/CRP/CAL/STA. |

### BUD — Retired budget editor; saved data retained

/plan, CropBudget, FarmContext; pack F. Separate from current clean-sheet.

| Check ID | Priority | Action / data point | Exact assertion / oracle | WEB | ANDROID | IOS | Evidence / issue |
|---|---|---|---|---|---|---|---|
| BUD-01 | P0 | Resolve farm/crop/tab URL parameters. | Correct farm and managed crop selected; malformed IDs handled explicitly; does not overwrite another farm's scenario. | RETIRED | RETIRED | RETIRED | Manual calculator interaction removed by user direction; prior execution is historical evidence only. Public data and preservation obligations continue in AGR/CRP/CAL/STA. |
| BUD-02 | P0 | Enter same manual arithmetic as FIN and uncertainty0. | Quantity, revenue, fees, production+extra costs, profit and break-even independently reconcile in all three scenarios. | RETIRED | RETIRED | RETIRED | Manual calculator interaction removed by user direction; prior execution is historical evidence only. Public data and preservation obligations continue in AGR/CRP/CAL/STA. |
| BUD-03 | P0 | Switch cycle, annual and establishment periods. | Period label/year/cost basis preserved; figures not silently reinterpreted as same duration. | RETIRED | RETIRED | RETIRED | Manual calculator interaction removed by user direction; prior execution is historical evidence only. Public data and preservation obligations continue in AGR/CRP/CAL/STA. |
| BUD-04 | P0 | Load reference costs and require review acknowledgment. | Sourceyear/system/page and per ha amounts explicit; editing/confirmation state not carried incorrectly to another template. | RETIRED | RETIRED | RETIRED | Manual calculator interaction removed by user direction; prior execution is historical evidence only. Public data and preservation obligations continue in AGR/CRP/CAL/STA. |
| BUD-05 | P0 | Save named scenario then reopen/restart. | All area, yield, loss, uncertainty, cost timing, price mode/product/market/month, commission/discount and source DIDs restored exactly. | RETIRED | RETIRED | RETIRED | Manual calculator interaction removed by user direction; prior execution is historical evidence only. Public data and preservation obligations continue in AGR/CRP/CAL/STA. |
| BUD-06 | P0 | Apply a scenario to managed crop. | Correct crop's area/yield/budget update; other crops/farms preserved; allocated area remains consistent with total farm area. | RETIRED | RETIRED | RETIRED | Manual calculator interaction removed by user direction; prior execution is historical evidence only. Public data and preservation obligations continue in AGR/CRP/CAL/STA. |
| BUD-07 | P1 | Retain more than saved-display limit. | Any visible limit/retention behavior documented; no unnoticed deletion of unrelated real scenarios; test only disposable records. | RETIRED | RETIRED | RETIRED | Manual calculator interaction removed by user direction; prior execution is historical evidence only. Public data and preservation obligations continue in AGR/CRP/CAL/STA. |
| BUD-08 | P1 | Remove one QA scenario or clear QA list. | Confirmation/target scope correct and no other farm's stored scenario key removed; restore original storage afterward. | RETIRED | RETIRED | RETIRED | Manual calculator interaction removed by user direction; prior execution is historical evidence only. Public data and preservation obligations continue in AGR/CRP/CAL/STA. |
| BUD-09 | P1 | Change legacy schema/corrupt JSON in isolated storage. | Safe migration/fallback, original backup retained when specified; no crash or cross-farm data reuse. | RETIRED | RETIRED | RETIRED | Manual calculator interaction removed by user direction; prior execution is historical evidence only. Public data and preservation obligations continue in AGR/CRP/CAL/STA. |
| BUD-10 | P0 | Open budget price/cost/yield/history source links. | Match exact selected assumptions and study pages; source dates/physical state visible rather than a generic latest product document. | RETIRED | RETIRED | RETIRED | Manual calculator interaction removed by user direction; prior execution is historical evidence only. Public data and preservation obligations continue in AGR/CRP/CAL/STA. |

### CAL — Calendars, dates and planning advice boundaries

CropBudget calendar/phenology; WeeklyPlan component reachability noted above.

| Check ID | Priority | Action / data point | Exact assertion / oracle | WEB | ANDROID | IOS | Evidence / issue |
|---|---|---|---|---|---|---|---|
| CAL-01 | P0 | Inspect all 12monthly calendar percentages for crop/activity. | Match exact UPRA departmental crop/activity/year row; totals/rounding retain source; not monthly prices or current optimum dates. | NR | PARTIAL | PARTIAL | IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:1 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| CAL-02 | P0 | Switch crop to no calendar. | Explicit no integrated calendar, never borrowed from another crop/department. | NR | NR | NR | — |
| CAL-03 | P1 | Compare calendar planting vs harvesting activity. | Labels and month columns align; no shifted header from source merged cells. | NR | NR | NR | — |
| CAL-04 | P0 | Enter coffee flowering date and altitude-specific guide. | Window starts from flowering, not sowing; add correct source-supported day bounds; leapday/year rollover calculated correctly. | RETIRED | RETIRED | RETIRED | Manual calculator interaction removed by user direction; prior execution is historical evidence only. Public data and preservation obligations continue in AGR/CRP/CAL/STA. |
| CAL-05 | P1 | Leave flowering date/altitude absent. | No invented exact harvest prediction; explanation and source still reachable. | RETIRED | RETIRED | RETIRED | Manual calculator interaction removed by user direction; prior execution is historical evidence only. Public data and preservation obligations continue in AGR/CRP/CAL/STA. |
| CAL-06 | P1 | Use manual sowing/start date and known cycle length. | End date equals exact day addition; invalid dates/durations rejected; clearly user simulation. | RETIRED | RETIRED | RETIRED | Manual calculator interaction removed by user direction; prior execution is historical evidence only. Public data and preservation obligations continue in AGR/CRP/CAL/STA. |
| CAL-07 | P0 | Open calendar/Cenicafé evidence. | Correct department/year/source row and study page; historical reference labelled, not official forecast for this farm. | NR | PARTIAL | PARTIAL | IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:1 scoped field checks pass; executed-matrix-field-crosswalk.json. |

### OFF — Private buyer/supplier offers

/offers, offerResult; disposable user-input fixtures.

| Check ID | Priority | Action / data point | Exact assertion / oracle | WEB | ANDROID | IOS | Evidence / issue |
|---|---|---|---|---|---|---|---|
| OFF-01 | P0 | Compare1kg,125kg carga and12.5kg arroba quotes. | Normalize per kg once; same offered physical quantity and price basis across sale/purchase results. | NR | PARTIAL | PARTIAL | IOS:2 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:2 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| OFF-02 | P0 | Enter100kg accepted at2000COP/kg,10%deduction,10000transport,5000packaging,5000fees. | Gross200000, deduction20000, cost20000, net160000, net/kg1600; purchase total200000/purchasekg2000; remainder equals available−100. | NR | PARTIAL | PARTIAL | PARTIAL WEB:160000sale/200000purchase exactoperandstestpassed; broaderoffercomparisons deferredforDANE. IOS:3 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:3 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| OFF-03 | P0 | Compare two offers with different quantities/costs. | Best-sale selection uses net/kg and best-purchase uses actual delivered cost/kg; total-payment differences not mislabeled as unit competitiveness. | NR | PARTIAL | PARTIAL | IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:1 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| OFF-04 | P0 | Set expired, today-expiring and future offers. | Bogotá date boundary correct; expired excluded from recommendation but retained visibly; payment delay remains separate from price. | NR | PARTIAL | PARTIAL | IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:1 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| OFF-05 | P1 | Add/remove QA offer and edit name/quality/pickup/paymentdays. | All fields attach to correct stable offer ID; never imply verified buyer/public listing. | NR | PARTIAL | PARTIAL | IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:1 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| OFF-06 | P0 | Try acceptedkg>available, blankprice, negativecost, noninteger/over365paymentdays. | Invalid offer not ranked; precise validation and no previous valid result beneath bad fields. | NR | PARTIAL | PARTIAL | IOS:2 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:2 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| OFF-07 | P1 | Restart and inspect private offer storage. | Exact entered data restored locally; no cloud/private-quote publication claim; restore pretest values. | NR | PARTIAL | PARTIAL | IOS:2 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:2 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| OFF-08 | P1 | Show fewer than two eligible offers. | No unjustified winner; expiry and invalidity reasons visible. | NR | PARTIAL | PARTIAL | IOS:2 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:2 scoped field checks pass; executed-matrix-field-crosswalk.json. |

### EVI — Source viewers, row provenance, reviews and originals

EvidenceContent/Provider, PDF/Workbook viewers and content routes; pack E and every domain above.

| Check ID | Priority | Action / data point | Exact assertion / oracle | WEB | ANDROID | IOS | Evidence / issue |
|---|---|---|---|---|---|---|---|
| EVI-01 | P0 | Open Consultar fuente from each data family. | Exact DID/locator/page/date/source matches displayed value; source title and publisher do not default to DANE for another publisher. | PARTIAL | PARTIAL | PARTIAL | ANDROID:15 scoped field checks; IOS:15 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:17 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| EVI-02 | P0 | Compare source metadata. | Original/extract/methodology kind, reference period, retrieved_at, MIME, bytes, page count, parent lineage match retained document; latest fetch is not observation date. | PARTIAL:WEB-03 fixed | PARTIAL | PARTIAL | 917f browser1440/390/412: city original now shows actual day; reviewed/corrected source notes and original MIME/parents verified for selected samples. Remaining full format/metadata pack NR. ANDROID:1 scoped field checks; IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:1 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| EVI-03 | P0 | Load real PDF at first, middle, last and linkedpage. | Canvas has completed render and visible content matches expected page; page count/selector/thumbnails correct, not blank canvas success. | PARTIAL | PARTIAL | PARTIAL | ANDROID:8 scoped field checks; IOS:8 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:8 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| EVI-04 | P1 | Use PDF next/previous, page dropdown, thumbnails, fit150%200%. | Correct page/zoom; text/figures legible; pan contained; navigation and sourceclose remain accessible. | PARTIAL | PARTIAL | PARTIAL | ANDROID:2 scoped field checks; IOS:2 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:2 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| EVI-05 | P0 | Compare PDF text mode to rendered page. | Numeric selected anchor matches printed PDF; inaccessible/scan text does not invent OCR success or replace original image. | NR | NR | NR | — |
| EVI-06 | P0 | Load XLS and XLSX including two sheets. | Actual native cells shown in read-only grid; no editable controls; rows/columns/sheet labels/order match original. | PARTIAL | PARTIAL | PARTIAL | ANDROID:7 scoped field checks; IOS:7 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:7 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| EVI-07 | P0 | Inspect formula, merged header, blank and numeric cells. | Formula display uses publisher's saved result, not recalculated invented value; blank vs0 preserved; decimal formatting does not change raw result. | PARTIAL:WEB-04 fixed | PARTIAL | PARTIAL | 917f browser1440/390/412: literal daily−2%/0%/2%, energy−60%,raw503.96 and blank fields pass. Formula/merged-cell exhaustive subset remains NR. ANDROID:2 scoped field checks; IOS:2 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:2 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| EVI-08 | P1 | Move workbook beyond100rows, lastpage and switchsheet. | Start/row count/page controls exact; stale sheet cells removed; correct end disabled; out-of-range start clamped visibly. | PARTIAL | PARTIAL | PARTIAL | ANDROID:2 scoped field checks; IOS:2 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:2 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| EVI-09 | P1 | Pan workbook horizontally and change zoom. | Last displayed column reachable; document body does not overflow; column truncation warning and full-download option truthful. | PARTIAL | PARTIAL | PARTIAL | ANDROID:1 scoped field checks; IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:1 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| EVI-10 | P0 | Inspect long original filename at390/412/native. | Full filename wraps within panel, all review notes readable; no overlay or horizontal overflow covering bottom nav. | PARTIAL | PARTIAL | PARTIAL | ANDROID:6 scoped field checks; IOS:6 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:6 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| EVI-11 | P0 | Open JSON daily-query exact locator. | Product, market, date, periodstart, mean, min, max, currency, unit, basis and resultset locator visible and match literal response. | PASS | PARTIAL | PARTIAL | WEB desktop JSONresultset[0]: brazo conhueso,ArmeniaFrigocafé,2013-04-18,mean/min/max8500COP/kg; actualdownloadSHAverified. harness-corrections+original-downloads. ANDROID:2 scoped field checks; IOS:2 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:2 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| EVI-12 | P0 | Open TXT/HTML/structured non-PDF source. | Appropriate readable evidence/text/record presentation; no fake PDF viewer or transformed file presented as original. | NR | NR | NR | — |
| EVI-13 | P0 | Download each supported format in browser and native shell. | Actual saved/shared file has original MIME/extension/bytes/SHA; response x-source-storage provesAzureBlob where applicable; successful click alone insufficient. | PARTIAL | PARTIAL | PARTIAL | PARTIAL WEB: actualsaved XLS/XLSX/PDF/JSON/ZIP hashes+MIME+Azureheaderspassed. CSV/TXT/PNGandnativeflowsremain. ANDROID:4 scoped field checks; IOS:4 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:4 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| EVI-14 | P0 | Check ZIPmember price source and parent lineage. | Downloaded PDF SHA agrees archive member, correct parentZIP visible; partial alternate recovery does not claim full missingZIP roster. | NR | NR | NR | PARTIAL WEB: downloadedSep25ZIPmemberhash equals cityPDF; parentmetadataretained. Alternatepartial2023recoveryUIstillunrun. |
| EVI-15 | P0 | Open corrected-date daily source. | Verifieddate note plus original erroneous heading preserved and corroborating official link works; raw title not silently rewritten. | PARTIAL | PARTIAL | PARTIAL | PARTIAL WEB: verified2014-02-11note,originalmisspelledheadingandcorroboratinglinkvisible; corroboratingexternalnavigationnotyetretested. ANDROID:1 scoped field checks; IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:1 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| EVI-16 | P0 | Open reviewed Decembermilk original. | Novembercontents remain visible with Decemberlink review note; invalid oldDecemberrows stay excluded; alternate realDecember evidence kept distinct. | PARTIAL | PARTIAL | PARTIAL | PARTIAL WEB: November2020workbook andDecemberreviewnotevisible; invalidDecemberpriceexclusion notnewUI-testedhere. ANDROID:4 scoped field checks; IOS:4 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:4 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| EVI-17 | P0 | Inspect reviewed cells inside otherwise valid source. | Nativevalid rows still viewable; exact current unresolved count/note shown;60Nov29cells and USDA1/36/35 anchors revalidated, not hidden or published as numeric quotes. | PARTIAL | PARTIAL | PARTIAL | PARTIAL WEB: Nov29original60reviewscountandnativegridvisible; USDA1/36/35anchors notrerununderDANEpriority. ANDROID:4 scoped field checks; IOS:4 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:4 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| EVI-18 | P0 | Open source superseded by a newer document. | Historical document viewer still shows its own eligible extracted records; no global newest-source query erases original evidence. | NR | NR | NR | — |
| EVI-19 | P0 | Open source after corrected parser supersedes an old review. | New valid locator can publish under revision rules; obsolete review no longer inflates active count; original review/history retained for audit. | NR | NR | NR | — |
| EVI-20 | P0 | Inspect OCR-backed quote. | Nativefailed page, image, retainedreading/page and final value traceable; native-readable page is not labelled OCR; ambiguity still reviewed. | NR | NR | NR | — |
| EVI-21 | P1 | Open filtered supply/crop/soil/weather evidence. | Exact food/month/municipality/coordinates/source rows respected; generic first100records never presented as requested subset. | NR | NR | NR | — |
| EVI-22 | P1 | Open missing document, bad locator or failedBlob request. | Honest404/error/retry/download guidance; no another-document fallback or empty viewer success. | NR | PARTIAL | PARTIAL | IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. ANDROID:1 scoped field checks pass; executed-matrix-field-crosswalk.json. |
| EVI-23 | P1 | Open/close source modal, fullpage and externalpublisher then back. | Underlying filters/scroll/selection preserved; body scroll/focus restored; PDF/workbook controls and bottomnav continue working. | PARTIAL | PARTIAL | PARTIAL | ANDROID:1 scoped field checks; IOS:1 scoped field checks pass; executed-matrix-field-crosswalk.json. WEB:1 scoped checks pass on8a8baf2 at1440/390/412; executed-matrix-field-crosswalk.json. |
| EVI-24 | P1 | Inspect parent/source links and download names with accents/longtext. | Encoding safe, labels legible, correct origin; no auth keys or SAS credentials exposed in screenshot/UI. | NR | NR | NR | — |
| EVI-25 | P0 | Compare original downloaded twice after revision. | DID URL still yields identical historical bytes; new sameURL revision gets its own DID; no historical file replaced behind hash. | NR | NR | NR | — |

### STA — Preferences, state boundaries and stored data

Preferences/FarmContext and native app storage; packs F/N.

| Check ID | Priority | Action / data point | Exact assertion / oracle | WEB | ANDROID | IOS | Evidence / issue |
|---|---|---|---|---|---|---|---|
| STA-01 | P0 | Snapshot/reload favorites and department. | agroamigo-preferences-v2 contains exact values; hydration does not overwrite saved data with startup empty defaults. | NR | NR | NR | — |
| STA-02 | P0 | Rapidly switch two filters with reversed response arrival. | UI shows only latest requested selection; no old price/map/weather payload wins race. | NR | NR | NR | — |
| STA-03 | P0 | Navigate/restart with existing two-farm/two-crop fixture. | Farm/crop IDs, selected IDs, plans and areas preserved; migrations retain private data and source references. | NR | NR | NR | — |
| STA-04 | P1 | Test browser storage denied/full. | Clear limitation where supported; current session remains usable; no claim unsaved settings persisted. | NR | NR | NR | — |
| STA-05 | P1 | Restore original storage after each test. | Compare serialized originals/keys; QA offers, farms, favorites and scenarios leave no user changes. | NR | NR | NR | — |
| STA-06 | P1 | Separate web browser, Android app and iOS app stores. | No assumed cloud synchronization; same local key values tested separately; crossplatform result never copies another platform PASS. | NR | NR | NR | — |
| STA-07 | P0 | Background/terminate/reopen native app. | Persisted values survive according to contract; session-only clean-sheet state not promised durable; APIrefresh yields correct latest sources. | NR | NR | NR | — |
| STA-08 | P1 | Open two tabs/windows where available. | Each filter/request remains coherent; sharedstorage behavior documented, no price under wrong visible filter. | NR | NR | NR | — |
| STA-09 | P1 | Clear only QA state then navigate all routes. | No hidden required seed state or stale selected ID preventing an empty-profile user from using app. | NR | NR | NR | — |

### NAT — Native wrapper-only integration

Installed Android MainActivity and iOS Flutter/WKWebView; pack N. WEB stays NR until explicitly N/A with reason.

| Check ID | Priority | Action / data point | Exact assertion / oracle | WEB | ANDROID | IOS | Evidence / issue |
|---|---|---|---|---|---|---|---|
| NAT-01 | P0 | Launch actual installed app and capture build/remote release. | Correct trusted Azure origin loaded; no claim desktop browser is native; native console and device screenshot recorded. | NR | NR | NR | — |
| NAT-02 | P0 | Use Android system back and iOS navigation/backgesture. | History returns correct screen and filters; no accidental exit before overlay/details close; root behavior explicit. | NR | NR | NR | — |
| NAT-03 | P0 | Open official external HTTPS source then return. | Native external browser opens intended URL; app preserves state and usable loading indicator. | NR | NR | NR | — |
| NAT-04 | P0 | Tap source download PDF/XLS/XLSX/CSV/JSON/TXT plus retained ZIP/PNG. | Android actual download/document flow and iOS native share sheet complete with correct file bytes/MIME; cancellation is not treated as WebView failure. | NR | NR | NR | — |
| NAT-05 | P0 | Export clean-sheet JSON natively. | Trusted-origin export triggers native save/share, validJSON and filename; data equals current displayed scenario; cancellation keeps app usable. | NR | NR | NR | — |
| NAT-06 | P0 | Test native location permission denied, allowed and laterrevoked. | Correct coordinate/accuracy or clear deniedstate; no lingering request or invented pin; privacy origin correct. | NR | NR | NR | — |
| NAT-07 | P1 | Open keyboard near bottom controls and rotate. | Safe areas handled; save/filter/navigation controls remain tappable; keyboard does not cover active numeric field permanently. | NR | NR | NR | — |
| NAT-08 | P0 | Lose network during mainframe load, then retry. | Native error screen/recovery works; private data preserved; app reloads trusted origin without blank white screen. | NR | NR | NR | — |
| NAT-09 | P1 | Attempt untrusted/unsupported navigation from isolated QA link. | Native shell does not execute export/download from untrusted content or navigate arbitrary local schemes; external failure communicated. | NR | NR | NR | — |
| NAT-10 | P1 | Inspect /android APK download and claims. | Downloaded artifact installable on declared minimum Android, version matches displayed demo metadata; site says local app/browser stores are separate. | NR | NR | NR | — |

### ERR — Errors, offline behavior, freshness and reader performance

Every API/UI surface; source latency and cache semantics, isolated fault fixtures only.

| Check ID | Priority | Action / data point | Exact assertion / oracle | WEB | ANDROID | IOS | Evidence / issue |
|---|---|---|---|---|---|---|---|
| ERR-01 | P0 | Cold-load every route/API family once. | Successful full content or explicit supported no-data state; record latency/status; no hidden503/undefined-field exception masked by partial shell. | NR | NR | NR | — |
| ERR-02 | P0 | Repeat catalog, product, input, reference, supply during scheduled writerload. | Frontend still serves correct data or clear retryableerror; no indefinite spinner or APIerror object treated as successful products array. | NR | NR | NR | — |
| ERR-03 | P0 | Simulate API503 for each data hookfamily then retry. | Errorvisible, selectionpreserved, old prices not relabelled, new request actually made and correct source shown after recovery. | NR | NR | NR | — |
| ERR-04 | P0 | Simulate valid empty/null arrays. | Appropriate no-data explanation with working filters; no Math.min empty Infinity, missingrows crash, or zeroprice substitution. | NR | NR | NR | — |
| ERR-05 | P0 | Submit malformedIDs, invalidcoordinates/month/step and overlongquery. | Boundedvalidation with appropriate400/404; no unrelateddata fallback, crash or internalcredential text. | NR | NR | NR | — |
| ERR-06 | P0 | Go offline after loading values. | No fresh-live claim for old data; native/web offline guidance clear; retained private state remains; no invented cached price persistence promise. | NR | NR | NR | — |
| ERR-07 | P0 | Reconnect after source publication or cacheexpiry. | New eligible revision becomes reachable after declared TTL/refresh; stale historical source remains archived and old price not silently overwritten. | NR | NR | NR | — |
| ERR-08 | P1 | Cancel navigation/filter while requests run. | No stuckdisabledcontrols, late state update to anotherpage, or noisy error for expected abort. | NR | NR | NR | — |
| ERR-09 | P1 | Break image, map tile, PDF and workbook independently. | Only affected panel fails, with usablefallback; source/download and main navigation remain accessible. | NR | NR | NR | — |
| ERR-10 | P0 | Cross Bogotá midnight with future-dated fixture. | Eligibility and displayed dates agree across catalog/detail/references; no tomorrowprice appears because UTC date advanced. | NR | NR | NR | — |
| ERR-11 | P1 | Inspect logs/response errors on all negative cases. | No secrets, connectionstrings, stacktraces or private farmdata exposed to UI; user-facingdiagnostic remains actionable. | NR | NR | NR | — |
| ERR-12 | P0 | Final regression pass after fixes. | Re-run failed IDs and neighboring sharedcomponent assertions on affected platforms; evidence links point to final release; no unsupported universal-completeness claim. | NR | NR | NR | — |

## Execution order and acceptance ledger

1. Capture releases and restore-safe state snapshots. Build the immutable sample manifest. Run NAV/HOM plus catalog/source-read smoke checks before mutating disposable local state.
2. Trace prices end-to-end: CAT → PRD/COF/INP/REF → MKT/CMP/MAP → EVI. Start with exact unit/currency/package edge cases and reviewed/old sources; perform independent source comparisons before marking UI values correct.
3. Execute supply, complementary references and every current/old period selected in the manifest. Check API counts and numeric aggregates before expensive viewer rendering.
4. Execute farm location → weather/spatial → crops/soils → current clean-sheet and legacy budget/calendar/offers. Keep municipal reference, exact pin, model point and source scale separate throughout.
5. Repeat all applicable IDs in the actual Android and iOS apps. Native-only interactions need native evidence; desktop/mobile browser results remain in WEB. Use each platform's own stored profile and restore it afterward.
6. Exercise isolated errors/offline/races and a bounded real scheduled-writer overlap. Fix concrete discrepancies, retain before/after evidence, then rerun affected/neighboring checks.

Do not end with an unexplained count of screenshots or “all works.” Publish a per-platform ledger: total/pass/fail/blocked/notrun/notapplicable, exact release/device, remaining issue IDs and coverage exclusions. Link numerical sources and original-download hashes. Any unreachable requested functionality, unsupported data family, remaining source review or native permission/share limitation remains explicit.

Existing suites to reuse as starting points, not prior PASS status: `apps/web/tests/{data,price-filters,comparisons,catalog-scrolling,supply-history,farm-location,farms,planning,weather-view,official-statistics,layout}.spec.ts`; `apps/ios/integration_test/{full_validation,catalog_validation,data_validation}_test.dart`; `apps/android/validate.cjs` plus Android instrumentation/UI artifacts. Run targeted meaningful tests after a fix; do not repeatedly load heavy endpoints without a new reason.

## Matrix totals at creation

| Group | Checks |
|---|---:|
| NAV | 10 |
| HOM | 8 |
| CAT | 15 |
| PRD | 18 |
| COF | 12 |
| INP | 16 |
| MKT | 9 |
| CMP | 15 |
| MAP | 12 |
| SUP | 11 |
| REF | 14 |
| DLY | 6 |
| CTY | 8 |
| AUX | 7 |
| LOC | 14 |
| WEA | 15 |
| GEO | 15 |
| CRP | 10 |
| FIN | 17 |
| BUD | 10 |
| CAL | 7 |
| OFF | 8 |
| EVI | 25 |
| STA | 9 |
| NAT | 10 |
| ERR | 12 |
| **Total** | **313** |

All 939 platform-status cells start as `NR`. Inventory/computation review does not certify execution.

## Thirty reusable execution scenarios

The 313 IDs are field-level assertions, **not 313 independent page launches**. Run the following 30 scenarios per applicable platform, checking multiple IDs against one captured immutable API/source sample. Existing Android 30-case and iOS full/data/catalog suites can record these IDs within their current cases; do not renumber the matrix to match an older test count. A scenario can be partial: record per-ID outcomes instead of passing its entire range after one screenshot. Batch only independent read requests and cache immutable fixture/original reads to keep execution bounded.

Use accessible roles/names first. CSS selectors below identify current components for value/bounds inspection, not a requirement to bypass real native taps. A native JavaScript assertion should read the actual loaded WebView DOM after native navigation; a hidden browser visit cannot replace it.

| Scenario | Route and entry/action | Value selectors / fields to record | Independent backend/source truth | Check IDs |
|---|---|---|---|---|
| Q01 | Home → each mainnav → credits → redirects | `nav[aria-label="Navegación móvil"]`, selected `aria-current`, `h1`, actual URL; credits author/license links | Route inventory; `image-library.json`; actual external destination | NAV-01–10, NAT-02/03 |
| Q02 | Home realtap autocomplete and submit | `Buscar un producto`, suggestion text/ID, resultingURL; first four product cards | `/api/catalog.products`: identity, id, href, name, price, unit, currency, basis; frozen sampleP/R | HOM-01–08 |
| Q03 | Products all filters and family reachability | `Departamento`,`Categoría`,`Moneda`, searchbox, applied chips, result count, card value/date/source | Full eligible `/api/catalog` set and `filters.excluded_nonregional_*`; exact source identities | CAT-01–06/08/13–15 |
| Q04 | First24card scrolling, loadmore, detail/back, saves | `.product-grid` card/image/body/footer bounds and screenshots; save `aria-pressed`, URL, storage | Captured catalog identity order and original preferences; no visual-pass inference from DOM bounds alone | CAT-07/09–12, STA-01/05/06 |
| Q05 | Product monthly selection then city package | `Tipo de precio`,`Mercado`,`Presentación`,`Unidades`, `[data-testid=current-product-price]`, chips | `/api/products/<id>`: current, filters, options, markets, classification; exact native price/classification rows | PRD-01–08/17/18 |
| Q06 | Same product history/table/all markets/source | `.price-chart`,`.chart-data tbody`,`.market-row`, expandbutton, source URL | Full history date/value pairs; independent latest date mean; each market's actual observation and locator | PRD-09–16 |
| Q07 | Milk litre and mill tonne/kg detail | Currentvalue/unit, marketoptions, range, source note | Printed milk litre and rice tonne price/min/max; divide rice by1000 only | PRD-01/06/15, MKT-03/05 |
| Q08 | FNC coffee history, branches, factors, calculator | `.coffee-big-price`, Factor select, Quantity/Unit,`.calculation-result`, TRMsource | `/api/coffee`: factors, markets, date, history, exchange; FNC bulletin and independent quantity arithmetic | COF-01–12 |
| Q09 | Inputs categories/search/variant collision | Inputcards heading, presentation, brand/ICA, date/price;coverage + department controls | Grouped `/api/planning/inputs`; eligible source-revision identity and archived row | INP-01–07/14–16 |
| Q10 | Input detail municipal/department/history/map link | `.entity-hero`, coverage select, chart/table, location rows, source/map href | `/api/explore/input`: input, regions, history; exact municipal or department source row | INP-08–13, MAP-05 |
| Q11 | Markets list → representative detail → expand | Marketcard name/city/count/date;`.entity-hero`, MarketPrices rows and filters | `/api/explore/markets`, market?id;eligible price identities and location metadata | MKT-01–09 |
| Q12 | Market A/B and national comparison | A/B controls, filterchips, summary counts, each row price/difference/percent, source expansion | `/api/compare/markets`; independently recompute identity matches, mean percent, national constituents | CMP-01–08/10–15 |
| Q13 | Inputcomparison in both scopes | Coverage, A/B, product/brand/package, matchcounts, summary | `/api/compare/inputs`; independent exact commercial identity andmunicipal/department date matching | CMP-01–15 |
| Q14 | Product/input/market map popup | Overlay,`Tipo de precio en mapa`,`Presentación en mapa`,`Unidades en mapa`,`.map-popup-quotes`, legend | `/api/explore/map`: points.value/unit/date/DID andeffectivefilters;curated coordinates | MAP-01–12 |
| Q15 | Product/market supply latest then old months | `Mes de consulta`,`.supply-summary`,`.supply-list`,`.supply-bars`, source link query | `/api/explore/supply`: rows.quantity_kg, datebounds, days, selected_period, history; original microdata ranges | SUP-01–11 |
| Q16 | Official list family filters, detail+history/source | Header `[data-price][data-currency][data-unit]`, historyselect, table, metadata definitions | `/api/references`: reference/history details; original native quoted values and review eligibility, not cache alone | REF-01–14 |
| Q17 | Daily/regional screens with unit+roundedgecases | `.input-card`, date/round, classification/package, range/equivalent, filters, count | `/api/planning/daily` andregional; source printed date/round, explicitquantity, zero-round suppression | DLY-01–06, CTY-01–08 |
| Q18 | Complementary summaries/electricity/wholesale | `Datos`,`Mes`,`Categoría`, rows.details, source links, pagination | `/api/data-references`: exact provider+stratum or product+city+unit identity; retained source cell | AUX-01–07 |
| Q19 | Farm empty → pin → reference municipality → farmB | `.location-place`, sixdecimalcoordinates, method/accuracy, statusmessage, savedfarmselect | FarmStore/profile snapshot;actual selected map/GPSpoint;municipality ID; outgoing query coordinates | LOC-01–09/12–14, STA-03 |
| Q20 | Current weather →24h→7d→refresh/stale | `section[aria-label="Tiempo y pronóstico de mi finca"]`, metrics, time/date, units, warnings | Archived `/api/planning/weather`: requested/modelpoint, current/hourly/daily arrays, fetched_at, timezones | WEA-01–15 |
| Q21 | Six spatial layers, month/year/forecast, tap point | Layer buttons,`Horizonte de la información`,`Mes habitual`,`.zone-reading`,`.zone-legend` | `/api/location/layers,point,grid,tile`;layer/valueFields, requested point, raw records, independent forecast aggregation | GEO-01–15 |
| Q22 | Expand crops, change crop/month, inspect soil | `.crop-option`, aptitude hectares, harvest/yield/year, soilsummary/source | `/api/planning/farm`: crops, suitability, soil;municipaloriginals, independent sums/percentiles | CRP-01–10 |
| Q23 | Retired manual finance scenario/waterfall/export | No current calculator UI; preserve original old reports and stored bytes | Historical FIN evidence remains traceable, not current-platform PASS | FIN-01–07/12/13/15–17 RETIRED; AGR-07/09 active |
| Q24 | Read-only historical price/seasonality | Historical table, complete-year count, descriptive index and source links | `/api/planning/seasonality`: complete years,12prices,unit; independent median month/annual-mean ratios andsource DIDs | AGR-04/05/06; former FIN/CRP-10 interactions RETIRED |
| Q25 | /plan crop references and legacy deep links | Municipality/crop selectors, exact published cost study, invalid-ID state, unchanged storage | FarmProfile/ManagedCrop resolution; native printed cost rubrics/year/region/source; exact serialized storage bytes | AGR-01/03/07/08/09; BUD/LOC-10 interactions RETIRED |
| Q26 | /plan calendars andcoffee development guidance |12-month table, activity/year, Cenicafé published development range | CalendarReference percentages and Cenicafé sourcepage; no private harvest-date calculation | CAL-01/02/03/07, AGR-02/10; CAL-04/05/06 RETIRED |
| Q27 | /offers normalized sale/purchase comparison | Offer inputs, private label, net/gross/per kg, expiry/winner, persisteddata | KnownOFF operands; unit 125/12.5 conversion;independent sale/purchase arithmetic;Bogotádate | OFF-01–08 |
| Q28 | Source PDF/XLS/XLSX/source correction/reviews | RenderedPDFcanvas, page/zoom, readonlygrid/range, sheetselect, metadata/reviewnotes | Original bytes/page/cells/formula cache;source_document/parents;current reviews anddate-resolution evidence | EVI-01–10/14–20/22–25 |
| Q29 | Source JSON/TXT, filtered records, native downloads/export | `.evidence-records dl`, native file/share/download UI, actual saved bytes/MIME | Archived original JSON/TXT andexact locator;SHA256;Azurecontentheader;scenarioinputs/results | EVI-11–13/21, NAT-01/04/05/09/10 |
| Q30 | Permissions, back, offline, races, restart, errorrecovery | Native OS dialogs, keyboard/insets, error/retry states;requested filter labels andactualreturned values | Captured storage/releases;bounded isolated fault fixtures and API requests;no production mutations | STA-02/04/07–09, NAT-02/03/06–08, ERR-01–12 |

Prioritize P0 value checks within each scenario before broader visual variants. Every group is assigned above; overlapping IDs intentionally cover entry-path and state differences. An API-level check validates the backend leg only. Finish with the actual UI field matching that same response on each platform.

## Nonexecuted component inventory and static leads

These are investigation notes, excluded from the313 platform checks and939 statuses. They are not confirmed UI failures or PASS claims.

- `WeeklyPlan.tsx` has no current route import. If restoring that screen is in scope, separately validate official advisories, completionstorage, weather rules (rain20mm, heat32°C, two days≤1mm and<30%, five days<5mm without irrigation), stale suppression andactual route reachability. Its32°C work-planning threshold is distinct from the map's35°C severe-weather rule. Keep reserved IDs `CAL-08` through `CAL-10` unused unless the screen is restored and the matrix deliberately expanded.
- Input catalog/detail code currently sets `historical=false`; INP-09 must investigate actual user reachability of retained history rather than infer support from an API parameter.
- Another audit agent identified a candidate duplicate input identity for a September2025 annual source row: populated brand/registration variant versus an older blank-metadata ID. Add exact source URL, row75346 andboth IDs to sampleI when independently confirmed; execute INP-01/02/07 and CMP identity checks before calling it resolved.
- Persisted reference/price caches and current forecasts can change during QA. Use snapshot times and document IDs, and distinguish an expected new eligible source from a rendering/identity mismatch.

## Deferred feature backlog — after data correctness

**FEATURE-BUG-REPORT (deferred; not implemented):** add an in-app bug report submission flow addressed to **ekallett@gmail.com**. Use the email implementation in `/Users/ethan/Documents/development/project-nasa-yuwe` as the implementation reference when this work starts. Keep it behind the current DANE/source correctness, extraction and cross-platform spot-check fixes. Future acceptance checks must cover the user's entered report, optional consented diagnostics, success/error/retry states and actual Android/iOS submission behavior. No email is sent and no feature is implemented by recording this TODO.

## Additional DANE all-market regression scope

`apps/web/tests/qa/dane-unscoped-city-cases.json` adds unscoped department/market, full-history cases for limónTahitíBulto24kg and moraCaja de cartón2.5kg/12.5kg. The independent22:58UTC snapshot had634/611/653 distinct dates and latest-day package means89500/22000/80375COP. All3/18 cases passed on browser at1440/390/412 and actual Android on8a8baf2; exact reports appear above. Historical city replays can increase date counts or legitimately revise old all-market means; preserve the dated raw oracle and compare the UI to the eligible population actually used by that response. Existing source-pinned exact-market proofs remain separate. Nine isolated PostgreSQL17 regressions cover date/round/revision selection, corrected/fallback classifications, whitespace variants and reviewed rows; SQL tests do not themselves pass UI columns.

The later Mi finca calculator review has now resulted in the read-only replacement below; its new checks do not reuse retired calculator assertions.

## Mi finca follow-up: manual tools retired, public references retained

The original313 IDs remain traceable.32 manual interaction checks are explicitly RETIRED: FIN-01..17, BUD-01..10, CRP-10, LOC-10 and CAL-04..06. Their former passes are not reused for the replacement. Existing CRP, soil, location/weather, CAL-01/02/03/07 and source-family obligations remain active. Ten new AGR checks below make the replacement and preservation contract explicit, for323 tracked IDs total (32 retired,291 active). The FNC quality/125kg calculation and private offer comparisons are separate features and remain in scope.

Implementation removes CleanSheet/CropBudget and calculator entry links. `/plan` and old budget deep links now provide crop data, printed calendars, nominal cost tables and historical prices. Local fixture-driven tests cover exact old storage bytes and source identity; they do not populate production or native platform statuses. Existing original documents, APIs and saved farm/budget/offer data are retained.

| Check ID | Priority | Action / data point | Exact assertion / oracle | WEB | ANDROID | IOS | Evidence / issue |
|---|---|---|---|---|---|---|---|
| AGR-01 | P0 | Open old /plan?tab=budget with exact farm/crop and the new crop-card link. | Requested crop/municipality resolve to their reference without selecting a different farm; visible legacy explanation and working Mi finca return. | PARTIAL | PARTIAL | PARTIAL | de491dcc WEB/Android/iOS exact legacy route and return; broader farm/crop-link fixtures remain local. |
| AGR-02 | P0 | Read calendar source rows. | Each activity/year and12 monthly percentages match its original; correct department/document per row; no current optimum date claim. | PARTIAL | PARTIAL | PARTIAL | Reuses CAL-01/02/03/07 source obligations. |
| AGR-03 | P0 | Expand a published cost study. | All literal COP/ha rubrics, nominal year/region/system/yield, exact sum and source page; no assumed current inflation or private farm cost. | PARTIAL | PARTIAL | PARTIAL | Replaces data-bearing subset of retired FIN/BUD. |
| AGR-04 | P0 | Change historical product/market. | Only same physical product in compatible COP/kg monthly series; no canned/pod vs dry grain merge, currency/package substitution or stale market response. | PARTIAL | PARTIAL | PARTIAL | catalog-reference-compatibility.spec.ts and reference-physical-product.spec.ts. |
| AGR-05 | P0 | Inspect a supported seasonal history. | Every monthly value/source retained;≥3 complete finite positive years support12 medians of month/annual-mean indices; no future price/income estimate. | PARTIAL | PARTIAL | PARTIAL | SeasonalChart remains a descriptive historical view. |
| AGR-06 | P0 | Inspect fewer than3 complete years. | All available complete-year monthly prices/source links still visible; explicit insufficiency and no fabricated seasonal pattern. | NR | NR | NR | farm-references.spec.ts two-year literal fixture. |
| AGR-07 | P0 | Visit /farm, /farm/id, /plan and four former calculator links. | No manual costs/profit controls or dead calculator CTA; FNC125kg/quality and private offers still work separately. | PARTIAL | PARTIAL | PARTIAL | Former links: coffee, input catalog/detail and offers. |
| AGR-08 | P0 | Open invalid farm/crop legacy IDs. | Explicit not-found/no-match state; another farm/crop is not silently substituted. | PARTIAL | PARTIAL | PARTIAL | Fixture checks unknown IDs independently. |
| AGR-09 | P0 | Navigate/change reference/reload with two existing farms and old scenarios. | Original farm/crop budgets, active IDs, scenario keys and legacy/location bytes unchanged by read-only consultation. | PARTIAL | PARTIAL | PARTIAL | de491dcc WEB/Android/iOS seeded scenario and all present farm/location bytes preserved on crop change; two-farm/reload fixture remains a separate test. |
| AGR-10 | P1 | Read coffee cost and development references. | FEPCafé source amount/date/125kg basis and Cenicafé study remain available; no farm harvest date or private profitability is invented. | PARTIAL | PARTIAL | PARTIAL | Source documents retained, old flower-date calculator retired. |
