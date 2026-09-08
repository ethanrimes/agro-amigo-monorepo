# Azure AI quota audit — 8 September 2026 UTC

Subscription: Visual Studio Enterprise, `9a04b64b-af19-4519-be50-56ec2acbd855`.

The audit queried quota and model catalogs in all **36 non-global regions** returned for Cognitive Services accounts. Every region returned a successful response. Positive quota entries were joined to the catalog's SKU usage names, excluding entries whose reported deprecation date had passed. This distinguishes a quota entry from a currently listed model. Actual deployment and inference were tested earlier only for GPT-4.1 mini and GPT-5 mini; other positive entries are candidates, not guarantees of service capacity or offer eligibility.

## Useful quota available

The following limits are reported in East US 2 and have matching current catalog entries. Other supported regions are retained in the full snapshot. Limits are not free tokens or monthly credits.

| Capability | Model / deployment | Reported total quota |
| --- | --- | ---: |
| Text classification / chat | GPT-5 mini, Global Standard | 500,000 tokens/minute |
| Text classification / chat | GPT-4.1 mini, Global Standard | 200,000 tokens/minute |
| Reasoning | o4-mini, Global Standard | 100,000 tokens/minute |
| Open-weight text model | gpt-oss-120b, Global Standard | 5,000,000 tokens/minute |
| Other open models | Phi-4 family, Llama 3.3 70B, Llama 4 Scout, Mistral medium/small, Codestral | 20,000 tokens/minute per named model |
| Semantic search / matching | text-embedding-3-small, Global Standard | 1,000,000 tokens/minute |
| Semantic search / matching | text-embedding-3-large, regional Standard | 350,000 tokens/minute |
| Transcription | gpt-4o-transcribe and transcribe-diarize | 400,000 tokens/minute each |
| Lightweight speech | gpt-4o-mini-transcribe and mini-tts | 50,000 tokens/minute each |
| Audio chat | gpt-audio-mini | 30,000 tokens/minute |
| Live voice | gpt-realtime-mini | 40 requests/minute |
| Image generation | FLUX.2-pro, Global Standard | 15 requests/minute |
| Image generation | FLUX.2-flex, Global Standard | 5 requests/minute |
| Asynchronous processing | GPT-4.1, 4.1 mini, 4.1 nano Global Batch | 90,000 enqueued tokens per model's reported quota |

The Batch row preserves the API's exact `Enqueued tokens (thousands)` description; it is not a tokens-per-minute limit. Fine-tuned deployment and developer-tier quota also exists, but it does not authorize standard base-model inference. Generic Model-as-a-Service quota appears as 600 capacity units and matches some Mistral/Cohere catalog entries; the audit does not translate that generic count into a universal throughput or credit entitlement.

**Luna:** no positive GPT-5.6 Luna real-time quota was found in any checked region. The same audit found no positive real-time quota for GPT-5.6 Sol/Terra, GPT-6, GPT-5.4, GPT-5 nano, the listed Claude models or GPT Image. Azure offers [GPT-5.6 Luna](https://ai.azure.com/catalog/models/gpt-5.6-luna), but catalog availability and subscription quota are separate. Its current [Global Standard short-context rates](https://azure.microsoft.com/en-us/blog/gpt-5-6-now-available-in-microsoft-foundry/) are $0.20 input / $1.20 output per million tokens. No Luna accuracy result exists because the earlier deployment attempt was rejected for insufficient quota.

Some Sora quota entries were positive, but did not match a non-expired catalog entry. They are deliberately not presented as verified usable video-generation capacity.

## Scope and cleanup

Azure is moving some models to shared subscription-wide Global and Data Zone pools. Repeated regional listings therefore must not be added together. The CLI scope response identifies GPT-5 mini and GPT-4.1 mini as Global pools. See [Microsoft's quota scope documentation](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/quotas-limits).

The initial snapshot used the older `2024-10-01` Usages API, which omitted the newer scope fields. The audit runner has been updated to the advertised stable `2026-07-01` API for future snapshots. The separate [East US 2 CLI response](eastus2-cli-scopes.json) records scope and allocation using the newer service response.

The earlier benchmark resource had been soft-deleted but still held 20,000 GPT-4.1 mini TPM, 50,000 GPT-5 mini TPM and one nano batch capacity unit. It was permanently purged as part of cleaning up that temporary experiment. A subsequent CLI response confirmed all three allocations returned to **zero**, so the full 200,000 / 500,000 TPM quotas are available again. The initial regional snapshot intentionally retains the pre-purge observations; use the later CLI response for those remaining-capacity values.

No new deployment, inference test, paid commitment or quota-increase request was made in this audit. Quota is permission to allocate throughput; actual use incurs model charges. The monthly Visual Studio credit balance was not checked. Azure Machine Learning GPU quotas, Azure AI Search service quotas and non-model Document Intelligence/Speech product limits are outside this Cognitive Services model audit.

## Evidence

- [snapshot.json](snapshot.json): regional quotas with model/SKU matches.
- [eastus2-cli-scopes.json](eastus2-cli-scopes.json): later scope-aware response and released test allocations.
- [catalog-matched-positive.json](catalog-matched-positive.json): convenience index of positive catalog matches; original regional snapshot remains authoritative.
- [audit.py](audit.py): read-only reproduction script; obtains an ARM token in memory and never writes credentials.
