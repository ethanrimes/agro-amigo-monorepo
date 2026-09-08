# AgroAmigo news model experiment

Run 7 September 2026 Pacific / 8 September UTC. This is an API-backed **synthetic smoke benchmark**, not a measurement of publisher coverage or real-world editorial accuracy. No news was published. The user authorized experimentation using their Gemini key and Azure subscription.

## Recommendation

Use **Gemini 3.8 Flash with low thinking for the first news pilot**, with ordinary scheduled code collecting authorized feeds and a model classifying only new candidates. It matched all fields on all 80 synthetic classifications, and the projected cost was about $2 per 10,000 batched headlines at the current promotional price. Its projected premium over the cheapest successful option was about $1.27 per 10,000 headlines. That difference does not justify sacrificing useful topic/geography accuracy at pilot volume. This finding applies to this news-routing prompt, not to the app's OCR, forecasting, or agronomic analysis.

**Azure GPT-4.1 mini is a credible cheaper alternative** and worked in the user's subscription. Revisit it after evaluating a representative set of permitted real articles. GPT-5 mini with minimal reasoning was also accessible and inexpensive, but made more tagging errors here. This is not evidence about that model with higher reasoning effort or a different prompt.

## Fixed comparison

Forty authored Spanish headlines and reference labels were written before the first call. The same Spanish instruction, JSON schema and title inputs were supplied to every model, in batches of eight, twice. Ground-truth labels were never sent. The cases cover crops, inputs, named markets, transport, international commodity relevance, ambiguous headlines, irrelevant keyword matches and two artificial prompt-injection attempts. These are invented test cases, **not claims that the described events occurred**.

The comparable table uses the **first 32 cases, each repeated twice**. Azure's default content filter rejected the final batch of eight, which contained the adversarial cases. That batch is excluded from **every** model in this comparison; its failures remain in the raw records. This is 32 distinct cases, not 64 independent examples.

| Model / service | Relevance decisions correct | All fields correct: relevance, topics, geography | Median request, eight headlines | Estimated inference / 10,000 headlines |
| --- | ---: | ---: | ---: | ---: |
| Gemini 3.1 Flash-Lite / Google | 62/64 | 50/64 | 1.46 s | $0.88 |
| Gemini 3.5 Flash-Lite / Google | 64/64 | 49/64 | 1.41 s | $1.19 |
| Gemini 3.5 Flash / Google | 64/64 | 64/64 | 1.38 s | $3.83 |
| **Gemini 3.8 Flash / Google, low thinking** | **64/64** | **64/64** | **1.42 s** | **$1.99** |
| GPT-4.1 mini / Azure | 62/64 | 56/64 | 2.59 s | $0.73 |
| GPT-5 mini / Azure, minimal reasoning | 64/64 | 44/64 | 2.98 s | $0.81 |

The successful full 40-case Gemini runs returned valid rows for all 80 classifications each. Gemini 3.8 Flash matched all fields on 80/80; 3.5 Flash matched 79/80, omitting the fertilizer topic from a cacao-fertilization headline once. Flash-Lite 3.5 returned one unsupported Corabastos tag and sometimes assigned Colombia to an unlocated ambiguous headline. Some strict-score errors are locations on correctly discarded entertainment stories, which would have little product impact. A separately recorded, **post hoc** operational metric ignores location on correctly discarded stories: 62/64 for 3.1 Flash-Lite, 59/64 for 3.5 Flash-Lite, 64/64 for both Flash models, 59/64 for GPT-4.1 mini and 52/64 for GPT-5 mini. This secondary metric was not predefined and must not be presented as an independent validation.

The final Azure batch had two artificial instruction attacks. Azure rejected the whole batch, so this experiment cannot attribute the rejection to a particular record or claim the underlying GPT model resisted those attacks. No filter was disabled and no blocked input was disguised or retried. Operationally, preserve a blocked batch for review and prevent one rejected batch from suppressing unrelated news collection. Both Gemini models in the Lite comparison and Gemini Flash handled those two artificial examples without following the embedded instructions; two examples do not establish general prompt-injection resistance.

No model-specific prompt tuning was performed. Gemini 3.1/3.5 used minimal thinking (2.5 was configured without thinking); GPT-5 mini used minimal reasoning; GPT-4.1 mini used temperature zero. Gemini 3.8 rejected the minimal setting with HTTP 400 and was then run with supported low thinking; both the configuration failures and successful run are preserved. This was a parameter correction, not a content-filter change. Concurrent requests were limited to two. Latency is local wall time from this Mac, includes network/service overhead, and is based on only eight successful requests per model in the shared comparison. It is not a production latency guarantee. Google and Azure were run at different times, not in randomized interleaved trials.

## Prices and measured cost

The projected amounts use each service's returned input/output token counts, with thinking tokens included where reported, multiplied by uncached pay-per-token list prices. No grounding/search tool was enabled, no provider Batch API was used, and no reserved throughput was purchased. The eight-headline grouping is ordinary request batching, distinct from a provider's discounted asynchronous Batch API.

| Model | Input / million tokens | Output / million tokens |
| --- | ---: | ---: |
| Gemini 3.1 Flash-Lite | $0.25 | $1.50 |
| Gemini 3.5 Flash-Lite | $0.30 | $2.50 |
| Gemini 3.5 Flash | $1.50 | $9.00 |
| Gemini 3.8 Flash, promotional through 31 December 2026 | $0.75 | $3.75 |
| Azure GPT-4.1 mini, Global Standard | $0.40 | $1.60 |
| Azure GPT-5 mini, Global Standard | $0.25 | $2.00 |

