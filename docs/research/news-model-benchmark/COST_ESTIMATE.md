# Gemini 3.8 Flash — ongoing news classification estimate

Prepared 8 September 2026 UTC. The user clarified that the intended design is **one daily fetching and classification job**. These are model-inference estimates in USD, assuming 30 runs per month and each new candidate classified once. They are not a quote for a fully hosted crawler or licensed news feed.

## Recommended pilot allowance

**Observed-volume update:** a subsequent [14-day source count](../news-volume/README.md) found 86 dated items across seven measurable feeds/sections, about 6.14/day before relevance filtering and cross-publisher deduplication. At that core-only rate, the excerpt scenario below projects to about $0.28/month. The 200–500/day figures below are sizing scenarios for a larger collection, not measured output of the identified sources. Several other proposed publishers remain unmeasured.

For **200–500 new candidate articles/day**, budget approximately **$10–$25/month for Gemini** if some stories need excerpts. A pipeline using only similarly batched headlines would instead project to about **$1.20–$3.00/month**. These are workload scenarios, not measured publication rates for the proposed source list.

Schedule one Azure job daily, for example at **06:00 Colombia time / 11:00 UTC**. That example time is a proposed implementation default, not a user-selected time. The job collects permitted feeds, deduplicates source URLs, classifies new records, saves permitted headlines and topic mappings in Azure, and exits. Web, iOS and Android read the same stored results. Gemini is invoked only for new or materially changed records; idle time does not consume inference tokens. Azure execution, storage and networking have their own billing. News may be almost a day old between refreshes, so official urgent weather, road and phytosanitary alerts should retain a separate freshness policy.

## Monthly scenarios

| Newly classified stories/day | Stories/month | Batched headlines, measured token usage | Headline plus excerpt, assumed 1,000 input + 200 billed output tokens/story |
| --- | ---: | ---: | ---: |
| 100 | 3,000 | $0.60 | $4.50 |
| 200 | 6,000 | $1.20 | $9.00 |
| 500 | 15,000 | $2.99 | $22.50 |
| 1,000 | 30,000 | $5.98 | $45.00 |

The headline column scales the [shared-case live benchmark](comparison-summary.json), which used requests containing eight headlines, a Spanish classification instruction, a structured response and low thinking. It is about $1.9949 per 10,000 classifications at current rates. It is based on 32 synthetic cases repeated twice, not observed production tokens across a news corpus.

The excerpt column is an independent sizing assumption. Its input budget includes instructions, source metadata, headline and context; its output allowance includes both the returned tags and any billed thinking. With 1,000 input and 200 billed output tokens:

`cost/story = (1,000 × $0.75 + 200 × $3.75) / 1,000,000 = $0.0015`

Reading full articles changes the result: assuming **5,000 input + 500 billed output tokens/story**, 500 articles/day would cost approximately **$84.38/month**. Multi-step agent calls, repeated extraction attempts, large taxonomies and reclassification also consume tokens; the fact that the app displays only a headline does not mean the model processed only that headline.

## Pricing and dates

[Google's Gemini API price list](https://ai.google.dev/gemini-api/docs/pricing) gives Gemini 3.8 Flash Standard rates of **$0.75/million input tokens and $3.75/million output tokens, including thinking**, through **31 December 2026**. From **1 January 2027**, the announced rates are **$1.50 and $7.50** respectively, so every scenario above doubles at identical token usage. No free-tier allowance, caching discount or asynchronous Batch discount is assumed.

No Google Search grounding is included. A collector that already has the relevant permitted RSS/site metadata does not need a paid model search tool just to classify it. Hosting, storage, network, publisher/API rights and maintenance are excluded. Visual Studio Azure credits do not pay Google API invoices.

## Cost controls for implementation

1. Check feeds once daily, deduplicate URLs before inference and classify only new or materially changed records.
2. Start with batches of eight headlines and source metadata; request more permitted context only when necessary.
3. Cache classification by input hash and prompt/model version within source retention terms; user page views should not trigger new model calls.
4. Cap input size, output tokens and retries, record returned usage and enforce a daily application-level spending threshold. Do not treat a provider budget alert as a guaranteed hard spending stop.
5. Review actual token use after a week and revise the estimate before expanding sources or turning on agentic browsing.

The Azure audit found no usable Luna quota; the [quota report](../azure-ai-quota/README.md) records the available alternatives. Gemini 3.8 Flash remains the provisional recommendation from the tested models, pending validation on permitted real news metadata.
