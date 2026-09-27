# Automation audit: 26 September 2026

This audit compared actual Azure execution since 8 September with current official
publications, retained originals, parser output and the application database.
Local detailed evidence is under `artifacts/automation-audit-2026-09-26/` (ignored
by Git). Counts below are dated observations, not a claim of complete archives.

## Findings

- The daily job had 25 attempts: 18 failed and seven interrupted. Hourly backfill
  had 266 attempts: 190 partial, 67 interrupted, eight succeeded and one running.
  Partial runs often loaded useful files, but one source failure made the whole
  daily invocation repeat. A five-hour input publication transaction still held
  the worker lock after its host execution window.
- Of 45 DANE daily Excel/PDF/city ZIP publications from 8–26 September, seven
  recent files had never been discovered. Another ZIP was marked failed because
  two members contradicted its date, despite 29 valid members containing 2,379
  price observations.
- Current supply microdata was excluded from frequent refresh. The 2026 original
  now has 1,700,536 literal source rows, reconciling to 30,260 monthly groups,
  192 foods and 32 markets through 23 September. Aggregate supply annexes remain
  reference data; they are not fabricated as individual agricultural prices.
- FNC's page still linked an older workbook before its September workbook. The
  prior first-link selection missed the latter's reference observations through
  26 September. All linked verified price workbooks are now discovered.
- August's municipal input annex renamed its service heading. Native extraction
  now yields 38,248 observations, including 768 services previously lost when
  validation rejected the entire file.
- Thirty-six department input annexes were sent to OCR because a native date
  heading omitted parentheses. All archived hashes match the downloaded files.
  Thirty-five clean originals reconcile exactly to all 287,184 positive source
  price cells. January 2026 has contradictory January 2025 headings on two
  sheets; it remains reviewable rather than assigning guessed dates.
- The PostgreSQL B1ms instance was CPU-saturated with nearly exhausted burst
  credits. Replaying million-row workbooks repeatedly rewrote unchanged values
  and triggered unnecessary retained revisions. Storage had automatically grown
  to 64 GiB. No compute upgrade was made during this repair.

## Changes

1. Hourly jobs recover discovery after six hours and split work between recent
   sources and historical backlog. Persistent progress identifies active files;
   overlap attempts are visible, and SQL/idle transaction timeouts limit stalls.
2. Source-specific errors are isolated. They no longer make Azure rerun the
   entire daily ingestion every five minutes.
3. Inputs validate completely, save 25,000-row source batches, then publish in batches of250 complete input/location/date identities, with
   month completion recorded only after all groups finish. Resume uses the exact retained
   original, including after a transient failed publication. Identical values
   keep their existing valid evidence. A narrow per-key revision watermark
   prevents an older intermediate revision from undoing a newer equal-value
   observation without rewriting every unchanged wide price row.
4. City ZIPs publish valid members while retaining individually identified
   conflicting PDFs for review. Readable milk narrative PDFs are distinguished
   from price-table extraction failures; their actual price Excel remains parsed.
5. Colombia and USDA source adapters handle verified historical layouts while
   preserving currencies, units, price basis, dates, locators and source quality.
   Superseded official originals can be replayed without replacing current URL
   pointers. Originals, prior observations and OCR readings are never deleted.
6. The health endpoint distinguishes connectivity from execution freshness and
   overdue recent publications. An hourly watchdog logs degraded automation;
   external email/SMS alert delivery is not configured by this change.

## Validation evidence

- Combined parser/runtime suite: 197 tests ran, 194 passed and three optional
  PostgreSQL integration tests skipped in that invocation. Those three real
  PostgreSQL tests passed separately using temporary tables only. Three further
  native-validation/resume deadline regressions also passed.
- Real PostgreSQL fixtures cover interrupted monthly publication, exact resume,
  changed-value provenance, unchanged revisions and fair scheduler selection.
  The final checkpoint verifier passed in 62.03 seconds against frozen runtime
  fingerprints, including actual second-batch COPY rollback, first-batch reuse,
  month/watermark rollback and OCR completion only after full publication.
  A local HTTP fixture verifies 304 checks, changed bytes at the same URL,
  preservation of both original revisions and retry after extraction failure.
- Colombia: 184 original files with matching SHA-256; 149 parse natively into
  37,482 records, 643 source-quality records remain reviewable, 32 require OCR,
  and three retained explicit source/layout exceptions at that checkpoint. Eleven current September
  originals produce unchanged identities, dates, values, units and locators.
- International: 119 real documents replayed, 92 accepted and 27 rejected with
  explicit reasons. Of 116 previously failed reports, 89 now recover 6,539
  historical observations. The current Miami source yields 76 quotes; Boston 35.
