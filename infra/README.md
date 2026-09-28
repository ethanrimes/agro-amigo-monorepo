# Azure infrastructure

The application uses Azure App Service for the Next.js server, Azure Functions for recurring ingestion, PostgreSQL for source and application data, and private Blob Storage for original documents.

## Implementation map

| File | Responsibility |
|---|---|
| [provision.py](provision.py) | Resource and database setup |
| [deploy.py](deploy.py) | Shared web packaging and deployment |
| [deploy_ingestion.py](deploy_ingestion.py) | Worker packaging and deployment |
| [app_settings.py](app_settings.py) | Application configuration and preservation of remote operator settings |

The scripts contain deployment-specific configuration. They require an authenticated Azure CLI context and appropriate permissions; local application development does not require running them.

## Boundaries

The web app uses a restricted database role and certificate-validated connections. Ingestion has a separate writer role. Source history is retained, and Blob originals are private; the application serves permitted source downloads through its own endpoint.

The web package contains the standalone Next.js server, static assets and local PDF/map resources. Environment files and credentials are excluded. Runtime settings provide database and storage configuration. `/api/health` reports database connectivity.

Worker timers, budgets and OCR limits are configuration rather than public client inputs. Checkpoints and a shared advisory lock support bounded processing and safe resume. Deploying parser code does not itself mean every historical original has been reprocessed.

## Local prerequisites

The web application needs Node.js/npm and a configured PostgreSQL connection. Python tooling uses the repository's requirements files. Azure deployment additionally requires Azure CLI access and an existing configuration for the intended environment. Keep local credentials in ignored environment/configuration files.

See [the root README](../README.md), [pipeline architecture](../pipelines/README.md) and [recurring ingestion](../pipelines/ingestion/README.md).
