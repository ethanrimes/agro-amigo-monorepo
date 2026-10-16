# Data sources and interpretation

AgroAmigo keeps publisher, observation period, unit and source document attached to its data. Available dates depend on each publisher and the eligible records already imported. A retained original, a parsed table and a publicly displayed observation are separate stages.

## Prices and market activity

| Publisher or family | Application use | Interpretation |
|---|---|---|
| [DANE SIPSA](https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa) daily/monthly prices | Dated daily-bulletin browser and monthly product/market histories | Keep daily, monthly and city/package series distinct; do not merge varieties by similar names |
| DANE city bulletins | Package quotations and price rounds | Preserve printed market, quantity, presentation, unit and round |
| DANE daily annex ZIPs and workbooks | Original workbook members, daily date/product/market view and exact Excel-cell source links | Package ranges, daily matrices and published daily means retain their own identities and worksheet locators; publisher market names stay literal where a canonical match is unverified |
| DANE weekly bulletins | Official reference detail/history | Published weekly mean and min/max retain their own period and basis |
| DANE SIPSA-I | Input catalog and comparisons | Commercial identity includes presentation and available manufacturer/registration metadata, plus distinct commercial lines for agricultural elements; municipality and department scopes remain separate |
| DANE SIPSA-I historical department workbook | Department average input histories alongside monthly department annexes | Each row supplies its own year/month; department means remain separate from municipal quotations. Overlapping exact product/department/month observations share one published identity while original worksheets and source rows remain retained |
| DANE raw milk | Farmgate municipal prices and separate macroregional references | COP/litre; a macroregion mean never substitutes for a municipality quotation |
| DANE rice mill series | Mill-level prices and comparisons | Preserve the mill basis; tonne-to-kg conversions apply consistently to price and ranges |
| DANE SIPSA-A | Supply by food, destination market and month | Reported arrivals, not inventory; partial months retain actual reporting coverage |
| DANE daily supply summaries | Original source viewer and separately typed references | Tonnes by market and reported-market total; printed PDF columns marked `p` are provisional, unmarked columns are not assumed definitive. Missing cells are not zeroes, and summary totals are not added to the food microdata |
| DANE monthly and first-fortnight supply summaries | Source tables with market totals, food groups and percentage changes | Keep the printed reporting period and precision. Definitive three-month reports retain each month separately. An undefined percentage change from a zero baseline remains **Sin dato**, alongside the reported quantities |
| [FNC](https://federaciondecafeteros.org/estadisticas-cafeteras/) | Coffee reference, yield factors and delivery branches | Dry parchment coffee, usually COP per 125 kg load; not a verified buyer offer |
| [SFC TRM](https://www.datos.gov.co/resource/32sa-8pi3.json) | Currency context | Dated COP/USD exchange rate, not a product price |
| [Other Colombian publishers](OFFICIAL_COLOMBIA_SOURCES.md) | Cacao, palm, cattle, pigs and Corabastos references | Source-specific product, geography, unit and basis |
| [International publishers](OFFICIAL_INTERNATIONAL_SOURCES.md) | Commodity and ornamental flower references | Original currency and physical unit; no implied Colombian farmgate price |

## Mi finca and agricultural references

| Source | Application use | Limits |
|---|---|---|
| [UPRA EVA](https://www.datos.gov.co/resource/uejq-wxrr.json) | Municipal crop, production, harvested area and yield references | Published municipality/year, not a prediction for a farm |
| [UPRA calendars](https://www.datos.gov.co/resource/6nv9-uruw.json) | Historical sowing and harvest activity | Department/crop/activity percentages, not optimal planting dates |
| [UPRA SIPRA](https://sipra.upra.gov.co/) | Crop suitability context | Regional mapped classes and areas, not parcel permission or guaranteed yield |
| [AGROSAVIA soil results](https://www.datos.gov.co/resource/ch4u-f3i5.json) | Municipal soil-sample context | Laboratory sample summaries do not measure the user's soil |
| [IDEAM](https://www.ideam.gov.co/) and [IGAC](https://www.igac.gov.co/) geographic layers | Climate normals, soil mapping, erosion and flood susceptibility | Historical cartography with explicit period and scale |
| [Open-Meteo](https://open-meteo.com/en/docs) | Point and map forecasts | Model predictions; requested and model coordinates remain distinct |
| [UPRA](https://upra.gov.co/) cost studies and FEPCafé reports | Read-only published production-cost references | Nominal study-year values, region/system and unit; no automatic farm budget or profitability prediction |

Planning reference imports are dated datasets. They are not all refreshed by the recurring price worker. Weather and spatial responses have separate request-driven retention. [Mi finca documentation](MI_FINCA_DATA.md) describes the visible distinctions.

## Evidence and unsupported data

The source viewer displays original PDFs, paginated spreadsheet cells or structured records and preserves downloadable bytes. Original publisher files and generated extracts are labelled separately. Row reviews, corrected date notes and partial coverage remain visible where relevant.

Corrections to a source's displayed reporting period are saved as separate annotations with a reason and references to the original cells. The archived file and its original metadata remain unchanged; the evidence response includes both the corrected period and the annotation history.

Native extraction is preferred. Supported OCR adapters validate literal values and identities; unsupported image-only layouts remain reviewable. A source link or successful download does not establish complete numeric extraction.

OCR is used only after normal PDF or spreadsheet extraction fails. Supported image tables require two independent agreeing readings, verified periods and units, complete market coverage and reconciliation with the printed total. A table continued onto another page is published only when both pages pass these checks. Publisher spelling, rounding and imputation notes remain attached to the source.

Parser revisions retain their earlier extracted cells. The ordinary source view selects the published revision rather than displaying duplicate revisions together; an exact historical cell link still resolves its original version.

The recurring ingestion job also cleans published product names and categories before and after loading new observations. It uses a reviewed spelling dictionary and Unicode/spacing cleanup, with a recorded correction trail. The app applies the same reviewed display dictionary to categories, places and presentations, and cleans invisible characters and spacing in commercial input names. Original source text and identifiers remain intact. It does not guess brand names, merge similar varieties, or remove package sizes and registration numbers. Searches and searchable selectors ignore case and accent marks while preserving the displayed spelling.

A later official city ZIP can retain PDFs from earlier dates. Recovery uses each original PDF's printed date, market and package; it does not assign the ZIP's date to every member or claim the unavailable earlier ZIP's full coverage. Contradictory captions and prices are retained for review while independently valid tables remain eligible.

For the same product, market, package and date, product histories use the latest available price round. They do not average different rounds together. Round-specific city-report cards and the original source retain the separate rounds; a zero-price round does not supply a quotation. When DANE republishes an identical report in a later ZIP, the selected quotation may cite that later retained copy. Both archive lineages remain available.

The app does not provide a public buyer network, verified offers/payments, pesticide prescriptions, parcel-level agronomic diagnosis or live supplier inventory. Private offers are user-entered data. Archived research and explanatory publications are not automatically promoted into quotation series.
