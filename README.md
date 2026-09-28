# AgroAmigo

AgroAmigo is a Spanish-language application for Colombian farmers and purchasers. It brings together agricultural prices, market arrivals, input comparisons, local weather and territorial references, with links to the original sources.

The web interface is shared by Android and iOS clients. The five main sections are **Inicio, Productos, Mercados, Insumos and Mi finca**.

- **Products and markets:** dated prices, original units, filters, retained history and comparable market quotations.
- **Inputs:** commercial identities, presentations and department or municipality prices.
- **Supply:** reported arrivals by food, destination market and month, with reporting coverage.
- **Mi finca:** a saved location, weather, territorial layers and read-only crop, calendar, cost-study and price-history references.
- **Coffee and offers:** FNC reference conversions and private offer comparisons, kept separate from official market data.
- **Sources:** PDF, spreadsheet and structured-data viewers with original downloads and provenance.

Demo: [web application](https://agroamigo-demo-9a04.azurewebsites.net) · [Android installation](https://agroamigo-demo-9a04.azurewebsites.net/android).

## Repository

| Directory | Purpose |
|---|---|
| [apps/web](apps/web) | Next.js interface, APIs and server-side queries |
| [apps/android](apps/android/README.md) | Android WebView client |
| [apps/ios](apps/ios/README.md) | Flutter client using WKWebView |
| [pipelines](pipelines/README.md) | Source discovery, importers and recurring ingestion |
| [infra](infra/README.md) | Azure provisioning and deployment implementation |

See [architecture](docs/ARCHITECTURE.md), [code navigation](docs/CODE_NAVIGATION.md), [data sources](docs/DATA_SOURCES.md) and [Mi finca](docs/MI_FINCA_DATA.md).

## Local web setup

Install Node.js with npm. From the repository root:

```sh
npm ci
npm run dev
```

Database-backed pages require a server-side `DATABASE_URL`, normally provided through the ignored `apps/web/.env.local`. Use an appropriately restricted PostgreSQL account. Certificate validation is enabled by default. Credentials are not sent to the browser.

`npm run build` creates the production web build. Mobile setup is described in each client's README. The app requires network access for source data; locally saved farms, favorites and offers do not provide an offline copy of official prices.
