# Official international agricultural price references

Validated 7 September 2026. Implementation: `pipelines/ingestion/international_sources.py`.
These references belong in `official_price_quote`, with their own currency, unit,
market, basis and exact quote identity. They must not enter the Colombian COP
wholesale average or be converted into an apparent Colombian farm price.

## Included sources

| Publisher and primary entry point | Included information | Basis and limits |
| --- | --- | --- |
| [World Bank Commodity Markets](https://www.worldbank.org/en/research/commodity-markets) | 45 monthly agricultural, food, feed, natural-fiber and fertilizer series. Latest downloaded workbook: 31,381 numeric observations from January 1960 through August 2026. | Nominal USD, original kilograms or metric tonnes. Each series retains its complete workbook methodology, underlying sources and cell locator. These are international benchmarks. |
| [USDA AMS Miami flower report](https://mymarketnews.ams.usda.gov/viewReport/3034) | Current report has 66 distinct flower/color/grade/size/package quotes, including hybrid tea and spray roses, carnations, chrysanthemums, alstroemeria and other flowers. | US entry-point FOB/delivered sales on a shipping-point basis. The current report does **not** identify each quote's origin country; no quote is labeled exclusively Colombian. Full ranges and the narrower reported “mostly” ranges are retained separately. |
| [USDA AMS Boston flower report](https://mymarketnews.ams.usda.gov/viewReport/2289) | Current report has 35 distinct quotes, seven explicitly originating in Colombia: carnations, miniature carnations, chrysanthemums, hydrangeas, solidago and two calla varieties. | Actual US terminal wholesale quotations. Origin, species, variety, package and report date remain part of identity/provenance. A US wholesale quote is not the price received by a Colombian grower. |

The flower `price` field is the arithmetic midpoint of the reported full range,
with `details.price_statistic=range_midpoint`. It is a display value, not a
publisher-reported average or weighted transaction price. `min`, `max`,
`mostly_min` and `mostly_max` retain their distinct meanings. The exact printed
package remains the unit: a bunch is never silently treated as one stem.

### World Bank commodity coverage

- Coffee: ICO other mild Arabicas and Robustas. The Arabica series is **not** an
  exclusive Colombian Milds or Colombian specialty coffee series.
- Cacao: ICCO international benchmark.
- Bananas: major-brand Central/South American banana import references in the US
  and Europe. These identify destination markets, not botanical varieties.
- Oils: coconut, palm, palm kernel, peanut, soybean, rapeseed and sunflower.
- Meat: beef, chicken and lamb; shrimp also included. The workbook has no pork
  series, so none is fabricated.
- Sugar: world ISA, US and EU references. Futures/import/FOB bases remain explicit
  in the source description; these are not interchangeable with Colombian sugar
  mill prices.
- Additional agricultural references: tea, groundnuts, soybeans, fish meal,
  soybean meal, barley, maize, sorghum, four rice grades, two wheat grades,
  oranges, cotton, two rubber grades and five fertilizer references.

The `Description` worksheet documents changes over time, including coconut/palm
and soybean oil terms, beef origin/grade, and chicken markets. It is preserved
and linked for each series rather than overwriting historical methodology with
only the current market definition.

Tobacco “US import u.v.” is excluded because it is a trade unit value. Energy,
metals, price indices and forecasts are outside this agricultural price import.
Likewise, flower export revenue divided by tonnes and unverified commercial
price-estimate websites are not treated as observed flower prices.

## Original files and recurring discovery

Current original assets:

- [World Bank monthly workbook](https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Historical-Data-Monthly.xlsx)
- [Miami MH_FV221 PDF](https://www.ams.usda.gov/mnreports/mh_fv221.pdf)
- [Boston BH_FV201 PDF](https://www.ams.usda.gov/mnreports/bh_fv201.pdf)

`discover()` returns the live World Bank homepage and both current USDA PDFs,
as well as the [Miami historical index](https://esmis.nal.usda.gov/publication/import-ornamental-shipping-point-report-miami-fl)
and [Boston historical index](https://esmis.nal.usda.gov/publication/ornamental-wholesale-market-report-boston-ma).
`discover(body, url, kind)` follows only the expected official workbook, report
PDFs and same-publication pagination links. This notices a new World Bank URL
when the year or document identifier changes. The current PDF and Excel URLs
are mutable and must be rechecked daily by the worker. Changed bytes need a new
immutable archived document and quote revision, not deletion of the old source.

The ESMIS historical indexes currently end in September 2025; they supplement
the current AMS reports and do not establish complete 2026 historical coverage.
Older text-era formats are not silently accepted by a PDF parser. Unexpected
layouts/identities/ranges fail for review while their original files remain
archived. Reprocessing after a parser fix must create a new parser revision.

Structured My Market News/API endpoints were investigated but could not be
reliably downloaded in this session. The implemented sources are the actual
accessible public USDA PDFs, not a third-party redistribution or guessed API.
The current reports and tested samples contain native text; OCR was not used.

## Validation evidence

`artifacts/official-sources/` contains the exact downloaded workbook, index HTML,
current PDFs, historical PDF fixtures, test log and machine-readable validation
report. Tests cover source-host discovery, USD/native units, original locators,
missing markers and malformed data, explicit dates, duplicate detection, PDF
page/column continuation, flower grades/colors/sizes and unquoted products.

Run:

```sh
.venv/bin/python -m unittest pipelines.ingestion.test_international_sources -v
```

Observed upstream quality exceptions:

- The World Bank workbook has four `#VALUE!` cells and four zero placeholders
  in a rice series. Those original cells remain in the archived workbook and
  are excluded from published positive-price observations. No interpolation is
  performed. Ellipses and empty cells also remain missing.
- [Miami 29 September 2025](https://esmis.nal.usda.gov/sites/default/release-files/4x51hj05x/4m90gw071/c534hn54d/MH_FV221.PDF)
  contains a malformed printed range `0.25-.0.29`. It is intentionally rejected
  for review instead of guessing the intended number.
- Three historical Boston report layouts from June, July and August 2025 were
  successfully parsed in addition to the latest September 2026 report.
