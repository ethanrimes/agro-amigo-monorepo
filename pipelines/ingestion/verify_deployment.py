"""Verify the deployed worker, read-only Excel endpoint and a bounded real run.

Credentials stay in memory and HTTP headers. This intentionally imports real
queued official files through the authenticated cloud worker; no fixtures are
published and no history is deleted.
"""

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path

import requests
from azure.storage.blob import BlobServiceClient

from . import worker

BASE = "https://agroamigo-data-9a04.azurewebsites.net"


def az_value(*args):
    return subprocess.run(
        ["az", *args, "-o", "tsv"], capture_output=True, text=True, check=True
    ).stdout.strip()


def main(report_path="artifacts/ingestion-deployment-verification.json"):
    key = az_value(
        "functionapp",
        "keys",
        "list",
        "-g",
        "agroamigo-demo-rg",
        "-n",
        "agroamigo-data-9a04",
        "--query",
        "masterKey",
    )
    headers = {"x-functions-key": key}
    started = time.monotonic()
    health = requests.get(BASE + "/api/status", headers=headers, timeout=(10, 20))
    health.raise_for_status()
    report = {
        "release": health.json()["release"],
        "health_seconds": round(time.monotonic() - started, 3),
        "workbooks": [],
    }
    assert report["release"] == worker.release_fingerprint(), (
        "Unexpected deployed worker release"
    )
    with worker.connect() as db:
        db.execute("SET default_transaction_read_only=on")
        before = db.execute("SELECT now()").fetchone()[0]
        for publisher in ("DANE", "World Bank"):
            row = db.execute(
                "SELECT id,title FROM source_document WHERE publisher=%s AND media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' ORDER BY octet_length(content) LIMIT 1",
                (publisher,),
            ).fetchone()
            assert row, publisher
            began = time.monotonic()
            response = requests.get(
                BASE + "/api/workbook/" + row[0], params={"limit": 10}, timeout=(10, 90)
            )
            response.raise_for_status()
            data = response.json()
            assert data["readOnly"] and data["sheets"] and len(data["rows"]) <= 10
            report["workbooks"].append(
                {
                    "publisher": publisher,
                    "id": row[0],
                    "status": response.status_code,
                    "seconds": round(time.monotonic() - began, 3),
                    "sheet": data["sheet"],
                    "rows": len(data["rows"]),
                }
            )
    print(json.dumps(report), flush=True)
    result = requests.post(BASE + "/api/run-check", headers=headers, timeout=(10, 210))
    result.raise_for_status()
    report["cloud_run"] = result.json()
    if report["cloud_run"].get("status") == "skipped_overlap":
        raise RuntimeError(
            "Another real ingestion holds the advisory lock; retry the bounded validation afterward"
        )
    assert report["cloud_run"]["assets"] > 0, "No queued real asset processed"
    health = requests.get(BASE + "/api/status", headers=headers, timeout=(10, 20))
    health.raise_for_status()
    assert health.json()["release"] == report["release"]
    report["latest_runs"] = health.json()["runs"][:2]
    with worker.connect() as db:
        db.execute("SET default_transaction_read_only=on")
        rows = db.execute(
            "SELECT id,media_type,metadata->>'ingestion_kind',content FROM source_document WHERE retrieved_at>=%s AND metadata->>'retention'='permanent'",
            (before,),
        ).fetchall()
    storage_key = az_value(
        "storage",
        "account",
        "keys",
        "list",
        "-g",
        "agroamigo-demo-rg",
        "-n",
        "agroamigodata9a04",
        "--query",
        "[0].value",
    )
    container = BlobServiceClient(
        "https://agroamigodata9a04.blob.core.windows.net", credential=storage_key
    ).get_container_client("source-archive")
    report["new_archives"] = []
    extensions = {
        "application/pdf": "pdf",
        "application/zip": "zip",
        "text/html": "html",
        "text/csv": "csv",
        "application/json": "json",
        "application/vnd.ms-excel": "xls",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
        "image/png": "png",
    }
    for did, media, kind, content in rows:
        assert hashlib.sha256(content).hexdigest() == did
        downloaded = container.download_blob(did + "." + extensions[media]).readall()
        size = len(downloaded)
        assert hashlib.sha256(downloaded).hexdigest() == did
        assert size == len(content)
        report["new_archives"].append(
            {"id": did, "kind": kind, "bytes": size, "blob_verified": True}
        )
    target = Path(report_path)
    target.write_text(json.dumps(report, default=str, indent=2) + "\n")
    print(json.dumps(report, default=str), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="artifacts/ingestion-deployment-verification.json")
    main(parser.parse_args().output)
