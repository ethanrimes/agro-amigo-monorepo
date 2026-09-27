# Broken source links and publication ambiguities

This audit distinguishes recovered observations from unresolved publisher errors.
Original documents, earlier observations and review evidence remain retained.

## Verified recovery rules

- Two August 2014 daily Excel URLs have publisher typos. Exact allowlisted
  replacements are used only after HTTP 404/410, and the complete replacement
  workbook must pass native date, identity and price validation on every fetch.
- Five native daily headings contain misspelled months or a missing year. Date
  corrections require the exact audited SHA-256, printed heading, archive date
  and independently checked official companion evidence. Changed files cannot
  inherit an old exception.
- Four archive links point to another day's original. Their verified actual-day
  observations can be retained and projected, but the requested-day gap remains
  explicitly reviewed. Three already share their canonical document hash.
- The November 29, 2012 workbook contains 238 positive cells: 178 have explicit
  product/market identities and 60 lack market labels. All cells are retained;
  only the 178 identified prices are published.
- A USDA Boston native text original begins with blank lines. Heading detection
  now skips blank preambles while preserving exact original line locators and
  rejecting nonempty junk or another market's heading.

Daily publication validates the entire workbook before committing valid rows,
cell-level reviews and immutable resolution evidence atomically. Replays reject
conflicting old immutable identities. Derived daily prices preserve Excel-over-
PDF precedence and reject older revisions within the same source priority.

## Ambiguities with verified alternative coverage

- DANE's public historical explorer independently supplies 12,638 daily means
  across nine requested dates, including the two missing daily Excels, six
  contradictory/mislinked daily originals and the missing July 2023 city ZIP.
  These remain a distinct daily-query series with published mean/min/max, exact
  units and fully archived query parameters/responses. Every selector and the
  native `totalRows` are checked; empty selections and partial pages are rejected.
- July 24, 2023's official ZIP contains 23 original July 22 city PDFs with 969
  package/round price ranges. All 49 members validate (2,283 ranges across three
  dates). The July 22 ZIP's full roster cannot be established. Bogotá's missing
  package-price PDF is not reconstructed; its 93 independently published daily
  means are included in the separate 754-row July 22 query response.

- September 17 and 24 city ZIPs contain PDFs dated the following day. All 100
  disputed positive prices match correctly dated originals already published.
  The premature Santa Marta PDF is empty; its proper report supplies 23 rows.
- The December 2020 milk Excel is byte-identical to November's. The correct
  December PDF supplies all 208 published December municipal prices. Assigning
  the copied annex to December would misstate 199 prices, so its review remains.
- September 2021 milk uses a single wide native table. Header geometry and the
  repeated report month recover 208 rows; all 624 minimum/maximum/mean cells and
  25 departments reconcile independently with Poppler.
- USDA Boston's explicit exceptional range stays attached to its base quote;
  truly unqualified duplicates are reviewed. Miami's out-of-range `mostly`
  qualifier reviews only its own quote and retains all literal values.

The app identifies reviewed reference dates in the source viewer and excludes
misdated daily workbook aliases from the library. Retained originals remain
available by document ID. Official DANE reference records are supported in the
same source viewer as the other official price series.
Corrected headers show the independently verified date and corroborating source.
The known February 2013 carrot-price disagreement is explicit in the viewer;
the original workbook value is preserved. The viewer displays the number of
records withheld for review. An additive read-only grant fixes access to retained
correction evidence. Official source queries now start with the selected
document, preserve its literal verified rows, and apply the same date/quote
review suppression without scanning the global price projection. Six TEMP
PostgreSQL regression cases validate those semantics; actual reader queries
returned in 0.07–0.15 seconds for six checked sources.

Responses are archived as each request completes, before schema/content
validation, so a later failure does not lose downloaded evidence. Failed and
deferred recovery cannot clear an existing source review. Parser-version changes
invalidate the daily recovery cache. All fallbacks keep their original date,
market, unit and price statistic; none uses OCR to fill missing identities.

## Validation and deployment evidence

Final full ingestion suite: 519 tests, 418 passed and 101 opt-in skips. Fourteen
explicit PostgreSQL tests passed using only session TEMP tables, including
atomic partial publication, wrong-date rejection, idempotent review retention,
daily revision chronology and provenance. The production web build passed.
Five additional TEMP PostgreSQL query tests check native response retention,
failed requests, replay, exact units/ranges, catalog publication and supplemental
city-archive identity. Three TEMP worker-run tests prove review suppression stays
in effect during and after failed/deferred alternate recovery. Mobile Chrome
and Safari source annotations fit their viewports without page errors; these
checks use browser emulation, not native simulator execution.

USDA v8 replay parses all 205 cached originals. Every one of the 188
previously successful v7 outputs remains exactly unchanged. The final 17
recoveries retain 1,063 valid literal price occurrences (1,018 distinct quotes)
and 62 review records. Two originals contain no printed prices; they receive
explicit no-price reviews. Missing units, conflicting identities and malformed
decimal ranges remain literal review evidence, while valid sibling rows publish.

Artifact root: `artifacts/source-ambiguity-2026-09-27/` (ignored; official
originals, price comparisons, query responses, database/API checks and logs).
Cloud deployment and official historical-query fallback validation are ongoing.
