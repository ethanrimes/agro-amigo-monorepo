# Observed news publication volume

Checked 8 September 2026 UTC. Count window: **24 August through 6 September 2026 inclusive**, 14 calendar days. September 7 was excluded because it was still in progress in Colombia. These are publisher-reported dates, not a two-week first-seen crawler log.

**Seven measurable source feeds/sections contained 86 dated items, averaging 6.14 per calendar day.** The combined daily count ranged from **1 to 15**. These are article/announcement URLs before cross-publisher event deduplication and AgroAmigo relevance filtering. This subtotal is not the total output of every publisher mentioned in the broader research.

| Source / section actually counted | Items in 14 days | Mean/day | Scope |
| --- | ---: | ---: | --- |
| [La Nación — Economía](https://www.lanacion.com.co/category/noticias-economia/) | 19 | 1.36 | Economics section, including non-agricultural finance/tax stories. |
| [Redagrícola](https://redagricola.com/) | 19 | 1.36 | All countries in the public posts feed; not all Colombia-relevant. |
| [Portafolio — Agro](https://www.portafolio.co/economia/agro) | 18 | 1.29 | Agriculture section only. |
| [ICA news](https://www.ica.gov.co/noticias) | 16 | 1.14 | Agricultural and animal-health/institutional announcements. |
| [AGROSAVIA news](https://www.agrosavia.co/noticias) | 9 | 0.64 | Research, outreach and institutional items. |
| [UPRA news](https://upra.gov.co/es-co/sala-de-prensa/noticias) | 3 | 0.21 | Published news listing. |
| [Agronet news](https://agronet.gov.co/noticias) | 2 | 0.14 | Published news listing; may repeat originating agencies. |
| **Measured subtotal** | **86** | **6.14** | **Seven distinct feeds/sections.** |

Redagrícola's explicit Colombia category returned **one item** in this window. That is a subset of its 19 items and is not added to the total. It is not a complete classifier of relevance: international crop or commodity stories can matter to Colombian farmers, and category tagging can be incomplete.

For scale, the same dated query across **all of La Nación** returned **415 posts, about 29.6/day**, compared with 19 in its economics section. The 19 are included in the 415; these figures must not be added. Monitoring whole general-news websites is therefore a substantially larger workload than selecting agricultural/business sections. It still does not imply that all those stories are useful to farmers.

## What remains unmeasured

The initial research also mentioned Agronegocios/La República, CONtexto Ganadero, Diario del Huila, La Patria, La Crónica del Quindío, El Colombiano, El País, El Espectador, Caracol, FNC/Cenicafé and other official sources. A reliable complete 14-day total for all those sources has **not** been established:

- Agronegocios section requests returned HTTP 403. Search-rendered category pages were accessible but did not provide a trustworthy complete dated archive for this count. No access control was bypassed.
- CONtexto Ganadero's `/rss.xml` returned 404, a tested section route returned 404, and the root response did not yield a dated listing suitable for counting. Search results included stale cached dates; they were not counted as current throughput.
- Diario del Huila's public WordPress response did not honor the tested one-item/field-selection parameters, returning a larger embedded-content payload. It was not used to infer a date-filtered count. No article body was saved in these artifacts.
- FNC's search-rendered national listing showed two entries within the window, but this was not verified as the complete publication stream. Its restrictions on automated copying were already documented; no broad crawler was run against it. Those two entries are not included in the seven-feed subtotal.
- The remaining general/regional outlets and official sources were not counted in this audit. Their contribution must not be silently assumed to be zero.

Thus **200–500 new candidates/day was an earlier cost-sizing scenario, not measured output from the identified sources**. This audit replaces that assumption for the seven-feed core only. It does not justify claiming that the complete wider source set publishes six items/day or that a fixed number of relevant, unique stories will exist for every product each day.

## Method and traceability

The two WordPress sites were queried with public `posts` endpoints, a publication-date window, `per_page=100`, selected metadata fields and relevant category IDs. La Nación's economics category ID is 22; Redagrícola's Colombia category ID is 645. All three queries returned exactly the number of items in their `X-WP-Total` header and all dates fell inside the requested window; no truncated ten-item RSS feed was used to estimate a two-week total.

AGROSAVIA dates came from the listing cards' `data-date` attributes. UPRA and Agronet supplied dated HTML cards. Portafolio's agriculture listing supplied `DD.MM.YYYY` dates. These listings extended to dates before the start of the window. ICA's five-item pages were followed until the listing reached dates before August 24. Within each source, duplicate links were removed.

Counts use each publisher's stated publication date. The WordPress records retain `date_gmt` for audit, but this calculation does not shift every publisher's calendar date into Colombia's timezone. This can matter near midnight, especially for Redagrícola's international publishing operation. A production ingestion job should normalize timestamps while preserving the original date and timezone.

This is a snapshot of publicly listed/dated posts. Backdating, corrections, updated evergreen pages, removed articles, omitted custom post types or incomplete editorial indexes can make first-seen daily crawler volume differ. Updating an existing cacao reference page is not necessarily a new story. The code checks extraction completeness within the inspected endpoints; it cannot prove completeness of a publisher's whole editorial system.

- [observed-counts.json](observed-counts.json): source URLs, exact API query URLs, dates, article links, per-day counts and coverage limits. No full article text or images.
- [summary.json](summary.json): combined daily counts and the whole-site La Nación comparison.
- [measure.py](measure.py): bounded, read-only reproduction script. It fixes the historical window intentionally.

## Effect on the daily-job budget

At the observed seven-feed rate, roughly **184 classifications/month** would be needed if future publication rates resembled this sample and every new record were classified once. Using the prior assumed 1,000 input + 200 billed output tokens per record, Gemini 3.8 Flash would cost about **$0.28/month** at its current introductory rates; similarly batched headline-only processing is smaller still. This is a model-only projection, excludes collection/hosting/rights, and is not a guarantee about future story volume or exact token usage. Even a small allowance has substantial room for this particular core set.

The larger $10–$25 monthly model allowance remains an optional reserve for a broader source list, richer excerpts and retries, not the measured cost requirement of these seven feeds. See the [daily-job cost model](../news-model-benchmark/COST_ESTIMATE.md) and [Google's date-dependent prices](https://ai.google.dev/gemini-api/docs/pricing).