Google rates were checked against [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing). Azure rates were retrieved from Microsoft's public [Azure Retail Prices API](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices); selected meter IDs, East US 2 region, prices, units and effective dates are saved in [azure-retail-prices.json](azure-retail-prices.json). Global Standard rates must not be substituted for regional, data-zone, priority, fine-tuned or provisioned offerings.

Google lists Gemini 3.8 Flash at **$1.50 input / $7.50 output per million tokens from 1 January 2027**, twice the introductory rates. At the same measured usage, its projection would rise from about $1.99 to $3.99 per 10,000 batched headlines. The runner freezes the September 2026 rates, so update them before interpreting a future experiment's costs. [Google pricing](https://ai.google.dev/gemini-api/docs/pricing).

Total estimated list-price inference for all successful test calls: **$0.07465075, under ten US cents**. This is a token-based estimate, not a reconciled billing receipt. Free allowances, credit balances, cached-input discounts and actual invoice adjustments were not inspected. Crawling, hosting, storage, retries, publisher permissions and integration maintenance are excluded. Longer excerpts, per-article calls, larger JSON outputs and additional reasoning will change the cost. The cost projection is for a similar distribution and batch size, not a fixed price per news article.

## Actual account access findings

- The supplied Gemini key authenticated successfully; it was read in memory, placed in a request header, and never logged or committed. The key file is ignored by Git and untracked.
- Gemini 2.5 Flash-Lite was listed by `models.list`, but generation returned HTTP 404 stating the model is unavailable to new users and recommending 3.5 Flash-Lite. Consequently its low advertised price is not an actionable option for this account. The general [deprecation page](https://ai.google.dev/gemini-api/docs/deprecations) did not disclose this account-specific restriction. Actual inference checks are stronger availability evidence than catalog listings.
- Azure's Visual Studio Enterprise subscription was Enabled, with the spending limit On. There were initially no Cognitive Services accounts and its provider was unregistered.
- The experiment registered `Microsoft.CognitiveServices` and created one temporary S0 OpenAI resource, `agroamigo-news-eval-20260908`, in `agroamigo-demo-rg`, East US 2.
- GPT-4.1 nano and GPT-5.6 Luna Global Standard deployments were rejected with `InsufficientQuota`: available capacity **zero**. GPT-5 nano real-time quota was also zero. Catalog visibility does not imply usable deployment quota. No quota-increase request was submitted.
- GPT-4.1 mini and GPT-5 mini Global Standard deployments succeeded and completed inference. A GPT-4.1 nano Global Batch deployment also succeeded, but no batch job was submitted: its [24-hour processing window](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/batch) is a separate workflow from prompt headline updates. Batch-only quota should not be reported as real-time availability.
- Quota checks in East US, East US 2 and Sweden Central are recorded in [azure-quota.json](azure-quota.json). Positive quota entries for obsolete legacy models do not establish those models remain deployable.
- The temporary Azure account and its deployments were deleted after testing. Provider registration remains; it is subscription configuration, not a running inference workload. No scheduled process, production deployment, fine-tuning job or reserved-capacity commitment was created.

Microsoft states that [Visual Studio Azure credits can fund Azure OpenAI](https://learn.microsoft.com/en-us/visualstudio/subscriptions/vs-azure-eligibility). Enterprise Standard benefits are normally $150/month, but the actual remaining credit balance and exact benefit entitlement were not verified. Existing AgroAmigo services share the allowance. The [offer terms](https://azure.microsoft.com/en-us/pricing/member-offers/credit-for-visual-studio-subscribers/) limit these monthly credits to individual development/test use; production workloads require an appropriate paid subscription. These credits do not pay Google's Gemini API invoices or direct OpenAI API invoices.

## Artifacts and reproduction

- [cases.json](cases.json): frozen authored inputs and expected labels.
- [run.py](run.py): bounded runner, exact prompt, structured schema, provider settings, token accounting and scoring.
- [gemini-results.json](gemini-results.json): initial 2.5 access failures and 3.5 Flash-Lite results.
- [gemini-comparison-results.json](gemini-comparison-results.json): 3.1 Flash-Lite and 3.5 Flash results.
- [gemini-38-results.json](gemini-38-results.json): rejected minimal-thinking parameter, before correction.
- [gemini-38-low-results.json](gemini-38-low-results.json): successful 3.8 Flash low-thinking results.
- [azure-results.json](azure-results.json): both accessible GPT models, including filter rejections.
- [comparison-summary.json](comparison-summary.json): shared-case metrics and detailed mismatches.

From the repository root, with `requests` available:

```sh
.venv/bin/python docs/research/news-model-benchmark/run.py \
  --models gemini-3.5-flash-lite gemini-3.8-flash
```

The runner accepts `GEMINI_API_KEY` or `--key-file`; it never prints the key. Azure execution needs a newly created compatible test account and named deployments because the temporary resource was removed. The script does not provision resources. Default result names use a UTC timestamp so reruns preserve the original evidence.

Before treating the recommendation as a production model selection, evaluate permitted real publisher metadata with independently reviewed labels, duplicate stories, stale dates, local place aliases, sponsored content, multilingual commodity news and sparse product coverage. Measure entity precision and missed useful stories separately. Deterministic checks should preserve original titles/URLs/dates and require evidence for exact market/place matches; model-generated tags must not silently change price data, weather alerts or farm recommendations.