- DANE's 35 clean input annexes passed independent full positive-cell equality.
  Source-conflicting January 2026 is deliberately excluded from that total.

## Remaining source limitations

The historical queue is still substantial. Native recovery counts above are
parser validation results; cloud publication must be verified independently.
Scanned or broken-font PDFs still need actual provider OCR. The blank Corabastos
18 February 2025 template cannot supply prices; two compact March 2025 exports now parse their legible rows with individual clipped-name reviews. Native USDA TXT discovery now reaches November 2018; access to the alternate MyMarketNews archive remains unverified. Two
September 17 city PDFs print September 18, and the January 2026 input annex has
mixed printed years. These exceptions retain their originals and precise errors.

The B1ms database limits repair throughput. Bounded transactions and checkpoints
reduce repeated work but do not imply unlimited ingestion capacity. Observe
freshness and backlog after deployment before deciding whether a separately
approved capacity increase is justified.

## Operations

Use `python -m pipelines.ingestion.audit_automation --output /tmp/agro-audit.json`
for a read-only current snapshot. Apply the additive SQL migrations before
deploying this runtime. On an active database, build the two supporting indexes
concurrently and verify `pg_index.indisvalid`; do not accept an incomplete index
left by a canceled build. Deploy with `infra/deploy_ingestion.py --code-only`
once schema and role grants are ready. The deployer verifies the exact package
fingerprint against the running authenticated health endpoint.

For operational checks, `POST /api/run-check?asset_url=<registered URL>` uses the
same real archive/parser/lock path, with no provider OCR requests. A caller
timeout alone does not establish failure: inspect the durable `ingestion_run`
record, final asset status, published rows and original Blob hash.

## Expanded audit and automatic recovery (27 September UTC)

Both Azure timer-disable overrides were removed and verified absent. The daily
schedule is `0 0 23 * * *` (18:00 Colombia), with hourly backfill at minute15 and
an automation watchdog at minute45. Always On is enabled. Restoring the timers
triggered the automatic run `12d74425-28cc-4ab5-a9b2-b91f372c59df` at04:59UTC;
by05:27 it had completed32 assets and retained24,887 rows. The current public
coffee and daily APIs then returned HTTP200 with COP2,105,000 and431 Sep25 DANE
prices. A large World Bank insertion hit the300-second SQL timeout, motivating
bounded, prevalidated official quote batches with durable progress. These are
observed checkpoints, not a claim that the complete historical queue has finished.

Further source checks found and fixed:

- Monthly PDF percentage matrices were misidentified as monetary prices.
  The previous `dane-monthly-bulletin` output is now withheld by an additive
  publication view;26,589 legacy rows and all originals remain stored. Only
  table-local monetary evidence permits new PDF prices. These legacy bulletin
  rows were not the canonical product price projection used by the frontend.
- February2015 input workbooks now yield all6,394 independently counted current
  prices across15 categories. March2015 monthly annexes yield398 prices with the
  correct current month. Excel percentage formats are normalized per cell;
  corrected metadata receives versioned provenance instead of overwriting rows.
- FNC's six price sheets contain20,218 observations,11,551 beyond the existing
  national daily series; ex-dock prices extend to1913. Additional PDF references
  include pasilla and the separately labeled New York futures quote. Monthly,
  annual, bonus, futures and producer prices retain their distinct units/bases.
- All209 registered international originals were checked:180 parsed reports,
  43,176 valid observations, one ambiguous quote reviewed,29 rejected/unavailable
  files. Older official TXT reports add187 valid observations and88 review rows
  in two2018 fixtures. All396 printed primary/mostly/exceptional ranges reconcile.
- All184 previously failing Colombian originals were retested:151 now parse,
  32 need OCR, one is a blank template. Existing149 native-file value digests
  match exactly. New Colombian coverage includes compact Corabastos reports and
  separately identified Porkcolombia tercile averages.
- A previously published USDA SOLIDAGO quote with contradictory repeated
  `mostly` qualifiers is withdrawn by the publication view; its original row
  remains intact. Newer review findings suppress only the same document/locator;
  a later corrected extraction can publish a new immutable revision.
- Seasonal comparisons use complete COP/kg years only and retain actual original
  document IDs for each individual month. Mixed-unit or ambiguous years remain
  stored with explicit review reasons. FNC monthly means use reported days only.

The expanded native/runtime suite passed239 tests (ten opt-in database tests
skipped in that invocation). Separate real PostgreSQL TEMP tests verify revision
chronology, atomic rollback, review withdrawal/correction and seasonal provenance.
Bulk FNC projection retained8,667 source rows as8,666 unique daily dates; its
source repeats one date with the same price. Publication took2.773s in isolation
and21.673s under concurrent database pressure.

