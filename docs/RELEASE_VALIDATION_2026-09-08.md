# Release validation — 8 September 2026

The final Azure web release is `1dfa14c9b2c94ccb861160bdcdea35d1`, built at 06:00:20 UTC. Its deployment and database connection passed health verification. The hosted Android APK matches the locally built APK byte for byte (SHA-256 `83cfbb87ce23f80487ce5327f4910182f641e9055e0273053c9e850372e217ae`). The deployed ingestion worker already matched the local fingerprint `73c19706beeb4e184ad369d64def4ef93a6c0e4e26e16e4e958d4c4e08202eae`; no unnecessary worker redeployment or configuration change was made.

## Automated and source checks

- Web production build passed. Android assembly and lint passed. Flutter analysis and navigation unit testing passed.
- 124 ingestion/infrastructure checks and 36 news-pipeline checks passed. The preceding two-week news archive's structural/date/source-accounting validator passed.
- Eight final mobile-browser weather/budget checks passed. The two home/catalog checks passed on the preceding UI-identical release. Source query changes were checked independently against the live database.
- Reference-list queries now materialize one published snapshot for results, counts and options, and join source documents only for the displayed page. Five before/after comparisons preserved exact quote identities, prices, units, dates, documents, source locators, filter options and pagination, including no-result searches. Equivalent comparison requests now share normalized default keys; the tested municipal responses matched all 206 rows and 205 matched identities.

Local evidence: `artifacts/prepush-python-tests.log`, `artifacts/release-web-query-build.log`, `artifacts/prepush-android-build.log`, `artifacts/final-browser-budget-weather.log`, `artifacts/release-reference-query-validation.json`, `artifacts/release-comparison-query-validation.json`, `artifacts/final-release-health.json`.

## Installed Android app

**All 30 cases passed together on the final release**, on the dedicated Pixel 9 / Android 17 emulator (`emulator-5554`) with the installed Android WebView app. There were zero JavaScript errors and no unexpected HTTP error responses; the deliberately injected error in the recovery case is identified separately. Original local settings and network states were restored.

Coverage includes the five navigation tabs; search, autocomplete and saved selections; exact market/package prices; charts and descending tables; map filters/popups and hardware back; original PDFs, page controls, zoom and verified native downloads; Excel sheets, row navigation and download hashes; credits; full market lists; national/pair/input comparisons; currencies and international history; input location filters; coffee kg/arroba/carga arithmetic and invalid values; map layers and horizons; budgets; offers and persistence; API/offline recovery; real emulator GPS, pin persistence and municipality exploration; current weather and forecast; all retained supply months and selected historical source values; native scrolling/card painting; and the farm finance waterfall/table.

The controlled farm scenario uses 2 ha, 1,000 kg/ha, 10% unsaleable harvest and COP 2,000/kg. Both financial views agree on COP 3,600,000 revenue, COP 1,660,000 costs and COP 1,940,000 profit. The break-even calculation is COP 1,300,000 / 1,620 kg, displayed rounded to COP 802/kg. Negative area removes the calculated result and displays the incomplete-input explanation. These are temporary user-entered test assumptions, not published observations.

Evidence: `artifacts/final-android-validation/report.json` and native screenshots in that folder. Earlier failures remain in `artifacts/release-android-validation/` and `artifacts/release-android-recheck/`; they are not counted as passing runs. The harness was updated for removed period controls and compares stored/requested coordinates to the actual Android GPS reading, whose emulator output can differ slightly from its nominal test point.

## Installed iPhone app

The dedicated **AgroAmigo QA iPhone 17 Pro / iOS 26.1** simulator (`1F158206-7EB2-4687-982A-6E1C41673EFD`) exercised the real WKWebView wrapper against the same final web release. All **24 numbered functional groups** passed across two focused runs: groups 1–15 in `artifacts/final-ios-full-recheck.log`, and 16–24 in the successful `artifacts/final-ios-farm-confirmed.log`. The first log's overall failure is retained: it stopped waiting for GPS permission; it is not represented as a fully passing suite.

The first group covers prices, table ordering, map popups, both Mora packages, in-app PDF/Excel viewing, all five credits/navigation links, comparisons, municipal filters, regional detail links, currencies and history. The second verifies actual CoreLocation input and GPS provenance, reload persistence, electricity sources, international source workbook, historical 2019/2020 supply, current weather and seven-day forecasts, and both farm finance views plus negative-input handling. Local farm settings are restored by teardown.

The native permission flow requires **two approvals** on a fresh installation: the iOS app location prompt and the WKWebView site's Spanish “Permitir” prompt. Both were accepted through native simulator interactions, then the dedicated simulator received a fresh synthetic GPS fix of `1.912345,-76.123456`. No geolocation JavaScript mock was used in that run. The test's `AGRO_IOS_FARM_AND_SOURCES_ONLY=true` flag permits a focused continuation without repeating already verified price screens. Source selectors wait for the requested option to load before selecting it.

Native screenshots were visually inspected, including map/pin, prices, source viewers, weather, finance cards, waterfall and horizontally scrollable table. Flutter integration captures omit the OS status bar; Android native captures can contain a fading keyboard toolbar immediately after field entry. These are validation captures, not app marketing images.

Two additional complete iPhone suites passed on the same release. `artifacts/final-ios-data-validation.log` covers coffee arithmetic and invalid inputs, fresh daily prices, private offer calculations and persistence, injected API failure/retry, and native sharing of a historical XLS. `artifacts/final-ios-catalog-validation.log` covers native card scrolling, expanding the catalog, saved quote identity, currency filters, detail/back navigation, international history beginning in 1960, and every one of the 24 monthly supply selections in 2019–2020. Captured catalog, international reference and full-width supply screens were also visually reviewed. Final Flutter analysis passed after the integration-test additions.

The normal `lib/main.dart` app was rebuilt, installed and launched after the suites, and the dedicated simulator's synthetic GPS override was cleared. A native screenshot including the status bar confirmed the restored home screen. Additional native taps opened the product catalog and coffee detail. A further left-edge swipe did not return to the catalog; before/after captures are retained as `artifacts/final-ios-native-detail-before-swipe.png` and `artifacts/final-ios-native-after-swipe.png`. The visible back link and home tab remained usable.

## Observed limitations

Earlier concurrent cold-data runs received intermittent 503 responses for catalog/reference/input reads. Redundant reference scans and comparison request duplication were reduced, and the final complete Android run had no unexpected HTTP failures. A cold municipal input read still failed once in an iOS attempt before its successful retry. These checks do not establish a load-test SLA for the small demo database. Cold historical queries can be slow; visible error/retry behavior is verified.

Rapid iOS navigation sometimes logs canceled Next.js prefetches and falls back to normal browser navigation; the destination assertions pass. The previously documented native iOS edge-swipe issue remains separate from verified visible-back navigation; it is not claimed fixed by these changes. See the earlier [validation report](VALIDATION_2026-09-08.md) for the attempted gesture coverage.

## Spanish news pipeline

The executable collector, 95-source candidate catalog, review handoff, durable state, expiry rules and CI tests are included. A live audit attempted all 88 enabled candidates; seven restricted/non-Spanish candidates remain disabled. Three Spanish international stories were reviewed, and a conflicting OMM publication date was retained for review. [Research and per-source evidence](research/news-global-spanish-2026-09-08/README.md).

**The daily subscription-funded Luna cloud task and delivery of news into the public app are still not connected.** The output remains private research with unverified display rights. A GitHub code/build run is not a daily Luna classification job. [Activation status](automation/README.md).
