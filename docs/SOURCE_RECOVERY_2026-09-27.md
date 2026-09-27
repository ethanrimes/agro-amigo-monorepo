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

- September 17 and 24 city ZIPs contain PDFs dated the following day. All 100
  disputed positive prices match correctly dated originals already published.
  The premature Santa Marta PDF is empty; its proper report supplies 23 rows.
- The December 2020 milk Excel is byte-identical to November's. The correct
  December PDF supplies all 208 published December municipal prices. Assigning
  the copied annex to December would misstate 199 prices, so its review remains.

The app identifies reviewed reference dates in the source viewer and excludes
misdated daily workbook aliases from the library. Retained originals remain
available by document ID. Official DANE reference records are supported in the
same source viewer as the other official price series.

## Validation and deployment evidence

Initial full ingestion suite: 456 tests, 368 passed and 88 opt-in skips. Fourteen
explicit PostgreSQL tests passed using only session TEMP tables, including
atomic partial publication, wrong-date rejection, idempotent review retention,
daily revision chronology and provenance. The production web build passed.

Artifact root: `artifacts/source-ambiguity-2026-09-27/` (ignored; official
originals, price comparisons, query responses, database/API checks and logs).
Cloud deployment and official historical-query fallback validation are ongoing.
