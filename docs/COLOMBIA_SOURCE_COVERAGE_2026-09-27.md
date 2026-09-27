# Colombian official source audit — 2026-09-26 / 27 UTC

Adapter: `colombia-prices-v4`. This is a local extraction and source-evidence audit; cloud publication and original-Blob reconciliation are separate checks. Runtime/source files were not deployed by this audit agent.

## Every registered source kind

| Kind | Purpose | Baseline assets/statuses | Current bodies tested | Failed originals retested |
|---|---|---|---:|---:|
| `coffee` | price extraction | 1: complete=1 | 0 | 0 |
| `coffee-pdf` | price extraction | 1: complete=1 | 0 | 0 |
| `colombia-agronet-cacao` | price extraction | 2: complete=2 | 2 | 0 |
| `colombia-corabastos-index` | index/discovery only | 1: complete=1 | 1 | 0 |
| `colombia-corabastos-media` | index/discovery only | 7: complete=7 | 1 | 0 |
| `colombia-corabastos-pdf` | price extraction | 616: complete=285, failed=62, pending=269 | 3 | 62 |
| `colombia-evidence` | statutory resolution original evidence only | 23: complete=23 | 0 | 0 |
| `colombia-fedegan-csv` | price extraction | 6: complete=6 | 6 | 0 |
| `colombia-fedegan-index` | index/discovery only | 1: complete=1 | 1 | 0 |
| `colombia-fedepalma-ffp` | price extraction | 1: complete=1 | 1 | 0 |
| `colombia-pork-index` | index/discovery only | 363: complete=363 | 1 | 0 |
| `colombia-pork-pdf` | price extraction | 330: failed=122, awaiting-ocr=52, complete=156 | 2 | 122 |
| `colombia-pork-posts` | index/discovery only | 4: complete=4 | 1 | 0 |

Baseline counts are the audit-start queue, not current cloud completion. FNC additionally has two real XLS originals and the current PDF checked; index/evidence kinds intentionally return no price rows. `source-family-matrix.json` contains all exact source URLs, hashes, discovery links, dates, units, series and bases.

## Price identity, period and whole-cell checks

| Family | Current retained source check | Meaning / separation |
|---|---|---|
| FNC | September XLS: 8,667 eligible rows through Sep26;8,666 unique dates because2018-11-11 repeats805,000. Sep25 PDF: national2,105,000;13 factors;16 branches. The same retained workbook also has Sep27 once that date becomes current. | COP per125kg FR94; factor and branch references remain distinct. Separate coffee adapter audit owns additional workbook/PDF sections. |
| AgroNET / UPRA cacao | Current page256 weeks through2026-09-21, price14,461.30/kg forSep21–27; legacy page222 weeks. | Effective week start, period end retained; reference purchase indicator, not guaranteed offer. |
| MADR / Fedepalma FFP |130 rows,1994-07 through2026-07; latest crude palm oil4,054/kg and palm kernel2,126/kg.23 linked resolution originals are evidence-only. | Statutory semiannual levy reference, not spot farm transaction prices. |
| Fedegán / FNG |All six CSV indicators:56,63,67,74,75,81. Independent numeric-cell counts match every extracted record; see fedegan-all-cell-coverage.json. | Milk bonus/no-bonus, auction and BMC invoice series stay distinct; August2026 average-to-maximum transition separately labeled. |
| Porkcolombia / FNP |Current Sep11 andSep25 reports; Sep25 national6,444 live/8,877 hot/9,541 cold COP/kg; all27 positive tercile means on current page separately extracted. | Terciles superior/medio/inferior are separate price_segment identities and simple means, never minimum/maximum of weighted quotes. Historical and current periods remain separate. |
| Corabastos |Sep23/24/25 each350 quotes,175 products ×two quality columns. Latest Banano Uraba45,000 extra/42,000 primera, CAJA quantity20. | Preserve literal package quantity/unit; no box-to-kg assumption. Calidad extra/primera are not min/max. Older Desde/Hasta keep their explicit separate basis. |

