"""Read-only checks of the deployed app against retained Azure observations."""

import hashlib
import json
import os
from pathlib import Path

import requests

from pipelines.ingestion.worker import connect, today


def verify():
    origin = os.environ.get(
        "AGRO_APP_ORIGIN", "https://agroamigo-demo-9a04.azurewebsites.net"
    )
    session = requests.Session()

    def get(path):
        response = session.get(origin + path, timeout=60)
        response.raise_for_status()
        return response.json()

    get("/api/health")
    catalog = get("/api/catalog")
    assert len(catalog["products"]) > 100
    for product in catalog["products"]:
        assert product["price"] > 0
        assert product["unit"] in ("kg", "125kg", "unit", "litre")
    detail = get("/api/products/aguacate-hass")
    assert detail["markets"] and all(
        m["source_url"].startswith("https://www.dane.gov.co/")
        for m in detail["markets"]
    )
    coffee = get("/api/coffee")
    assert (
        len(coffee["history"]) > 250
        and len(coffee["markets"]) == 16
        and len(coffee["factors"]) == 13
    )
    assert coffee["exchange"]["price"] > 0
    with connect() as db:
        cutoff = (
            db.execute("SELECT (%s::date-interval '1 year')::date", (today(),))
            .fetchone()[0]
            .isoformat()
        )
        for row in coffee["history"] + detail["history"]:
            assert cutoff < row["date"] <= today().isoformat()
        daily = get("/api/planning/daily")
        latest = db.execute("SELECT max(observed_on) FROM daily_price").fetchone()[0]
        expected = db.execute(
            "SELECT count(*) FROM daily_price WHERE observed_on=%s", (latest,)
        ).fetchone()[0]
        assert len(daily) == expected > 100 and all(
            r["observed_on"] == latest.isoformat() for r in daily
        )
        alias = "daily-2012-06-12-workbook"
        source = get("/api/evidence/" + alias)
        expected_hash = db.execute(
            "SELECT document_id FROM document_alias WHERE alias=%s", (alias,)
        ).fetchone()[0]
        response = session.get(
            origin + "/api/evidence/" + alias + "/content", timeout=60
        )
        response.raise_for_status()
        assert hashlib.sha256(response.content).hexdigest() == expected_hash
        assert (
            response.headers["Content-Type"].split(";")[0] == "application/vnd.ms-excel"
        )
    assert (
        session.get(origin + "/api/products/does-not-exist", timeout=60).status_code
        == 404
    )
    report = {
        "origin": origin,
        "status": "passed",
        "catalog_products": len(catalog["products"]),
        "coffee_history_days": len(coffee["history"]),
        "latest_daily_date": str(latest),
        "latest_daily_rows": len(daily),
        "recent_view_boundary": cutoff,
        "historical_xls_sha256": expected_hash,
        "historical_xls_bytes": len(response.content),
    }
    Path("artifacts/app-data-validation.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    verify()
