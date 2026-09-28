"""Bounded scheduling with independent lanes for indexes and actual price files."""

from datetime import timedelta

from psycopg.types.json import Jsonb


def expected_versions():
    from . import (
        coffee_sources,
        colombia_sources,
        dane_weekly,
        international_sources,
        worker,
    )

    kinds = (
        set(worker.PARSER_VERSIONS)
        | set(colombia_sources.PUBLISHERS)
        | set(international_sources.PUBLISHERS)
        | set(coffee_sources.PUBLISHERS)
        | set(dane_weekly.PUBLISHERS)
    )
    return Jsonb({kind: worker.parser_version(kind) for kind in kinds})


def daily_candidates(db, today):
    from .colombia_sources import ROOTS as colombia
    from .dane_weekly import ROOTS as weekly
    from .international_sources import ROOTS as international

    roots = [url for url, _ in (*colombia, *international, *weekly)]
    return db.execute(
        """WITH versions AS (
          SELECT *,processor_version IS DISTINCT FROM coalesce(%s::jsonb->>kind,'source-v1') AS outdated
          FROM ingestion_asset
        ), fresh AS (
          SELECT url,row_number() OVER(PARTITION BY kind ORDER BY discovered_at DESC,url) AS turn
          FROM ingestion_asset WHERE (kind LIKE 'colombia-%%' OR kind LIKE 'international-%%' OR kind IN ('dane-weekly-xlsx','dane-weekly-pdf'))
          AND observed_on IS NULL AND status='pending'
          AND discovered_at>=now()-interval '48 hours'
        ), candidates AS (SELECT a.*,row_number() OVER(PARTITION BY kind ORDER BY
          CASE WHEN status='pending' THEN 0 ELSE 1 END, observed_on DESC NULLS LAST,
          checked_at ASC NULLS FIRST,url) turn FROM versions a WHERE (
          a.url=ANY(%s::text[]) OR kind IN ('international-worldbank-monthly','colombia-fedegan-csv') OR
          (kind='dane-weekly-index' AND url ~ %s) OR
          (kind IN ('dane-weekly-xlsx','dane-weekly-pdf') AND observed_on>=%s) OR
          (kind NOT LIKE 'international-%%' AND kind NOT LIKE 'colombia-%%' AND (
            kind IN ('inputs','inputs-municipal','coffee','coffee-pdf','rice') OR
            (kind IN ('monthly','supply','supply-reference','supply-index') AND
             (url ~ %s OR observed_on>=%s OR kind='supply-reference')) OR
            (kind='milk' AND url ~* %s) OR
            (kind IN ('milk','monthly-annex','inputs-annex','inputs-reference','inputs-pdf','milk-pdf','monthly-pdf','supply-reference-pdf') AND (observed_on IS NULL OR observed_on>=%s)) OR
            (kind IN ('daily','daily-pdf','city-zip') AND observed_on>=%s)
          )) OR ((kind LIKE 'international-%%' OR kind LIKE 'colombia-%%') AND observed_on>=%s)
          OR a.url IN (SELECT url FROM fresh WHERE turn<=3))
          AND (outdated OR (status<>'awaiting-ocr' AND (status<>'review' OR checked_at<now()-interval '1 day')))
          AND ((outdated AND status<>'pending') OR checked_at IS NULL OR checked_at<now()-interval '6 hours')
        ) SELECT url,kind,observed_on FROM candidates
          ORDER BY CASE WHEN url=ANY(%s::text[]) THEN 0 ELSE 1 END,turn,
            CASE WHEN kind='coffee-pdf' THEN 0 WHEN kind='coffee' THEN 1
                 WHEN kind IN ('daily','city-zip') THEN 2
                 WHEN kind IN ('inputs','inputs-municipal','supply') THEN 4 ELSE 3 END,
            observed_on DESC NULLS LAST,checked_at ASC NULLS FIRST,url""",
        (
            expected_versions(),
            roots,
            str(today.year) + "|" + str(today.year - 1),
            today - timedelta(days=70),
            str(today.year) + "|" + str(today.year - 1),
            today.replace(month=1, day=1),
            # DANE revises this annual workbook in place, sometimes months
            # after its last ingested observation. Individual monthly leaves
            # must still use the recency cutoff below.
            rf"/anex-SIPSALeche-SerieHistoricaPrecios-({today.year}|{today.year - 1})\.xlsx?([?].*)?$",
            today - timedelta(days=70),
            today - timedelta(days=14),
            today - timedelta(days=14),
            roots,
        ),
    ).fetchall()


def backfill_candidates(db, limit):
    return db.execute(
        """WITH versions AS (
          SELECT *,processor_version IS DISTINCT FROM coalesce(%s::jsonb->>kind,'source-v1') AS outdated
          FROM ingestion_asset
        ), eligible AS (
          SELECT * FROM versions WHERE
            (status IN ('pending','failed') OR
             (outdated AND status IN ('complete','processed','archived','review','awaiting-ocr')) OR
             (status IN ('complete','processed','archived','review') AND checked_at<now()-interval '30 days'))
            AND (checked_at IS NULL OR checked_at<now()-interval '6 hours' OR
                 (outdated AND status IN ('complete','processed','archived','review','awaiting-ocr','failed')))
        ), fair AS (
          SELECT *,row_number() OVER(PARTITION BY kind ORDER BY
            CASE WHEN outdated AND status IN ('failed','review','awaiting-ocr') THEN 0
                 WHEN status='pending' THEN 1 WHEN outdated THEN 2
                 WHEN status='failed' THEN 4 ELSE 3 END,
            CASE WHEN kind LIKE 'colombia-%%' OR kind LIKE 'international-%%' OR kind IN ('dane-weekly-xlsx','dane-weekly-pdf') THEN observed_on END DESC NULLS LAST,
            CASE WHEN kind LIKE 'colombia-%%' OR kind LIKE 'international-%%' OR kind IN ('dane-weekly-xlsx','dane-weekly-pdf') THEN discovered_at END DESC,
            coalesce(observed_on,'1900-01-01'),url) AS turn
          FROM eligible
        ) SELECT url,kind,observed_on FROM fair ORDER BY turn,
          CASE WHEN kind='city-zip' THEN 0 WHEN kind LIKE 'colombia-%%' THEN 1
               WHEN kind LIKE 'international-%%' THEN 2 ELSE 3 END,kind LIMIT %s""",
        (expected_versions(), max(1, min(int(limit), 1000))),
    ).fetchall()


def supply_validation_retry(db):
    """Give one interrupted whole-workbook validation a full hourly window.

    Supply must validate the entire native source before publication checkpoints.
    Repeatedly appending it after current large input files can exhaust every run
    before that first checkpoint. Only a time-budget deferral earns this slot;
    malformed, reviewed or newly discovered sources keep the ordinary queue.
    """
    return db.execute(
        """SELECT url,kind,observed_on FROM ingestion_asset
        WHERE kind='supply' AND status='pending'
          AND error IN ('Supply native validation exceeded the run budget',
                        'Supply native validation deferred before starting')
          AND (checked_at IS NULL OR checked_at<now()-interval '6 hours')
        ORDER BY checked_at ASC NULLS FIRST,url LIMIT 1"""
    ).fetchall()
