# International agricultural price references

International references appear in the unified catalog with their original currency, physical unit, market and basis. They are not merged into Colombian wholesale or farmgate averages.

| Publisher | Information | Interpretation |
|---|---|---|
| [World Bank Commodity Markets](https://www.worldbank.org/en/research/commodity-markets) | Monthly agricultural, food, feed, fiber and fertilizer benchmarks | Original USD units and published periods; benchmark values are not local purchase offers |
| [USDA AMS Miami ornamental report](https://esmis.nal.usda.gov/publication/import-ornamental-shipping-point-report-miami-fl) | Imported ornamental shipping-point quotations | Origin, grade, variety and literal package/stem unit |
| [USDA AMS Boston ornamental report](https://esmis.nal.usda.gov/publication/ornamental-wholesale-market-report-boston-ma) | Ornamental wholesale market quotations | Boston market basis, reported range and exact product variants |

## Implementation

[international_sources.py](../pipelines/ingestion/international_sources.py) owns discovery and native XLSX/PDF/TXT extraction. [official_sources.py](../pipelines/ingestion/official_sources.py) publishes immutable quote revisions and explicit reviews. The current catalog is maintained by [official_catalog.py](../pipelines/ingestion/official_catalog.py).

World Bank workbook rows retain the published period, unit and cell locator. Displayed tonne-to-kg equivalents are derived conversions, not new source prices. Missing values are not zero and are not interpolated.

USDA reports retain report date, commodity/variety, quality, origin, market, package and range. Where the application uses a range midpoint, it identifies that value as calculated; it does not call it a published mean. Narrative dates or numbers cannot silently become price rows. Unsupported or ambiguous native layouts remain reviewable; retaining an OCR image does not create a typed publication path for these adapters.

## Application behavior

`/products` includes distinct reference identities. `/references/[id]` provides their prices, history and original evidence. Saved references use stable keys independent of canonical Colombian product IDs.

Global or unverified locations do not acquire a Colombian department from a text guess. A currency conversion does not establish a Colombian selling price, farmgate flower value or product equivalence. Sources, nominal values and original units remain available alongside any supported display conversion.
