# AgroAmigo news task and UI follow-ups

## Activation status

**Prepared, not scheduled.** No cloud task ID or verified next-run time exists. This session exposes no scheduler or Workspace Agents creation tool. The browser integration returned `Invalid browser service environment`. No local automation, paid API replacement, Azure news import, or account upgrade was created.

The user authorized a daily subscription-funded cloud job using **GPT-5.6 Luna**, broad source discovery, categorization and story expiry. The proposed run time is **06:00 America/Bogota, every day** (11:00 UTC). The complete self-contained request is in [news-cloud-prompt.txt](news-cloud-prompt.txt), with task configuration in [news-cloud-job.json](news-cloud-job.json) and an executable [Spanish news collector](../../pipelines/news/README.md). Its catalog now contains **95 source candidates (88 enabled for access checks, seven disabled)** across eight groups; the original 71-source task list is retained for the preceding backfill audit. Most candidates have not had their listing/feed completeness or publication rights verified. The seven-source measured volume must not be extrapolated to this broader catalog.

To activate: in ChatGPT web, select Work, choose **Advanced → GPT-5.6 Luna**, and paste the prompt. Review the created task in **Scheduled**, verifying cloud execution, model, timezone and next run. The model name in a prompt alone is not verification of the scheduler's model setting. If unavailable, report the limitation rather than silently choosing another model. [Official scheduling documentation](https://learn.chatgpt.com/docs/automations?surface=web), [model controls](https://learn.chatgpt.com/docs/models).

The output is a private research report and JSON until an authorized AgroAmigo import connection exists. There is no verified unattended delivery to Azure. No sources were granted republication rights by this work. Prior research: [news integration](../NEWS_INTEGRATION_RESEARCH.md).

## Expiry rules

| Content | Default feed lifetime from publication | Earlier cutoff |
| --- | --- | --- |
| General news, research, policy | 14 days | Retraction, correction or supersession |
| Spot/daily prices | 48 hours | Explicit quote validity |
| Market trend analysis | 7 days | Superseded analysis |
| Operational weather and road disruption | 48 hours; review daily | Explicit end of forecast/event |
| Seasonal weather outlooks | 14 days; review daily | Newer official outlook |
| Phytosanitary warnings | 14 days in feed; review daily | Official correction/revocation |
| Calls, applications, courses, events | 14 days | Relevant application deadline/event end |

Expiry controls visibility in the news feed; it does **not** declare a hazard resolved or a law/recall invalid. Re-fetching never resets the clock. Missing publication dates go to review. Corrections preserve provenance, subject to source retention rights.

## UI changes in this work

- Mi finca: current model weather, next 24 hours and seven days, automatic visible-page refresh every 15 minutes, stale-state labeling, original responses preserved through the existing Azure weather snapshot mechanism. Open-Meteo data is model output, not a sensor at the farm. [Provider documentation](https://open-meteo.com/en/docs).
- Farm location: use a map/GPS, with municipality and landmark search; searching explores the map without silently relocating the saved pin. Photon supplies OSM place search with a debounce, bounded cache, limited concurrent requests and Colombia filtering. Public demo service has no availability guarantee; set `PHOTON_SEARCH_URL` for a different Photon endpoint as traffic grows. [Photon docs](https://github.com/komoot/photon/blob/master/docs/api-v1.md), [service terms](https://github.com/komoot/photon#demo-server).
- Removed recent/all-history selectors and their redundant badges from catalog, detail, supply, comparison and reference views. Existing recent-data defaults remain; actual dates and historical reference/seasonality data are retained. Price charts render the dataset supplied by their endpoint without an extra period switch.
- Source/help/credit links use underlines, blue link text, focus states and larger touch targets.
- Fixed page viewport scale and disabled native WebView page zoom on iOS/Android. MapLibre retains its own map interaction. Mobile input sizes are at least 16px to avoid input-focus zoom. Browser/OS accessibility overrides may still control browser zoom.

See the dated [application validation report](../VALIDATION_2026-09-08.md) for subsequent deployed releases and native checks. Native wrappers require a new release for their explicit WebView zoom setting; shared web changes are delivered through the hosted web app.

## Verification

- TypeScript check: `npx tsc --noEmit --incremental false` passed.
- iOS: `flutter analyze lib/main.dart` and `flutter test` passed. Android: `./gradlew :app:compileDebugJavaWithJavac --offline` passed. These are analysis/test/compilation checks; no signed release or store upload was performed.
- Browser coverage includes desktop Chromium, mobile Chromium and iPhone WebKit. Checks exercise weather freshness and recovery, hourly/daily views, evidence links, GPS persistence, map search without relocating the farm, map zoom with page scale 1, and footer links above the fixed navigation.
- Live weather verification requested a Colombian farm point, received current conditions, 168 hourly records and seven daily forecasts, then read the saved original response back through the Azure evidence endpoint. The archived JSON matched the returned weather payload, and its evidence metadata included the same current conditions.
- Historical supply records remain accessible through the API after removing the UI history switch. Monthly totals, citations and retry behavior are covered separately.

Some pre-existing native integration/validation scripts still exercise the retired manual-coordinate and full-history UI. They were not used to claim native end-to-end coverage for this change. A signed device release and store upload remain separate work.

Final focused browser outcome: **35 checks passed across the runs**. The main selection covered 29 cases; one desktop case was rerun successfully with an isolated output directory after another run removed its trace files. Six additional GPS permission/persistence cases passed after updating the legacy test fixture to seed storage only once and compare coordinates numerically. This is focused coverage, not a claim that the complete historical integration suite passes.