## Historical and visual stress evidence

All184 previously failed original PDFs were downloaded from official URLs and matched their archived SHA256. v4 parses151 natively into38,212 source records, including773 review records;32 require OCR, and the one blank template remains blocked. All149 previously native originals have exactly unchanged core identity/date/market/price/unit/locator digests. New compact files each contain175 printed rows and350 quality records; March17 holds2 clipped records for review, March19 holds128 overlapping/clipped records rather than completing names by guess.

Sixteen original pages were rendered with Poppler and inspected, spanning current FNC/Pork/Corabastos, rotated side dates, spreadsheet print exports, compact layouts, repeated conflicting prices, image scans, broken font maps, a truly blank page, and a cached-Gemini OCR report. `visual-spotchecks.json` records17 comparisons across the initial15 pages; `cached-ocr-tiers.json` adds the16th-page actual paired-Gemini result:15 tiers, e.g. Antioquia5,369/5,280/5,208 COP/kg on2020-03-27. The existing108 average/history records remain, giving123 total parsed records. No new provider OCR calls were made.

Examples checked against actual rendered numbers:

- FNC Sep25 page1: FR94 national2,105,000 per125kg; factor88=2,169,375 andfactor100=2,040,375. Page2: Bogotá2,104,250 andArmenia2,105,500 per125kg.
- Pork Dec23,2021 page1: national live8,593, hot10,767, cold11,294. Dec30,2022 page3: February live7,826 andDecember30 cold14,160; adjacent chart ticks were excluded.
- Broken-font Dec31,2020 page2 visibly shows national7,434/9,281/9,827, but requires OCRpages1–3. The2023-02-17 scan visibly shows10,256/13,155/13,725, but requires OCRpages1–4. These are pending extraction, not published proof.
- Corabastos April23,2024 rotated-date page2: Acelga20,000/18,000, ATADO quantity10 KILO. August9 print-export page1 matches the same values and unit.
- Compact March17/19,2025 page1: Banano Uraba40,000/38,000, CAJA quantity20; clipped long Aguacate label is retained for review.
- November1,2024 page2 literally repeats Coliflor with24,000/22,000 and30,000/28,000 for the same package; both remain review evidence. Header saysNov1; print footer saysNov5, preserved in original.

## Cloud reconciliation manifest

`expected-current-official-rows.jsonl`: 7,936 current-source records (7,921 eligible, 15 reviews). Repeated histories across documents are intentionally retained; counts are not unique published identities. Match bydocument_id+source_locator+parser_version andquote_key+date, including price/currency/unit/basis/market/dimensions. `expected-current-fnc.json` contains pure-parser FNC rows/factors/branches.

## Explicit remaining boundaries

- 32/184 historical originals require OCR; native fallback tests and one actual paired cached Gemini report are validated, not all32 OCR completions.
- One Feb18,2025 Corabastos original is blank/unverifiable; no recoverable printed prices.
- Pork reports contain adjacent third-party Chicago USD/ton context not covered by this Colombia adapter. These are not represented as Colombian farm prices.
- Source review records remain unpublished: clipped labels, zero placeholders, conflicting repeated prices, dates out of sequence.
- Not every already-complete or pending historical original was visually inspected; coverage counts explicitly separate tested files from baseline queue inventory.

43 focused source tests pass, including cached independent Gemini readings and literal tier regressions. Actual PostgreSQL TEMP-table chronology/bulk checks are recorded separately in price-revision-final-passed.log and price-revision-full-workbook.log; no application data was mutated.

Public API repeat: coffee nowSep27/COP2,105,000 and DANE dailySep25/431 rows are HTTP200. Official-reference, regional and input reads still returned503 during this sample. Exact URLs/timings are in ../public-freshness-after-parser-audit.json; those errors prevent a claim of frontend freshness for those families.
