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
3. Inputs validate completely, save 25,000-row source batches, then publish each
   month atomically with a durable checkpoint. Resume uses the exact retained
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
