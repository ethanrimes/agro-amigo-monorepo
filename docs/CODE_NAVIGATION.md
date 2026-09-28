# Code navigation

Use this map to find the implementation of a feature. [Architecture](ARCHITECTURE.md) explains how the components fit together.

## Applications and infrastructure

| Area | Entry points | Responsibility |
|---|---|---|
| Shared interface | [app](../apps/web/src/app), [components](../apps/web/src/components) | Next.js routes and React screens |
| Server boundary | [db.ts](../apps/web/src/lib/server/db.ts), [server queries](../apps/web/src/lib/server) | PostgreSQL connections and validated data access |
| Android | [MainActivity.java](../apps/android/app/src/main/java/co/agroamigo/demo/MainActivity.java) | Trusted-origin WebView, back, permissions and downloads |
| iOS | [main.dart](../apps/ios/lib/main.dart) | WKWebView, safe areas, navigation, permissions and sharing |
| Deployment | [infra](../infra/README.md) | Azure resources, packaging and configuration |

## Price and reference ingestion

| Module | Responsibility |
|---|---|
| [function_app.py](../pipelines/ingestion/function_app.py) | Timer and authenticated worker entry points |
| [worker.py](../pipelines/ingestion/worker.py), [queue_plan.py](../pipelines/ingestion/queue_plan.py) | Discovery, version dispatch, bounded scheduling and canonical price projections |
| [inputs.py](../pipelines/ingestion/inputs.py), [resumable_inputs.py](../pipelines/ingestion/resumable_inputs.py), [input_references.py](../pipelines/ingestion/input_references.py) | Input identities, resumable publication and ancillary annex data |
| [pdf_sources.py](../pipelines/ingestion/pdf_sources.py) | Native PDF text/tables, monetary guards and input PDF parsing |
| [city_reports.py](../pipelines/ingestion/city_reports.py) | ZIP members, city packages, rounds, classification and member checkpoints |
| [dane_weekly.py](../pipelines/ingestion/dane_weekly.py) | Weekly PDF/XLS/XLSX periods, means, ranges and review rows |
| [special_prices.py](../pipelines/ingestion/special_prices.py) | Municipal milk and mill rice observations |
| [milk_macroregions.py](../pipelines/ingestion/milk_macroregions.py), [milk_publication.py](../pipelines/ingestion/milk_publication.py) | Separate milk chart identities and municipal/chart publication coordination |
| [supply.py](../pipelines/ingestion/supply.py) | Bounded supply aggregation with exact original row ranges |
| [coffee_sources.py](../pipelines/ingestion/coffee_sources.py), [colombia_sources.py](../pipelines/ingestion/colombia_sources.py), [international_sources.py](../pipelines/ingestion/international_sources.py) | Publisher-specific price semantics |
| [official_sources.py](../pipelines/ingestion/official_sources.py), [official_catalog.py](../pipelines/ingestion/official_catalog.py) | Official quote publication, reviews and current catalog refresh |
| [ocr.py](../pipelines/ingestion/ocr.py) | Retained images, paired readings and supported typed fallback dispatch |
| [source_link_recovery.py](../pipelines/ingestion/source_link_recovery.py), [query_publication.py](../pipelines/ingestion/query_publication.py) | Evidence-preserving alternative sources and historical-query responses |
| [schema.sql](../pipelines/ingestion/schema.sql), [migrations](../pipelines/ingestion/migrations) | Durable data structures and publication views |

Parser versions affect retry eligibility as well as extraction. Inspect `worker.parser_version(kind)` and the relevant completion checkpoints when changing an adapter. Source-specific unsupported layouts must remain explicit.

## APIs and screens

| Feature | Server implementation | UI implementation |
|---|---|---|
| Unified products | [catalog.ts](../apps/web/src/lib/server/catalog.ts), [catalog-types.ts](../apps/web/src/lib/catalog-types.ts) | [CatalogView.tsx](../apps/web/src/components/marketplace/CatalogView.tsx) |
| Product filters/history | [price-quotes.ts](../apps/web/src/lib/server/price-quotes.ts) | [product detail route](../apps/web/src/app/product) |
| Official references | [official-references.ts](../apps/web/src/lib/server/official-references.ts), [summary-references.ts](../apps/web/src/lib/server/summary-references.ts) | [reference route](../apps/web/src/app/references) |
| Markets, inputs and supply | [explore.ts](../apps/web/src/lib/server/explore.ts), [planning.ts](../apps/web/src/lib/server/planning.ts) | [explore components](../apps/web/src/components/explore) |
| Comparisons | [comparisons.ts](../apps/web/src/lib/server/comparisons.ts), [comparison-math.ts](../apps/web/src/lib/comparison-math.ts) | [comparison components](../apps/web/src/components/comparison) |
| Source display/download | [evidence API](../apps/web/src/app/api/evidence), [source-storage.ts](../apps/web/src/lib/server/source-storage.ts) | [EvidenceContent.tsx](../apps/web/src/components/planning/EvidenceContent.tsx) |
| Workbook preview | [workbook_preview.py](../pipelines/ingestion/workbook_preview.py) | Read-only worksheet pagination in the source viewer |
| Mi finca | [location.ts](../apps/web/src/lib/server/location.ts), [planning.ts](../apps/web/src/lib/server/planning.ts) | [LocationWorkspace.tsx](../apps/web/src/components/location/LocationWorkspace.tsx) |
| Crop references | [planning.ts](../apps/web/src/lib/server/planning.ts) | [CropOptions.tsx](../apps/web/src/components/planning/CropOptions.tsx), [CropReferences.tsx](../apps/web/src/components/planning/CropReferences.tsx), [plan route](../apps/web/src/app/plan) |
| Private device state | [farm-types.ts](../apps/web/src/lib/farm-types.ts) | [FarmContext.tsx](../apps/web/src/components/planning/FarmContext.tsx) |
| Photos and attribution | [images.ts](../apps/web/src/lib/images.ts), [image-library.json](../apps/web/src/lib/image-library.json) | [credits route](../apps/web/src/app/credits) |

Static planning and geographic imports live under [pipelines/planning](../pipelines/planning) and [pipelines/spatial](../pipelines/spatial). The separate [news collector](../pipelines/news/README.md) has no connected public app feed.
