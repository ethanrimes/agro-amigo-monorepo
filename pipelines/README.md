# Data pipelines

The pipelines preserve source originals and produce the application data consumed by the shared web and mobile interface. Recurring price ingestion and dated planning imports are separate paths.

| Directory | Purpose |
|---|---|
| [ingestion](ingestion/README.md) | Official source discovery, versioned extraction, publication, retries and historical backfill |
| [demo](demo) | Base schema and initial application imports |
| [planning](planning) | Municipal crop references, calendars, cost publications and related source metadata |
| [market](market) | Market/supply schema and initial imports |
| [spatial](spatial) | Allowed geographical layers, schemas and reference imports |
| [assets](assets/README.md) | Local image assets and attribution |
| [news](news/README.md) | Separate local Spanish-language news collector; no connected public feed |

## Data contracts

Original files are identified by content hash. Observations retain source document and cell/page/row locators, date, unit and original identity. Publisher revisions and parser corrections do not delete older raw evidence. Public projections choose eligible data and keep reviewed records separate.

Prices, supply volumes, statistical crop references and territorial information have different meanings. Supply arrivals do not represent inventory; municipal yield does not predict a parcel; older nominal cost studies do not become current farm costs.

[planning/reference-downloads.json](planning/reference-downloads.json) describes static reference files. Recurring source selection belongs to the ingestion worker. Forecast and spatial APIs archive request-driven responses separately. Adopting a new source layout requires preserving its own periods, units and provenance.

## Python environment

From the repository root:

```sh
python3 -m venv .venv
.venv/bin/pip install -r pipelines/requirements.txt
```

Individual subsystems may have additional requirements. Database-connected importers require a configured restricted connection; local credentials and downloaded caches stay outside Git. Consult the relevant module before running an importer because import commands publish data.

See [data sources](../docs/DATA_SOURCES.md) and [code navigation](../docs/CODE_NAVIGATION.md).
