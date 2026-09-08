# Active data and UI work

Requested September 7, 2026. Status recorded September 8 UTC. Detailed evidence: [current validation report](VALIDATION_2026-09-08.md).

Data:
- [ ] Finish the entire historical archive queue. All requested source families are implemented, retained, published and exposed to the frontend; at 05:00 UTC, 9,337 discovered assets remained queued for unattended hourly backfill. Source coverage and review exceptions are documented in the validation report.
- [x] Daily discovery of new sources and changed contents at existing URLs; permanent originals in private Azure Storage.
- [x] OCR only when ordinary PDF page / Excel sheet extraction fails; test scanned PDFs and image-only workbooks with Gemini; retain uncertainty for review.
- [x] Stress tests, cloud deployment and live evidence checks; recover missing 2022 milk prices and the full 95 MB 2020 supply workbook with bounded memory.
- [x] Expose retained supply months and their source quantity records in the frontend.

UI after data validation:
- [x] Resolve Android simulator stale-card painting: isolate native display corruption from correct WebView pixels, switch the dedicated emulator to verified host graphics, and recheck scrolling, saves, back navigation and 48 cards.
- [x] Unify agricultural products, city reports and official references in one searchable catalog; move source details into the product flow and validate both native apps.
- [x] “Ver datos en tabla”: numbers descending.
- [x] Product top card shows current price for selected market + presentation + units.
- [x] Product hierarchy from city reports, e.g. Frutas > Cítricos; preserve hierarchy in ingestion.
- [x] The same filters apply to history graph and market comparisons; show applied filters everywhere.
- [x] Read-only in-app Excel source viewer with document-viewer controls, alongside PDF viewer.
- [x] Fix bottom navigation on image credits page.
- [x] Remove transport-cost calculation from product details.
- [x] Map prices in popups instead of the list below.
- [x] Expandable full price lists on markets.
- [x] Compare market A/B/Colombia using matched product + presentation + units, category summaries and overall mean percentage difference.
- [x] Restore and improve comparable insumo comparisons; inspect May implementation/history.
- [x] Extensive iOS + Android simulator interaction, navigation, visual and filter consistency checks after final deployment. Native iOS edge-swipe remains an open validation issue; visible back links pass. See the report for exact release and test scope.
- [x] Final cleanup: organize ingestion adapters, shared filtering/comparison and source-viewer modules; remove temporary redundant indexes; add a concise code navigation guide; revalidate behavior.

Additional requested work:
- [x] Exact Mi Finca point from GPS or map placement, persisted with the active farm. Reference municipality changes preserve the pin. Weather requests use six-decimal coordinates; source resolution stays explicit.
- [x] Official alternative source adapters and price views, with currencies, units, methods and original evidence preserved. Unsupported or unreliable sources excluded.
- [x] Remote runtime configuration and Gemini secret in Azure app settings; deployment preserves existing operator configuration.
