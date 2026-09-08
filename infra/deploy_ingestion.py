"""Deploy the permanent data worker to the existing subscription and App Service plan."""

import argparse
import hashlib
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from infra.app_settings import configure_app
from infra.provision import GROUP, LOCAL, SERVER, az, private_write

APP = "agroamigo-data-9a04"
STORAGE = "agroamigodata9a04"


def database():
    import certifi
    import psycopg
    from psycopg import sql

    c = json.loads((LOCAL / "database.json").read_text())
    credentials = LOCAL / "ingestion-database.json"
    worker = (
        json.loads(credentials.read_text())
        if credentials.exists()
        else {"password": secrets.token_urlsafe(36) + "Aa1!"}
    )
    with psycopg.connect(
        host=c["host"],
        dbname=c["database"],
        user=c["user"],
        password=c["password"],
        sslmode="verify-full",
        sslrootcert=certifi.where(),
        connect_timeout=20,
    ) as db:
        db.execute("SET LOCAL lock_timeout='3s'")
        db.execute((ROOT / "pipelines/market/schema.sql").read_text())
        db.execute((ROOT / "pipelines/ingestion/schema.sql").read_text())
        if not db.execute(
            "SELECT 1 FROM pg_roles WHERE rolname='agro_ingestor'"
        ).fetchone():
            db.execute(
                sql.SQL("CREATE ROLE agro_ingestor LOGIN PASSWORD {}").format(
                    sql.Literal(worker["password"])
                )
            )
        db.execute(
            "GRANT CONNECT ON DATABASE agroamigo TO agro_ingestor; GRANT USAGE ON SCHEMA public TO agro_ingestor; GRANT TEMP ON DATABASE agroamigo TO agro_ingestor"
        )
        db.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO agro_ingestor")
        db.execute(
            "GRANT INSERT ON official_source_review,official_price_quote,historical_price,retained_record,source_document TO agro_ingestor"
        )
        db.execute(
            "GRANT INSERT,UPDATE ON ingestion_run,ingestion_asset,document_alias,product,market,price_observation,coffee_reference,coffee_factor,exchange_rate,daily_price,input_price,input_municipal_price,source_pdf_page,regional_price,source_archive_member,input_reference_row,seasonal_year,supply_observation TO agro_ingestor"
        )
        db.execute(
            "GRANT INSERT,UPDATE ON source_ocr_task TO agro_ingestor; GRANT INSERT ON regional_classification,source_ocr_scan,source_ocr_result,source_ocr_attempt TO agro_ingestor; GRANT USAGE ON SEQUENCE source_ocr_attempt_id_seq TO agro_ingestor"
        )
    worker["url"] = (
        f"postgresql://agro_ingestor:{quote(worker['password'], safe='')}@{c['host']}:5432/{c['database']}"
    )
    private_write(credentials, json.dumps(worker))
    print(
        "Permanent retention migration and restricted ingestion role ready.", flush=True
    )
    return worker


