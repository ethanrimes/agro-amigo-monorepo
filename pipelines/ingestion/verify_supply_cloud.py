"""Execute the retained 2020 supply asset in Azure and verify published totals.

The long source can exceed the HTTP response window. Poll the persistent run
record rather than misreporting an HTTP timeout as completed ingestion.
"""

import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from azure.storage.blob import BlobServiceClient

from . import worker
from .verify_deployment import BASE, az_value

URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/series-historicas/microdato-abastecimiento-2020.xlsx"
DID = "bb28aa715c6642ed2ec30c251c5cd7f022bb2e2ae34126f6c0424705f64372b8"


def main():
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
    response = requests.get(BASE + "/api/status", headers=headers, timeout=(10, 20))
    response.raise_for_status()
    initial = response.json()
    assert initial["release"] == worker.release_fingerprint()
    previous_run = initial["runs"][0][0]
    report = {"release": initial["release"], "source_url": URL, "document_id": DID}
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=1) as pool:
        request = pool.submit(
            requests.post,
            BASE + "/api/run-check",
            headers=headers,
            params={"asset_url": URL},
            timeout=(10, 235),
        )
        while time.monotonic() - started < 900:
            time.sleep(15)
            try:
                status = requests.get(BASE + "/api/status", headers=headers, timeout=(10, 20))
                status.raise_for_status()
            except requests.RequestException as exc:
                print(json.dumps({"elapsed_seconds": round(time.monotonic() - started, 1), "health_poll": type(exc).__name__}), flush=True)
                continue
            value = status.json()
            assert value["release"] == report["release"]
            current = value["runs"][0]
            if request.done() and "http_status" not in report:
                try:
                    result = request.result()
                    report["http_status"] = result.status_code
                    if result.ok:
                        body = result.json()
                        report["response"] = body
                        assert body.get("status") != "skipped_overlap", (
                            "Another run holds the advisory lock"
                        )
                except requests.RequestException as exc:
                    report["http_status"] = type(exc).__name__
            print(
                json.dumps(
                    {
                        "elapsed_seconds": round(time.monotonic() - started, 1),
                        "run_id": current[0],
                        "status": current[4],
                    }
                ),
                flush=True,
            )
            if current[0] != previous_run and current[4] != "running":
                report["run"] = current
                assert current[4] == "succeeded", current[4]
                assert (
                    current[5]["assets"] == 1
                    and current[5]["rows"] == 33981
                    and not current[5]["errors"]
                )
                break
        else:
            raise RuntimeError("Cloud source still has no completed persistent run")
    with worker.connect() as db:
        db.execute("SET default_transaction_read_only=on")
        db.execute("SET statement_timeout='15s'")
        report["asset"] = db.execute(
            "SELECT status,records,processor_version,document_id,error FROM ingestion_asset WHERE url=%s",
            (URL,),
        ).fetchone()
        assert report["asset"] == ("complete", 33981, "supply-v3", DID, None)
        report["published"] = db.execute(
            "SELECT count(*),count(DISTINCT market_id),count(DISTINCT food_id),count(DISTINCT period_start),min(first_reported_on),max(observed_on),sum(quantity_kg) FROM supply_observation WHERE document_id=%s",
            (DID,),
        ).fetchone()
        assert report["published"][:4] == (33981, 29, 177, 12)
        assert abs(float(report["published"][-1]) - 6308398393.95) < 0.01
        report["source_bytes"] = db.execute(
            "SELECT octet_length(content) FROM source_document WHERE id=%s", (DID,)
        ).fetchone()[0]
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
    blob = BlobServiceClient(
        "https://agroamigodata9a04.blob.core.windows.net", credential=storage_key
    ).get_blob_client("source-archive", DID + ".xlsx")
    digest, size = hashlib.sha256(), 0
    for chunk in blob.download_blob().chunks():
        digest.update(chunk)
        size += len(chunk)
    assert digest.hexdigest() == DID and size == report["source_bytes"]
    report["original_blob_download_verified"] = True
    report["validation_seconds"] = round(time.monotonic() - started, 1)
    Path("artifacts/supply-2020-cloud-verification.json").write_text(
        json.dumps(report, default=str, indent=2) + "\n"
    )
    print(json.dumps(report, default=str), flush=True)


if __name__ == "__main__":
    main()
