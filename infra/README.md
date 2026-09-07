# Azure demo

Subscription: `9a04b64b-af19-4519-be50-56ec2acbd855` (tenant `148ba320-1a6d-4fd7-ba8b-2897083e7531`). All new resources are isolated in `agroamigo-demo-rg`, North Central US.

| Resource | Name | Configuration |
|---|---|---|
| PostgreSQL Flexible Server | `agroamigo-demo-pg-9a04` | PostgreSQL 16, Burstable B1ms, 32 GiB, 7-day backups |
| Database | `agroamigo` | Recent observations, historical references and immutable evidence |
| App Service plan | `agroamigo-demo-plan` | Linux B1 |
| Web app | `agroamigo-demo-9a04` | Node 22 LTS, HTTPS only, TLS 1.2+, FTPS disabled |

App URL: https://agroamigo-demo-9a04.azurewebsites.net

These are provisioned Azure services and incur subscription charges while running. No existing project resources were modified. No DNS/custom domain was configured.

## Local development

```sh
npm ci
npx playwright install chromium
python3 -m venv .venv
.venv/bin/pip install -r pipelines/requirements.txt
.venv/bin/python pipelines/demo/import_data.py
npm run dev --workspace agroamigo-web -- -p 3002 -H 127.0.0.1
```

`import_data.py` uses the locally provisioned credentials in `.azure-local/database.json` and creates `apps/web/.env.local` with only the read-only application connection. On another workstation obtain credentials securely and allow its client IP in the PostgreSQL firewall. Never commit credentials or use `NEXT_PUBLIC_` for database access. An environment template is in `apps/web/.env.example`.

## Provision and deploy

`provision.py` is configured for this subscription and isolated resource names. The initial resource-group creation is:

```sh
az group create --subscription 9a04b64b-af19-4519-be50-56ec2acbd855 -n agroamigo-demo-rg -l northcentralus
python3 infra/provision.py db
python3 infra/provision.py web
```

For subsequent deployments:

```sh
npm run build --workspace agroamigo-web
python3 infra/deploy.py
```

Deployment copies the standalone server, Next static files, and local image/font assets. Dotenv files are explicitly excluded from the ZIP. App Service settings supply `DATABASE_URL`; the web app uses `agro_reader`, which can SELECT relevant tables and INSERT public weather snapshots. The database certificate is verified. Its firewall allows the initial developer IP and the app's exact outbound IPs, not all internet or all Azure addresses. If the plan or outbound addresses change, run deployment again to add the current addresses and review obsolete firewall rules.

The application starts with `node apps/web/server.js`. `/api/health` returns HTTP 200 only when PostgreSQL is reachable. Public error responses do not contain connection strings or SQL details.

## Refresh and retention

```sh
.venv/bin/python pipelines/demo/import_data.py
.venv/bin/python pipelines/planning/fetch_references.py
.venv/bin/python pipelines/planning/import_references.py
.venv/bin/python pipelines/planning/import_costs.py
.venv/bin/python pipelines/planning/import_daily.py 2026-09-04
.venv/bin/python pipelines/planning/methodology.py
.venv/bin/python pipelines/demo/verify_database.py
.venv/bin/python pipelines/planning/verify.py
```

`--cached` reuses downloaded source files for reproducibility; omit it to refresh. Raw source workbooks are archived in PostgreSQL and cached locally; only recent observations enter the rolling observation tables. Five complete years support the separate seasonal tables. The last-12-month boundary uses `America/Bogota`, including database insertion guards. Each import prunes expired records. There is no unattended schedule configured; this is an explicitly dated demo snapshot. Public queries always enforce the date window even between refreshes.

Provisioning credentials are held in owner-only local files under `.azure-local/`. That directory also holds ignored build/deployment artifacts. Keep this folder secure. A new administrator can reset the server password using Azure and update local credentials; the application role's credential must be rotated independently.