def deploy(code_only=False):
    # Build a complete Linux/Python 3.11 package even when deploying from macOS.
    # Remote Oryx builds and run-from-package conflict on Dedicated Linux plans.
    bundle = LOCAL / "ingestion.zip"
    with tempfile.TemporaryDirectory(prefix="ingestion-build-", dir=LOCAL) as stage:
        stage = Path(stage)
        target = stage / ".python_packages/lib/site-packages"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--quiet",
                "--no-compile",
                "--target",
                str(target),
                "--platform",
                "manylinux_2_28_x86_64",
                "--platform",
                "manylinux2014_x86_64",
                "--implementation",
                "cp",
                "--python-version",
                "3.11",
                "--only-binary=:all:",
                "-r",
                str(ROOT / "pipelines/ingestion/requirements.txt"),
            ],
            check=True,
        )
        with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in target.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(stage))
            for name in ["function_app.py", "host.json", "requirements.txt"]:
                archive.write(ROOT / "pipelines/ingestion" / name, name)
            for name in [
                "pipelines/ingestion/workbook_preview.py",
                "pipelines/ingestion/queue_plan.py",
                "pipelines/ingestion/official_sources.py",
                "pipelines/ingestion/international_sources.py",
                "pipelines/ingestion/colombia_sources.py",
                "pipelines/ingestion/ocr.py",
                "pipelines/ingestion/special_prices.py",
                "pipelines/ingestion/input_references.py",
                "pipelines/ingestion/city_reports.py",
                "pipelines/ingestion/worker.py",
                "pipelines/ingestion/inputs.py",
                "pipelines/ingestion/pdf_sources.py",
                "pipelines/ingestion/supply.py",
                "pipelines/demo/import_data.py",
            ]:
                archive.write(ROOT / name, name)
        from pipelines.ingestion.worker import RELEASE_FILES, release_fingerprint

        with zipfile.ZipFile(bundle) as packaged:
            release = hashlib.sha256(
                b"".join(
                    packaged.read(
                        name if name in packaged.namelist() else Path(name).name
                    )
                    for name in RELEASE_FILES
                )
            ).hexdigest()
        if release_fingerprint() != release:
            raise RuntimeError(
                "Worker sources changed during packaging; rebuild before deploying"
            )
    print("Complete Linux dependency package built.", flush=True)
    if code_only:
        worker = json.loads((LOCAL / "ingestion-database.json").read_text())
        if not worker.get("url"):
            raise RuntimeError(
                "Restricted worker configuration missing; run database setup first"
            )
        print(
            "Reusing current database schema and restricted worker configuration.",
            flush=True,
        )
    else:
        worker = database()
    key = az("storage", "account", "keys", "list", "-g", GROUP, "-n", STORAGE)[0][
        "value"
    ]
    storage = f"DefaultEndpointsProtocol=https;AccountName={STORAGE};AccountKey={key};EndpointSuffix=core.windows.net"
    from azure.core.exceptions import ResourceExistsError
    from azure.storage.blob import BlobServiceClient

    client = BlobServiceClient.from_connection_string(storage)
    try:
        client.create_container("source-archive")
    except ResourceExistsError:
        pass
    app = az("functionapp", "show", "-g", GROUP, "-n", APP)
    existing = {
        r["startIpAddress"]
        for r in az(
            "postgres",
            "flexible-server",
            "firewall-rule",
            "list",
            "-g",
            GROUP,
            "-s",
            SERVER,
        )
    }
    for ip in app["outboundIpAddresses"].split(","):
        if ip not in existing:
            az(
                "postgres",
                "flexible-server",
                "firewall-rule",
                "create",
                "-g",
                GROUP,
                "-s",
                SERVER,
                "-n",
                "ingestion-" + ip.replace(".", "-"),
                "--start-ip-address",
                ip,
                "--end-ip-address",
                ip,
            )
    defaults = {
        "DATABASE_URL": worker["url"],
        "AzureWebJobsStorage": storage,
        "DAILY_SCHEDULE": "0 0 23 * * *",
        "BACKFILL_SCHEDULE": "0 15 * * * *",
        "GEMINI_OCR_MODEL": "gemini-3.5-flash",
        "GEMINI_OCR_DAILY_REQUESTS": "40",
    }
    runtime = {
        "FUNCTIONS_WORKER_RUNTIME": "python",
        "FUNCTIONS_EXTENSION_VERSION": "~4",
        "FUNCTIONS_WORKER_PROCESS_COUNT": "1",
        "PYTHON_THREADPOOL_THREAD_COUNT": "2",
        "SCM_DO_BUILD_DURING_DEPLOYMENT": "false",
        "ENABLE_ORYX_BUILD": "false",
        "WEBSITE_RUN_FROM_PACKAGE": "1",
        "AzureWebJobsFeatureFlags": "EnableWorkerIndexing",
    }
    gemini_key = os.environ.get("GEMINI_API_KEY") or (
        (ROOT / "gemini-api-key").read_text().strip()
        if (ROOT / "gemini-api-key").exists()
        else None
    )
    if gemini_key:
        defaults["GEMINI_API_KEY"] = gemini_key
    configure_app("functionapp", APP, defaults, runtime)
    az(
        "functionapp",
        "config",
        "set",
        "-g",
        GROUP,
        "-n",
        APP,
        "--always-on",
        "true",
        "--min-tls-version",
        "1.2",
        "--ftps-state",
        "Disabled",
    )
    print("Deploying complete Python function package.", flush=True)
    if release_fingerprint() != release:
        raise RuntimeError(
            "Worker sources changed after packaging; rebuild before deploying"
        )
    az(
        "functionapp",
        "deployment",
        "source",
        "config-zip",
        "-g",
        GROUP,
        "-n",
        APP,
        "--src",
        str(bundle),
        "--build-remote",
        "false",
        "--timeout",
        "1800",
    )
    import requests

    key = az("functionapp", "keys", "list", "-g", GROUP, "-n", APP)["masterKey"]
    for attempt in range(36):
        try:
            response = requests.get(
                f"https://{APP}.azurewebsites.net/api/status",
                headers={"x-functions-key": key},
                timeout=20,
            )
            if response.ok and response.json().get("release") == release:
                print(
                    "Deployed worker release verified; status and database are healthy.",
                    flush=True,
                )
                return
        except (requests.RequestException, ValueError):
            pass
        if attempt % 6 == 0:
            print("Waiting for Azure to load the deployed package.", flush=True)
        time.sleep(5)
    raise RuntimeError(
        "Azure did not report the deployed worker release; inspect host logs before accepting deployment"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-only", action="store_true")
    parser.add_argument(
        "--code-only",
        action="store_true",
        help="Deploy runtime code using the already configured schema and restricted role",
    )
    args = parser.parse_args()
    if args.database_only and args.code_only:
        parser.error("Choose either --database-only or --code-only")
    database() if args.database_only else deploy(code_only=args.code_only)