Actual visual PDF checks cover13 DANE pages and9 FNC/USDA pages, plus the
Colombian audit samples. These include units, package sizes, minimum/maximum,
classifications, dates, percentages, page continuations and unreadable headings.
Representative sampling is distinguished from full independent cell reconciliation
and from actual cloud publication in the source matrices.

Several pages also contain chart/prose prices and aggregate supply figures that
remain retained context, not structured quotes. Weekly SIPSA bulletins are a
separate uncovered family. The source inventory and known limits are documented
in [the DANE coverage matrix](DANE_SOURCE_COVERAGE_2026-09-27.md).

### Follow-up live findings and publication checks

The automatic run `659b6d01-e198-425c-9581-d2929355c312` started at06:08UTC
without a manual invocation. It fetched the new TRM original, completed the FNC
workbook and additional city reports. The FNC supplement reconciles all11,551
additional observations exactly. The unchanged workbook contains one national
price that becomes eligible on27September, increasing the validated total to
20,219; a daily Colombia-date checkpoint now prevents HTTP304/same-hash checks
from hiding newly eligible dates.

This live run also reproduced five-minute SQL timeouts while publishing a whole
seasonal set, a municipal input month and the current supply workbook. Those
failed attempts were recorded as failures. Subsequent supply catch-up completed,
as detailed below. Seasonal publication commits250 complete years per batch;
input and supply publication now commit250 complete source identities per batch.
Seasonal refresh also has a separate five-minute budget before yielding to fresh
files, with explicit deferral reporting. Completing all seasonal history remains
unproven if repeated comparison of the unchanged prefix consumes that allowance. The database remains on its
existing capacity. Original documents and committed historical rows are retained
through timeout/retry paths.

The previous official-reference request computed latest/previous quotes from all
historical revisions and exceeded the web query timeout. Migration007 and
`official_catalog.py` move that computation into ingestion. The Azure bootstrap
completed all1,217 identities with zero dirty entries. Quote/review invalidation,
concurrent refresh, withdrawal, bootstrap and revision selection have separate
PostgreSQL tests. Web release `5764d5c8a9a54c5295c897c8d75ee00f` returned HTTP200
for cacao, pork, Corabastos, cattle and palm samples in0.265–1.671seconds. DANE
daily, regional, scoped inputs and input detail also returned HTTP200; the scoped
Antioquia catalog contains966 inputs. This checks those endpoints independently:
the broader unified catalog still timed out in the first follow-up test and is
being investigated separately.

Runtime regression evidence at this checkpoint:307 tests collected,242 passed,
65 opt-in PostgreSQL tests skipped. Dedicated actual PostgreSQL runs separately
covered the cache, coffee date rollover, supply, milk/rice, seasonal batches,
retained replay and input revision behavior. Test artifacts distinguish local
database correctness from live Azure timing and publication.


### Verified current-source catch-up and durable supply publication

On27September, the registered2026 supply workbook completed in cloud run
`f0b18f47-7f53-43f7-aef7-d951519cef46`,06:56:44–07:13:43UTC. It published30,260
monthly groups with zero errors. The independent check reconciled18 groups across
nine months, including quantities, reporting days, dates, original IDs and source
row ranges. The full81,111,242-byte original downloaded from Azure Blob matches
its SHA-256 document ID. The new annual supply summary is also archived as context.

The current annual milk workbook published all1,456 observations across January–
July2026; all1,456 historical values and six June/July application projections
matched the source. The current FNC PDF's pasilla and New York references both
match their printed values, explicit normalization and original IDs. All four
current-source originals match their complete Blob byte hashes. Verification was
read-only and did not redownload official sources or invoke OCR providers.

The August municipal input workbook validated38,248 native observations and
committed seven250-identity groups during its short operational check. Its asset
correctly remained pending with no source-complete marker; this is durable partial
progress, not a claim that all August prices finished. Checkpoint deferrals are
now eligible on the next automatic invocation instead of waiting another hour.

Supply-v5 validates the entire original and rejects malformed late rows before
any publication. It then saves250 complete market/food/month identities and each
checkpoint atomically, newest month first. Pending validated supply resumes the
same retained bytes before checking a mutable URL again. All30,260 current groups
and metadata reconciled under local publication/revision stress; fourteen
PostgreSQL/deadline checks covered interruptions, rollback, stale/equal revisions,
metadata corrections and source-completion markers. Local timings are separate
from the observed cloud runtime above.

