# Noticias agrícolas en español

A bounded, resumable collector for Spanish-language source articles, with a separate editorial classification handoff. It includes international news when there is a plausible connection to Colombian crops, inputs, weather, trade or logistics; an article need not mention Colombia. Publication facts and inferred Colombian effects remain separate.

**Execution status:** runnable locally; no daily cloud scheduler, Luna API invocation, Azure news importer or public app news feed is connected. The requested subscription-funded cloud task remains [prepared, not scheduled](../../docs/automation/README.md). This collector does not use the Gemini key or incur model API charges.

## Source catalog

[sources.json](sources.json) contains **95 candidates across eight groups**, with 88 enabled for bounded access checks and seven disabled. Colombian official, research, trade, national and regional sources are complemented by Spanish international official, specialist and general publications. An enabled candidate is not a verified complete feed or a grant of publication rights. Source names, owners, origins, language, discovery URLs and access status are explicit.

Spanish is checked in article text independently of HTML language and URL. English/Portuguese pages are rejected, including pages reached from a Spanish masthead. We do not translate foreign articles to satisfy the language requirement. The collector respects robots rules, host allowlists, throttling and publisher restrictions; login, paywall and access-denied responses are not bypassed. Rights remain unverified unless explicitly reviewed. No article bodies, thumbnails or source images are persisted; records retain a headline excerpt of at most 20 words, source link, dates and content hash. Research acceptance does not authorize public display.

## Run

From the repository root:

```sh
.venv/bin/pip install -r pipelines/news/requirements.txt
.venv/bin/python -m pipelines.news.cli catalog
.venv/bin/python -m pipelines.news.cli collect --max-seconds 900
.venv/bin/python -m pipelines.news.cli export
.venv/bin/python -m unittest pipelines.news.test_news
```

The initial window is 14 days. Subsequent successful source checkpoints overlap by 72 hours. `--since` and `--end` specify inclusive Colombian calendar dates; the end never exceeds the current time. Source date-only timestamps carry an explicit assumed source timezone. The observation date is never substituted for a missing publication date.

```sh
.venv/bin/python -m pipelines.news.cli collect \
  --source fao --source portal-fruticola --source freshplaza-en-espanol \
  --source omm-en-espanol --since 2026-08-25 --end 2026-09-07 \
  --seeds pipelines/news/verification-seeds.json --seeds-only
```

Use `--state` and `--output` for isolated runs. The default SQLite state and JSON output are under ignored `pipelines/news/cache/`. Preserve that directory between scheduled executions; an ephemeral checkout would lose checkpoints, review decisions, cooldowns and unprocessed URLs. Source pages and article budgets default to two and eight per invocation. Unattempted sources run first on the next invocation. A duration limit is checked between requests; in-flight requests and bounded retries can finish after that limit.

## Evidence and editorial review

The collector only proposes tags. Records with valid Spanish text and an unambiguous in-window publication date enter review; they are **not** labelled as Luna classifications. Publication timestamps come from article metadata or explicit publisher date elements. Masthead, modification, listing and event dates do not silently replace publication dates. Conflicts, insufficient text, parser failures and restricted sources stay visible in reports.

The reviewer opens the original URL, verifies facts and supplies a JSON handoff:

```json
{
  "stories": [{
    "id": "copy from review-queue.json",
    "content_sha256": "copy from that exact record",
    "decision": "include",
    "primary_category": "precios_y_mercados",
    "story_kind": "market_trend",
    "crops": ["café"],
    "inputs": [],
    "transmission_channel": "comercio",
    "factual_label_es": "A concise Spanish paraphrase of verified publication facts.",
    "colombia_relevance_es": "A separate Spanish explanation of the possible Colombian impact and its limits.",
    "impact_is_inference": true,
    "event_id": "shared-id-for-the-same-underlying-event",
    "priority": 75
  }]
}
```

The example placeholders must be replaced. Both text fields must be Spanish, each 5–65 words, with enough combined text to verify language. Categories, crop/input tags and story kinds are defined in [content.py](content.py). `crops`, `inputs` and `transmission_channel` can correct the initial keyword suggestions. The factual source claim must not be replaced by a guessed local price, yield or agronomic instruction.

```sh
.venv/bin/python -m pipelines.news.cli review \
  --reviews reviewed-stories.json --reviewer reviewer-identity
```

The whole handoff is validated before any decision is saved. A changed content hash rejects a stale review. Re-fetching unchanged content preserves original publication, first-seen time, reviewed tags and expiry. Changed text or headline withdraws acceptance and retains the previous record. Retraction/correction/supersession decisions reference another verified collected record and immediately remove the old story from featured results. Cross-publisher event grouping is an editorial task; exact matching headline hashes are only duplicate suggestions.

## Freshness and outputs

| Story kind | Feed lifetime from publication | Recheck |
| --- | --- | --- |
| General, research, policy | 14 days | Before expiry |
| Market analysis | 7 days | Before expiry |
| Spot prices, operational weather, roads | 48 hours | Daily |
| Seasonal weather outlook | 14 days | Daily |
| Phytosanitary warning | 14 days | Daily |
| Event or application | 14 days or earlier verified deadline | Before deadline |

Expiry removes a story from featured news; it does not declare a warning resolved, a law invalid or a forecast fulfilled. Explicit earlier deadlines need the original-source URL. Accepted expired stories remain in the research archive. Expired records do not consume the routine live recheck budget.

- `run.json`: per-source pages, article attempts, errors, backlog and time-budget deferrals. A checked source does not mean its archive was exhaustively collected; `coverage_complete` stays false.
- `records.json`: collected metadata and decisions.
- `review-queue.json`: pending evidence/editorial work and exact-title duplicate suggestions.
- `research-feed.json`: reviewed private research, plus active home and crop selections. Home selection rotates source groups, caps each publisher at two stories and avoids repeated reviewed events. `public_display_authorized` remains false.

SQLite retains source watermarks, article backlog, revisions, run reports, host Retry-After cooldowns and a lease preventing simultaneous runs against the same state. Failed sources do not advance successful watermarks. Source layout changes require targeted adapters and tests; no silent synthetic fallback fills missing facts.

## Verification

The focused suite covers publication/masthead/update conflicts, body-language checks, RSS/Atom extraction, XML entity rejection, source restrictions, private/redirect destinations, robots and rate limits, restart-safe cooldowns, backlog/checkpoint safety, review atomicity and stale hashes, crop correction, content changes, expiry and publisher/event diversity. CI runs it on pushes and pull requests.

[Spanish international research and real collection evidence](../../docs/research/news-global-spanish-2026-09-08/README.md) records the dated live verification. The preceding [two-week Colombian backfill](../../docs/research/news-backfill-2026-09-07/report.md) remains a separate research archive; totals from different collection passes should not be added without canonical/event deduplication.
