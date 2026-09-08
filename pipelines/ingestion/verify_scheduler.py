"""Exercise real PostgreSQL scheduling SQL using only a temporary queue table."""

from . import queue_plan, worker


def main():
    with worker.connect() as db, db.transaction():
        db.execute(
            "CREATE TEMP TABLE ingestion_asset (LIKE public.ingestion_asset INCLUDING DEFAULTS) ON COMMIT DROP"
        )
        for number in range(200):
            db.execute(
                "INSERT INTO ingestion_asset(url,kind) VALUES(%s,'colombia-pork-index')",
                (f"https://example.invalid/index/{number}",),
            )
        cases = [
            ("leaf", "colombia-pork-pdf", "pending", "", "NULL"),
            (
                "international-leaf",
                "international-usda-boston-flowers",
                "pending",
                "",
                "NULL",
            ),
            ("upgrade", "milk", "complete", "old-parser", "now()"),
            (
                "stale-review",
                "milk-pdf",
                "review",
                worker.parser_version("milk-pdf"),
                "now()-interval '31 days'",
            ),
            (
                "recent-review",
                "milk-pdf",
                "review",
                worker.parser_version("milk-pdf"),
                "now()",
            ),
            ("recent-failure", "milk-pdf", "failed", "old-parser", "now()"),
        ]
        for name, kind, status, version, checked in cases:
            db.execute(
                f"INSERT INTO ingestion_asset(url,kind,status,processor_version,checked_at) VALUES(%s,%s,%s,%s,{checked})",
                ("https://example.invalid/" + name, kind, status, version),
            )
        selected = {
            url.rsplit("/", 1)[-1]
            for url, _, _ in queue_plan.backfill_candidates(db, 8)
        }
        assert {"leaf", "international-leaf", "upgrade", "stale-review"} <= selected, (
            selected
        )
        assert not {"recent-review", "recent-failure"} & selected, selected
        daily = {url for url, _, _ in queue_plan.daily_candidates(db, worker.today())}
        assert "https://example.invalid/leaf" in daily
        assert "https://example.invalid/international-leaf" in daily
        print(
            "Temporary PostgreSQL queue: index/leaf fairness, NULL-date discovery, parser upgrades, stale review and retry cooldown passed."
        )


if __name__ == "__main__":
    main()