Real Gemini checks used four provider requests for two paired page readings.
The broken-font Porkcolombia page remained reviewable because its transcriptions
were not safely publishable. An old queued monthly cover exposed an obsolete OCR
candidate; queued DANE daily/monthly pages now recheck native eligibility before
using cached readings or requesting OCR. Originals, images and readings remain
retained. This verifies provider execution and conservative publication, not a
claim that the OCR backlog has completed.


### Live source delivery and frontend read paths

Migrations008–010 were built concurrently and verified valid/ready. They cover
catalog dates/names, narrow supply-history totals, and historical product filter
identities. Supply endpoints for Armenia/Mercar and Bogotá/Corabastos changed from
HTTP503 to HTTP200 in2.7–2.9seconds, retaining165 months fromJanuary2013 through
September2026. September detail sums match the historical totals and current
original IDs. Four local PostgreSQL parity tests cover118,802 fixture rows,
scopes, metadata, unmapped foods, zero quantities and future exclusion.

The Palmira raw-milk filter-options query changed from a15-second timeout to
0.274seconds using the covering index. The full local service check returned166
historical points; a public request returned HTTP200 with July2026 COP2,120.54
per litre and the selected market/unit/series filters.

The source-content API served the current88,645-byte FNC PDF and124,057-byte milk
Excel with `X-Source-Storage: azure-blob`. Both complete response bodies matched
their immutable document SHA-256 values. This checks delivery through the actual
application, in addition to the separate storage integrity checks.

The monthly catalog shares one recent-row snapshot across department requests,
aggregating with integer cents and PostgreSQL-compatible numeric rounding. It
retains the SQL oracle's identities, units, date windows and prior-month rules.
All reads share a read-only repeatable-read transaction; failures cannot publish
partial snapshots, and outer caches honor the snapshot expiry. Eleven tests
cover real PostgreSQL parity, large retained history, decimal edge cases, failed
refresh and expiry behavior. Source dates and historical aliases are retained.


### Automatic execution and final frontend regression repair

Worker release `0a7d2d94c963c387b60a512768910c28f885b2df6c1f3438320d1c443abf8eb3`
started run `8ab92e97-d575-477f-8b58-b2afd576c437` automatically at
07:27:40 UTC on 27 September. By 08:00:22 UTC it had processed 41 assets and
86,047 rows, including city reports, input annexes, milk and historical rice.
Those are processed-row counts, not a claim that every row was newly inserted.
The run continued source ingestion after recording a seasonal SQL timeout. It
finished at 08:02:41 UTC at the intended 35-minute budget, retaining 1,709 rows
from the next city ZIP for continuation. Its status is correctly partial, not
failed or fully complete.

The final market browser checks exposed another real failure: both supply-history
UI tests encountered HTTP503 while loading the market page, before the supply
tab was available. Exact-market metadata now counts eligible identities without
building every market's full price payload. Product lists select complete winning
quote keys first, then load their payloads. The market directory likewise counts
identities without classifying every historical quote. Six real PostgreSQL tests
cover parity, source eligibility, missing references, supply-only markets and
complete winning quote identities. These fixes are in commit `03add73`.

The product regression exposed a separate avocado detail timeout in filter
options and classification reads. Narrow option reads retain an exact fallback
for ambiguous whitespace/case identities; classification still comes from the
stored source classification, including overrides and absent classifications.
Four real PostgreSQL cases and TypeScript validation passed. Additive indexes
011–013 support these reads; index validity and the deployed regression results
are recorded separately from successful builds.

The independent five-minute seasonal allowance protects fresh source work, but
the observed 300-second seasonal SQL timeout remains unresolved. Bounded actual
PostgreSQL plan and retention metadata checks found no broad anti-join scan,
recursive retention trigger, missing primary key, or missing worker permission.
They do not prove that execution-time contention or retention-write cost caused
the timeout. No database capacity upgrade or speculative SQL rewrite was made.


The September17 city ZIP subsequently completed its valid-member publication in
cloud run `e7179191-c2e2-4287-b104-682c9ec956d5` at 08:05:09 UTC: 2,379
observations, zero execution errors. Its asset remains explicitly `review` for
the two PDFs whose internal date is September18. The hourly OCR trigger fired
at 08:05 and recorded `skipped_overlap`, proving the shared lock prevented a
second writer. This manual targeted catch-up is separate from the preceding
automatic run.

A follow-up UI correction labels calculated range midpoints only when the
source metadata explicitly identifies that statistic. Published weekly means
retain their literal value and a distinct label. Six desktop/mobile browser
checks passed with deliberately unequal mean/midpoint fixtures; build and
TypeScript also passed. Browser emulation is not a native simulator run.
