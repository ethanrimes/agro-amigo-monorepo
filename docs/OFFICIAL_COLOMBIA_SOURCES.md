# Official Colombian price references

These sources supplement DANE and FNC in the unified product catalog. Each quotation keeps its publisher, market, period, currency, physical unit and price basis.

| Publisher | Information | Basis |
|---|---|---|
| [UPRA / AgroNET](https://agronet.gov.co/noticias/precio-de-referencia-semanal-de-compra-de-cacao-fuente-industria-nacional-exportadores) | Cacao buying reference | Weekly industry/exporter reference with explicit effective dates |
| [MADR / Fedepalma FFP](https://fedepalma.org/fondo-de-fomento-palmero-ffp/) | Palm oil and palm kernel reference | Statutory contribution basis, not a spot purchase offer |
| [Fedegán / FNG](https://estadisticas.fedegan.org.co/Indicadores/13) | Cattle and producer-milk indicators | Sex, geography, liveweight, invoice/auction method and bonus distinctions |
| [Porkcolombia / FNP](https://porkcolombia.co/ronda_de_precios/) | Pig and carcass quotations | Published national/regional means and distinct price segments; liveweight and carcass bases stay separate |
| [Corabastos](https://corabastos.com.co/boletin-precios-corabastos/) | Daily food quotations | Literal product, quality, presentation, quantity and package unit |

## Implementation

[colombia_sources.py](../pipelines/ingestion/colombia_sources.py) discovers original files and parses source-specific rows. [official_sources.py](../pipelines/ingestion/official_sources.py) validates identities and writes versioned quotations or reviews. [official_catalog.py](../pipelines/ingestion/official_catalog.py) maintains the eligible current catalog and previous-date values.

HTML/JSON indexes lead to original HTML, CSV and PDF sources. CSV downloads are identified by content, not merely URL extension. Mutable URLs are rechecked, and changed bytes receive a new immutable document ID.

Quote identity includes the source series, product, market, currency, unit, basis and additional dimensions such as quality or price segment. A package price is not divided by an assumed package weight. Method changes remain distinct series. Explicit tercile means do not replace the overall mean or become its min/max range.

Native extraction runs first. Supported Pork PDF failures can use page-specific paired OCR through the adapter; that contract does not imply OCR support for every Colombian publisher. Uncertain dates, missing unit declarations, zero prices and contradictory ranges remain source reviews rather than guessed quotations.

## Application behavior

Official references appear in `/products` and `/references/[id]`, with source-specific history and original evidence. Department filters apply only to verified geographical matches. International or national references without a supported regional match are excluded from a regional selection, with an explanation.

Source files and old parser results remain retained when a corrected revision changes the published view. These references do not establish live buyer availability, transaction guarantees or equivalent prices across unlike bases.
