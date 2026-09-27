"""Exercise real PostgreSQL scheduling SQL using only a temporary queue table."""

from datetime import date, timedelta

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
        # Reproduce the Sep 2026 milk gap: the current annual URL was revised
        # in September, while its stored observation was still in May. The
        # URL's annual scope, not that old observation, requires revalidation.
        audit_day = date(2026, 9, 27)
        milk_root = "https://www.dane.gov.co/files/operaciones/SIPSA/"
        milk_cases = [
            ("anex-SIPSALeche-SerieHistoricaPrecios-2026.xlsx", date(2026, 5, 1), "complete", "now()-interval '1 day'", True),
            ("anex-SIPSALeche-SerieHistoricaPrecios-2025.xlsx", date(2025, 5, 1), "complete", "now()-interval '1 day'", True),
            ("anex-SIPSALeche-SerieHistoricaPrecios-2024.xlsx", date(2024, 5, 1), "complete", "now()-interval '1 day'", False),
            ("anex-SIPSALeche-may2026.xlsx", date(2026, 5, 1), "complete", "now()-interval '1 day'", False),
            ("anex-SIPSALeche-ago2026.xlsx", date(2026, 8, 1), "complete", "now()-interval '1 day'", True),
            ("ANEX-SIPSALECHE-SERIEHISTORICAPRECIOS-2026.XLS", date(2026, 5, 1), "complete", "now()-interval '1 day'", True),
            ("anex-SIPSALeche-SerieHistoricaPrecios-2026.xlsx?cooldown", date(2026, 5, 1), "complete", "now()", False),
            ("anex-SIPSALeche-SerieHistoricaPrecios-2026.xlsx?ocr", date(2026, 5, 1), "awaiting-ocr", "now()-interval '1 day'", False),
            ("anex-SIPSALeche-SerieHistoricaPrecios-2026.xlsx?review", date(2026, 5, 1), "review", "now()-interval '7 hours'", False),
            ("anex-SIPSALeche-SerieHistoricaPrecios-2026.xlsx?stale-review", date(2026, 5, 1), "review", "now()-interval '2 days'", True),
            ("anex-SIPSALeche-SerieHistoricaPrecios-2026.xlsx?changed", date(2026, 5, 1), "complete", "now()-interval '1 day'", True),
        ]
        for name, observed_on, status, checked, _ in milk_cases:
            db.execute(
                f"INSERT INTO ingestion_asset(url,kind,status,observed_on,checked_at) VALUES(%s,'milk',%s,%s,{checked})",
                (milk_root + name, status, observed_on),
            )
        daily = {url for url, _, _ in queue_plan.daily_candidates(db, audit_day)}
        for name, _, _, _, expected in milk_cases:
            assert ((milk_root + name) in daily) == expected, name
        next_year = {url for url, _, _ in queue_plan.daily_candidates(db, date(2027, 9, 27))}
        assert milk_root + "anex-SIPSALeche-SerieHistoricaPrecios-2026.xlsx" in next_year
        assert milk_root + "anex-SIPSALeche-SerieHistoricaPrecios-2025.xlsx" not in next_year
        # All other mutable annual families already have an independent
        # eligibility rule. Guard them against the same old-observation bug.
        for kind in ("inputs", "inputs-municipal", "coffee", "coffee-pdf", "rice", "monthly", "supply", "supply-reference", "supply-index"):
            source = f"https://example.invalid/annual/{kind}-2026.xlsx"
            db.execute(
                "INSERT INTO ingestion_asset(url,kind,status,observed_on,checked_at) VALUES(%s,%s,'complete',%s,now()-interval '1 day')",
                (source, kind, audit_day - timedelta(days=150)),
            )
        daily = {url for url, _, _ in queue_plan.daily_candidates(db, audit_day)}
        for kind in ("inputs", "inputs-municipal", "coffee", "coffee-pdf", "rice", "monthly", "supply", "supply-reference", "supply-index"):
            assert f"https://example.invalid/annual/{kind}-2026.xlsx" in daily, kind
        # A :25 checkpoint should be eligible at the next :15 hourly run,
        # fifty minutes later. The old five-hour backdate missed that run;
        # expected deferral is not a source error with a six-hour retry delay.
        for name, status, elapsed in [
            ("checkpoint-next-hour", "pending", "6 hours 50 minutes"),
            ("checkpoint-immediate-next-run", "pending", "6 hours 1 second"),
            ("old-checkpoint-next-hour", "pending", "5 hours 50 minutes"),
            ("failed-next-hour", "failed", "50 minutes"),
        ]:
            db.execute(
                "INSERT INTO ingestion_asset(url,kind,status,checked_at,processor_version) VALUES(%s,'inputs',%s,now()-%s::interval,%s)",
                ("https://example.invalid/" + name, status, elapsed, worker.parser_version("inputs")),
            )
        for candidates in (
            queue_plan.daily_candidates(db, audit_day),
            queue_plan.backfill_candidates(db, 1000),
        ):
            selected = {url.rsplit("/", 1)[-1] for url, _, _ in candidates}
            assert {"checkpoint-next-hour", "checkpoint-immediate-next-run"} <= selected
            assert not {"old-checkpoint-next-hour", "failed-next-hour"} & selected
        print(
            "Temporary PostgreSQL queue: index/leaf fairness, NULL-date discovery, parser upgrades, stale review, retry cooldown, 11 milk annual/leaf cases, calendar-year rollover, 9 other mutable annual families and checkpoint continuation without failure cooldown passed."
        )


if __name__ == "__main__":
    main()
