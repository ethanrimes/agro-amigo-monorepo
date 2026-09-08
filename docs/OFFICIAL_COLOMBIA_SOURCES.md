# Official Colombian price sources

Verified against original public pages and downloaded files on 7–8 September 2026. These adapters supplement DANE and FNC. They do not merge unlike price bases into a wholesale COP/kg series.

## Included sources

| Publisher and original entry point | Products and basis | Verified coverage / extraction |
| --- | --- | --- |
| [UPRA / AgroNET cacao reference](https://agronet.gov.co/noticias/precio-de-referencia-semanal-de-compra-de-cacao-fuente-industria-nacional-exportadores-0) and [the earlier migrated page](https://agronet.gov.co/noticias/precio-de-referencia-semanal-de-compra-de-cacao-fuente-industria-nacional-exportadores) | Cacao in grain, weekly industry/exporter buying reference, COP/kg | Two mutable HTML tables. The current page has 254 weekly rows from 23 August 2021 through the week starting 7 September 2026. The other page recovers nine otherwise missing weeks in August–October 2025. Dates represent the explicit effective week start; the exact end remains in `details.period_end`. |
| [MADR / Fedepalma Fondo de Fomento Palmero](https://fedepalma.org/fondo-de-fomento-palmero-ffp/) | Crude palm oil and palm kernel, statutory reference used to calculate the contribution to FFP, COP/kg | 130 quoted product/semester values from July 1994 through July 2026. Original resolutions linked by the price table are discovered and archived. This is a regulatory reference, not a purchase offer or market transaction price. |
| [Fedegán / FNG price indicators](https://estadisticas.fedegan.org.co/Indicadores/13), linked from the [official price page](https://www.fedegan.org.co/estadisticas/precios) | National and regional live cattle indicative auction prices, BMC registered invoice transaction prices, producer milk with/without voluntary bonus | Six public CSV exports, 5,735 raw price cells. National fat cattle starts January 2006; regional lean male/female and fat cattle June 2017; BMC weekly regional cattle June 2018; milk January 2017. Original CSVs use ISO-8859-1 and `text/csv`, although the download URL ends in `export.jsp`. |
| [Porkcolombia / FNP Ronda de precios](https://porkcolombia.co/ronda_de_precios/) and its [public report collection](https://porkcolombia.co/wp-json/wp/v2/ronda_de_precios?per_page=100&page=1) | Pig live weight, hot carcass, cold carcass; reported producer survey averages in COP/kg, with the weight basis explicit | Public collection has 329 report posts. Reports include older historical files, including a verified March 2020 report. Recursively follow archive pages and original PDF links. Native text validated on 2023, 2025 and 2026 layouts, including letter-spaced historical tables. March 2020 price tables require OCR after native extraction returns only headings. |
| [Corabastos daily bulletins](https://corabastos.com.co/boletin-precios-corabastos/) and [public bulletin attachments](https://corabastos.com.co/wp-json/wp/v2/media?search=Boletin&per_page=100&page=1) | Banano Criollo/Urabá, plantain presentations, coconut, sugar varieties, packaged coffee, poultry, fish, meat cuts, produce and other food prices at Corabastos warehouses | Calendar has 374 event entries (343 distinct eligible PDF links in the saved snapshot). Public media search finds 608 attachments across seven pages, including additional PDFs from April 2024. Original 2024 and 2025–2026 layouts are supported without OCR. Recent reports contain 175 package identities / 350 separate quality quotes; verified older reports contain 176 / 352. |

## Price identity and retention

The pure adapter module is `pipelines/ingestion/colombia_sources.py`. It exports:

- `VERSION`, `ROOTS`, `PUBLISHERS` and `INDEX_KINDS`.
- `discover()` returns the seed `(url, kind)` pairs. `discover(body, url, kind, today=None)` returns trusted, public child URLs. PDF/CSV leaves return an empty discovery list before any HTML decoding.
- `parse(body, url, kind)` returns typed dictionaries with `product_id`, `product_name`, `category`, `publisher`, `series`, `basis`, `currency`, `unit`, `market`, `date`, `period_start`, `price`, `source_locator`, `identity_dimensions`, and `details`.
- `parse_with_ocr(body, url, kind, readings_by_page)` accepts already independently verified OCR readings only after the normal parser raises `NormalExtractionFailed`. That exception exposes `required_pages` as original 1-based PDF page numbers. Native extraction always runs first. Unsupported OCR layouts remain reviewable; they do not produce guessed quotes.

Quote identity must include product, series, market, currency, unit, basis, and `identity_dimensions`. Corabastos quality, presentation, literal quantity and published unit are retained. The source changed some unit labels between 2024 and 2025; the adapter preserves those labels instead of asserting a box/bunch/bag weighs one kilogram. Older `Desde/Hasta` columns are distinct from newer `calidad extra/primera` columns. Published per-unit derived values remain evidence metadata, not a substitute for the quoted package price.

Source locators must identify individual observations, including the market column inside multi-market PDF rows. `colombia-prices-v2` adds the missing market dimension to native Porkcolombia monthly locators. The publication layer now rejects collisions instead of allowing an immutable primary-key conflict to discard another market silently. Parser and publication versions are combined in the stored revision key; old rows remain retained while corrected versions become publishable.

The production replay on 8 September 2026 recovered 444 previously omitted Porkcolombia market/date observations, increasing the published total from 282 to 726. All published Porkcolombia and Corabastos PDF observations then had an explicit source-page number. The retained original bytes and previous parser results were preserved; replay evidence is in `artifacts/official-pdf-revision-replay.json`.

Fedegán changed lean cattle source methodology on 14 August 2026 from average to maximum reported auction prices. August is a separate transition series; later months are a maximum series. Prior averages remain available. Live-weight cattle, live pigs, carcasses, milk and regulatory palm prices must remain visibly distinct.

Recheck roots and full-history CSV URLs daily. CSV date ranges are stable within the current year, so same-URL changes are hash-versioned rather than silently skipped. Recursively enqueue new report posts, media pages, original PDFs and FFP resolution links. Preserve each original response and parser revision. Adapters never write to the database, delete history or fetch credentials.

## Publisher defects retained for review

`details.quality_issue` or a null `price` means preserve the raw row but exclude it from the published-price projection:

- AgroNET March 2024 has an ambiguous `$22.421.720` value. Other historical amounts use a second dot as a decimal marker with exactly two final digits. The ambiguous three-digit suffix is not silently repaired.
- The Fedegán female lean cattle CSV reports zero for Llanos Orientales in May 2019. It remains raw evidence rather than a zero-price quote.
- A 2026 Porkcolombia report prints `Nov-24` and `Dic-24` inside the chronological 2025–2026 hot-carcass table. These six market cells remain reviewable. Dates are not guessed from neighboring rows.
- Some 2024 Corabastos files print `Desde` higher than `Hasta`. Both literal values are retained for review. Package prices are not divided by a guessed quantity or substituted with an inconsistent source-derived unit price.

The latest cacao update arrived during validation: COP 16,162.00/kg for the week 7–13 September 2026. This is a valid currently effective reference even though its week ends later; `date` is 7 September and `period_end` is 13 September.

## Limits and exclusions

- Both AgroNET pages still link [their historical workbook](https://agronet.gov.co/Lists/Boletin/Attachments/20623/PrecioReferenciaCacaoHistoricoMADR%20(1)%20(1).xlsx), but the publisher returns HTTP 404. The former `/Noticias/Documents/PrecioReferenciaCacao-Historico.xlsx` endpoint also returns 404 after migration. Therefore Colombian weekly cacao history before August 2021 has not been claimed as recovered. Secondary papers quoting it are not substituted for the missing original.
- [BMC indicative collateral values](https://indice.bolsamercantil.com.co/preciosindicativos.aspx) returned HTTP 503 during verification. They are not added as spot transactions. BMC registered cattle invoices published by Fedegán are available and explicitly labeled separately.
- Fedepalma SISPA public landing pages identify additional statistics, but no additional stable original transaction dataset was verified in this bounded adapter work. FFP references do not claim to fill this role.
- No reliable public Colombian farm-gate flower price series was confirmed. Asocolflores trade totals are not presented as flower prices. Likewise, banana/flower export value divided by tonnage is not silently treated as a farmer's quote. International official benchmarks belong in a separately labeled reference series.
- Corabastos' packaged coffee does not establish coffee cultivar or specialty-grade farm prices; its literal product/package identity is preserved. FNC and international coffee variety benchmarks remain separate sources.

## Validation evidence

Run `python -m unittest pipelines.ingestion.test_colombia_sources`. Tests cover trusted discovery, same-URL export identity, cross-month/year weeks, effective reference dates, decimal parsing, real publisher defects, quality/package separation, native wrapped names, normal-extraction-first behavior, missing OCR pages, and disagreement between duplicated OCR tables.

Downloaded originals and validation results are in `artifacts/official-sources/`. `colombia-tests.log` records the 22-test regression suite. `corabastos-stress.json` records five additional live original PDFs across 2024 and 2026, each yielding 350 or 352 literal quality/range quotes. The historical 2023 Porkcolombia fixture produces 180 native quotes including 165 monthly quotes since February 2022.

Actual Gemini 3.5 Flash OCR was also validated on the original March 2020 Porkcolombia report, where normal extraction found headings but no price cells. Each required page (2 and 3) has two independently agreeing readings saved as `pork-2020-page{2,3}-reading{0,1}.json`. The parser extracts 108 observations from January through March 2020; `pork-2020-ocr-validated-rows.json` preserves the validated output. Page 3's titles were emitted separately from its tables, so the parser binds each table to an explicit native product heading and an exact six-market current-price vector already identified on page 2. Reordering the OCR tables produces identical quotes; changing one matching price fails validation. The national 27 March values match the rendered original: COP 5,298/kg live, 7,023/kg hot carcass, and 7,254/kg cold carcass. Synthetic hand-checked OCR fixtures remain separately labeled in tests. This establishes extraction behavior; database publication and archived evidence links are verified by the ingestion integration separately.
