# DANE source audit — 26 September 2026

This is an exhaustive inventory of **registered DANE source kinds**, with representative actual-file checks across every price family. It is **not** a claim that every historical original has been downloaded, parsed or published. Queue counts below are the retained baseline at **2026-09-27 04:03:30 UTC**, before recovery. Parent deployment verification supplies the current publication status separately.

`all-dane-expected-manifest.json` contains **9,645 URL entries**: all **9,146 baseline DANE assets**, plus **499 URLs missing from that baseline** (466 supply originals, 14 supply indexes, 12 explanatory PDFs and 7 current daily files). It records URL, expected kind, parent page, prior original hash/status and explicit sampling status. No URL was removed because its parser failed. Encoded aliases remain distinct URLs and may share original hashes.

| Registered / newly discovered kind | Baseline count | Native actual-file validation and semantic basis | Boundary / remaining limitation |
|---|---:|---|---|
| `daily-index` | 166 | Current daily index and archived month links enumerated, including current September24–26 gap | Queued archives June2012–August2026; index success means link discovery, not all child processing |
| `daily` | 3,366 | Sep25 2026:431 positive prices; June12 2012 XLS:210 prices. Names, cities/markets, COP/kg and product unit exceptions retained | Earliest registered June12 2012. Internal day must equal linked date. Baseline2,783 pending,8 failed,5 review,3 awaiting OCR |
| `daily-pdf` | 3,394 | June27 2012:120 real COP/kg cells. Printed June27 verified and percentage columns excluded. Sep25 2026 contains narrative plus daily **supply tonnes**, not a comparable national price matrix | Earliest June27 2012. Current supply totals through Sep24 retained as PDF context, not structured daily supply. Old readable monetary matrices now strict `daily-pdf-v4` |
| `city-zip` | 952 | Sep26:202 package/round observations from Corabastos; Sep17:2,379 rows from29 valid members. Actual Arauca/Corabastos min/max, units, category/subcategory, market, date and rounds visually checked | 2 Sep17 ZIP members print Sep18; held for review. Earliest queued ZIP June2023, not evidence city ZIPs existed in2012. 173 pending/51 failed at baseline |
| `monthly` | 10 | 2026 mutable series:37,007 Jan–Aug observations. Consolidated2013–17:281,386 observations with market-level COP/kg/unit/litre distinctions | Earliest consolidated2013. Mutable same URLs must be checked for revisions. Monthly values are distinct from package city/daily prices |
| `monthly-annex` | 139 | Aug2026:463 city-price cells; Feb2015:404; March2015:398 independently matched price cells after current/comparison month fix | `Marzo/febrero2015` dates current monetary cells to March, not February. Baseline117 pending/14 review/4 failed. Percentage number-format normalization verified without changing modern percent-point values |
| `monthly-pdf` | 414 | July2012:353 real city monetary observations on pp10–11; printed July vs August13 publication date verified. July2026:263 apparent old prices are actually percent changes; now rejected with0 OCR | **Critical bug fixed:** table-local monetary proof required. Old `dane-monthly-bulletin` raw rows need append-only review quarantine. Strict verified rows use `monthly-pdf-v3` + neutral monthly-city basis; no numerical guesses |
| `inputs` | 1 | Department consolidated2018–26 uses explicit month/year and full commercial identity; earlier native coverage regression preserved current rows | Department series starts2018; older municipal XLS/PDF complements it. Scope is departmental mean, not individual shop quote |
| `inputs-municipal` | 2 |2013–20 and2021–26 consolidated native sheets; municipality/code, presentation, brand, ICA and category preserved | One pending at baseline; large files require resumable native publication and dated revision watermarks |
| `inputs-annex` | 80 | CurrentAug municipal:38,248 positive cells;35 formerly OCR-blocked departmental annexes:287,184 prices now native. Entire36-file batch hashed | Remaining Jan2026 annex:7,995 rows sayJan2026 but1,299 service rows sayJan2025; entire source remains explicit period review. Readable logos are not OCR justification |
| `inputs-reference` | 176 | Feb2015 grouped XLS:6,394 exact current-price cells across15 categories, including services/rent/material; independent xlrd cell comparison. Context workbook indexes95 reports fromJul2012–May2020 | Native legacy header gap fixed. Prior comparison columns (Jan/Nov/Dec) not assigned guessed years. Baseline48 failed; all other legacy layouts not individually certified |
| `inputs-pdf` | 173 | July2012:3,271 verified rows;Aug2012:7,914 verified +7 unresolved overprinted headings (7,921 retained). Gauge12,5, roll350m and Aguachica141,250 visually verified against page36; preserved per-package COP and geographic identity | Earliest July2012. Ambiguous/overprinted headings remain unresolved, not attributed to previous product. CurrentAug2026 PDF narrative/chart content retained, while native annex supplies prices |
| `milk` | 83 | CurrentJul annex208 prices, cumulativeJan–Jul1,456.2013–19 consolidated16,470 observations; native COP/litre, farmgate, municipality | Earliest consolidated2013. Source geographic means, not wholesale product prices |
| `milk-pdf` | 166 | Oct2012:180 municipal prices, Angostura mean887/min712/max990 COP/litre visually verified. Aug2014:183 rows independently validated and replayed in earlier phase | EarliestOct2012. Jul2026 has no supported municipality grid, **does contain macroregion price charts** (CostaCaribeJuly1960); context retained, not structured macroregion quotes |
| `rice` | 7 | Current2026:837 observations/6 products Jan–Aug;2013–20:12,056 prices. First Aguazul packaged white rice2,464,133.333 COP/**tonne**, mill basis retained | Earliest2013. Never silently convert tonne to kg or mix mill and retail/wholesale basis |
| `supply` | 14 |2026:1,700,536 source rows→30,260 market×food×month groups;5,563,129,891.66kg, Jan2–Sep23.2013:1,046,815 rows→14,175 groups;4,457,161,058.01kg | Independent standard-openpyxl2013 traversal matches all row/group counts and total within0.000005kg floating accumulation. Earliest Jan1 2013. Preserve source-row ranges, not only aggregate totals |
| `supply-reference` | 1 (136 expected) | Native tables/context cell retention; monthly/published aggregate totals stay separate from microdata | Adds135 XLS/XLSX originals; reference totals must not double-count underlying microdata |
| `supply-reference-pdf` | 0 (331 expected) | Aug2026 p3 market totals:MercarJuly10,053t/Aug9,640t/-4.11%; visual/native context agrees | Preserves331 PDFs as source pages/text/tables. Aggregate market tonnes are not monetary prices or individual-food observations |
| `supply-index` | 0 (14 expected) | Canonical archive index2013–26 discovered and enumerated | Index queue records are not data observations |
| `context-pdf` | 2 (14 expected) | Twelve additional official PDFs retained:6 quarterly,May2021 special,2 launch documents,Acerca,certification note,April2013 press. Strict official-host/name matcher tested | Monetary prose, charts, aggregate indicators and methodology remain reference context. EgQ2 2026 prose saysAprilBucaramanga chócolo1,325/kg; not yet a structured quote row. No guessed period from filename typo`20133` |

## Weekly bulletins added on 27 September

The weekly family is now registered through `dane_weekly.py` (`dane-weekly-v1`)
and the official-source publication path. The observed-link inventory covers
**16 index pages** (current root and 2012–2026 archives) and **1,453 originals**:
730 PDFs, 415 XLSX and 308 XLS. These are additional to the 9,645-entry baseline
manifest above. Discovery now includes legacy `Anexo_`, `anex_` and `bol_`
filenames and removes fragment-only index duplicates; all 1,453 observed links
are recognized without synthesizing missing weeks.

| Weekly kind | Observed inventory | Validated behavior |
|---|---:|---|
| `dane-weekly-index` | 16 pages | Current and historical child discovery; current/previous-year indexes and recent 70-day files receive recurring checks. Unknown-date leaves retain bounded daily/backfill eligibility. |
| `dane-weekly-pdf` | 730 files | Explicit weekly period, literal product/market, COP, printed minimum/maximum/**mean**, unit and page/table locator; supported native failures request OCR only for failed pages. |
| `dane-weekly-xlsx` | 723 files, including 308 XLS | Native monetary cells and declared unit exceptions; original XLS/XLSX bytes and worksheet/row locators retained. Same-URL byte revisions remain separate originals. |

Twelve retained originals spanning June 2012, August/November 2012, 2017–2018,
December 2018, 2025–2026 and September 2026 completed native stress validation:
**49,006 literal rows, 39,529 publishable and 9,477 review rows**. These counts
include companion-file overlap; they are not unique database observations.
The current September 19–25 workbook/PDF pair matches all **4,571 literal
product/market keys and 13,713 min/max/mean cells** against independently decoded
workbook XML. No precision discrepancy was found in that pair; the published
mean is preserved, not replaced by a range midpoint. Weekly prices remain a
separate period/basis from daily and monthly quotations.

Source ambiguity remains explicit:

- The current workbook declares 84 egg quotes per unit and 47 liquid quotes per
  litre. Its PDF lacks those exception notes, so those 131 PDF rows retain their
  literal figures as unit reviews; the workbook provides verified quotations.
- Early grouped XLS annexes without any unit declaration are retained for review.
  A price magnitude or a companion publication is not silently treated as a
  declaration in that original.
- The first June 16–22, 2012 PDF contains 1,428 rows: 1,340 publishable, 62 unit
  reviews and 26 rows in blocks with absent/conflicting product headings. The
  cross-year 2018 PDF also genuinely prints conflicting Trucha/Pasto prices;
  its affected block is reviewed rather than choosing an arbitrary value.
- Native layout regressions cover unbolded product headings, centered category
  captions, wrapped market names and cross-year periods. Pure cached-OCR tests
  cover image tables under readable headings; no provider OCR was requested for
  this weekly validation. **Image-only weekly workbooks remain explicit layout
  review:** the legacy workbook OCR publisher does not supply typed weekly
  period/basis semantics.

Evidence is under `artifacts/automation-audit-2026-09-26/weekly-assessment/`:
`weekly-observed-manifest.json`, `weekly-discovery-recheck.json`,
`final-parser-results.json`, independent current/historical reconciliations and
`FINAL-VALIDATION.md`. Sixteen adapter tests pass; shared wiring has separate
isolated PostgreSQL and scheduler proof. Registration and local validation do
not establish live publication or completion of all 1,453 historical files;
cloud original/Blob and API verification are recorded separately.

## Defects found and bounded fixes

1. **False monetary interpretation:** modern monthly city percentage matrices resembled old monetary grids. July2026's0.09 and63.99 are percentages. Strict table-local `Precio $/Kg`, printed period, price-only columns and versioned provenance now distinguish them. Original bytes/raw rows remain; review quarantine is additive.
2. **Missing historical native input format:** grouped sheets `FERTILIZANTES FEB15` + `Precio medio febrero` were unrecognized. The corrected parser reads all6,394 positive current cells and full headings. It validates the independently printed column month against the sheet's year/month and rejects unknown category/place/identity.
3. **Monthly comparison period confusion:** the historical `Marzo/febrero2015` heading caused March to be rejected. The corrected parser selects the first explicitly printed current month and still rejects an expected February link.
4. **Discovery omissions:** the supplied supply page/archive links and12 context PDFs were missed by earlier narrow discovery. Their complete expected URL lists are now machine-readable; download/retention is a separate cloud verification step.
5. **Readable spreadsheets sent to OCR:**35/36 old input annexes need native header support, not image extraction. One genuine conflicting period remains review; no normal native values are replaced with OCR.
6. **City ZIP member dates:** one mismatched internal PDF must not erase valid markets. Durable member review retains conflicting originals while validated members publish independently.

7. **Excel percentage scaling:** the old March2015 YTD value0.101871 is displayed by Excel as10.1871%; modern August2026 uses literal27.159 percent-points. The parser now reads each cell’s number format, scales only actual percentage formats, and preserves escaped/quoted percent text. Versioned `monthly-annex-v2` rows retain the old evidence while allowing corrected metadata.

## Evidence and limits

- `visual-spotchecks.json`:12 actually rendered/viewed PDF samples, seven exact row assertions plus five explicit reference-context classifications; render files under`visual/`. The July2026 percentage page additionally rendered/viewed as`monthly-july2026-page13.png`.
- `historical-parser-results.json`:13 native boundary/layout cases with hashes, counts, dates, units, exact sample records and explicit errors from before the latest two layout fixes.
- `legacy-layout-after.json`:corrected two native layouts; `legacy-layout-tests.log`:34 earlier tests passed, including independent source-cell coverage. Final combined regression: **54 tests passed in6.219s**, `final-dane-regressions.log`.
- `pdf-semantics-tests.log`:19 tests passed; verified OCR/native use the same monetary gate; a readable percent table triggers no OCR.
- `supply-2013-independent.json`:independent1,046,815-row source validation; no ingestion helper reused.
- `current-coverage-before.json`:45 specific Sep8–26 daily originals;37 previously complete/processed,7 undiscovered and1 failed date-conflictingZIP at baseline.
- `older-input-layout-after.json`:36-original full native batch review;35 complete source cell mappings,1 conflicting period.
- All audit scripts are read-only local-original parsing; no production writes were performed by this audit agent.

Remaining breadth is explicit: many registered historical files remain pending/failed/review; current retained-only charts/prose/aggregate supply have not all become structured observations. Weekly bulletins are now registered and independently validated as described above, with historical loading and unsupported source layouts still explicit. A complete URL inventory plus representative validation is stronger than claiming all historical files passed, and still does not substitute for the parent's post-recovery publication/retention reconciliation.
