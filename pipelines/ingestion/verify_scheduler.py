"""Exercise real PostgreSQL scheduling SQL using only a temporary queue table."""

from . import queue_plan, worker


def main():
    with worker.connect() as db, db.transaction():
        db.execute(
            "CREATE TEMP TABLE ingestion_asset (LIKE public.ingestion_asset INCLUDING ALL) ON COMMIT DROP"
        )
        # Repeated discovery should not create new tuples or even take an
        # UPDATE row lock for unchanged known sources. New dates/kinds still
        # update metadata and preserve the original first-discovery time.
        source = "https://example.invalid/repeated.xlsx"
        worker.queue(db, source, "daily")
        original = db.execute(
            "SELECT ctid,xmin,xmax,discovered_at FROM ingestion_asset WHERE url=%s",
            (source,),
        ).fetchone()
        worker.queue(db, source, "daily")
        assert db.execute(
            "SELECT ctid,xmin,xmax,discovered_at FROM ingestion_asset WHERE url=%s",
            (source,),
        ).fetchone() == original
        worker.queue(db, source, "daily", worker.today())
        worker.queue(db, source, "daily-pdf", worker.today())
        assert db.execute(
            "SELECT kind,observed_on,discovered_at FROM ingestion_asset WHERE url=%s",
            (source,),
        ).fetchone() == ("daily-pdf", worker.today(), original[3])
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
        # New files must not sit behind hundreds of successful old workbooks;
        # mutable current supply must be revisited even when its URL is stable.
        for name, kind, day, checked in [
            (
                "microdato-abastecimiento-2026.xlsx",
                "supply",
                None,
                "now()-interval '1 day'",
            ),
            (
                "microdato-abastecimiento-2013.xlsx",
                "supply",
                None,
                "now()-interval '1 day'",
            ),
            ("fresh-daily", "daily", worker.today(), "NULL"),
            ("recent-daily", "daily", worker.today(), "now()"),
        ]:
            db.execute(
                f"INSERT INTO ingestion_asset(url,kind,status,observed_on,checked_at) VALUES(%s,%s,'complete',%s,{checked})",
                ("https://example.invalid/" + name, kind, day),
            )
        daily = {
            url.rsplit("/", 1)[-1]
            for url, _, _ in queue_plan.daily_candidates(db, worker.today())
        }
        assert "microdato-abastecimiento-2026.xlsx" in daily
        assert "microdato-abastecimiento-2013.xlsx" not in daily
        assert "fresh-daily" in daily and "recent-daily" not in daily
        print(
            "Temporary PostgreSQL queue: index/leaf fairness, NULL-date discovery, parser upgrades, stale review and retry cooldown passed."
        )


if __name__ == "__main__":
    main()
