"""Bounded scheduling with independent lanes for indexes and actual price files."""

from datetime import timedelta

from psycopg.types.json import Jsonb


def expected_versions():
    from . import colombia_sources, international_sources, worker

    kinds = (
        set(worker.PARSER_VERSIONS)
        | set(colombia_sources.PUBLISHERS)
        | set(international_sources.PUBLISHERS)
    )
    return Jsonb({kind: worker.parser_version(kind) for kind in kinds})


def daily_candidates(db, today):
    from .colombia_sources import ROOTS as colombia
    from .international_sources import ROOTS as international

    roots = [url for url, _ in (*colombia, *international)]
    return db.execute(
        """WITH fresh AS (
          SELECT url,row_number() OVER(PARTITION BY kind ORDER BY discovered_at DESC,url) AS turn
          FROM ingestion_asset WHERE (kind LIKE 'colombia-%%' OR kind LIKE 'international-%%')
          AND observed_on IS NULL AND status='pending'
          AND discovered_at>=now()-interval '48 hours'
        ) SELECT a.url,a.kind,a.observed_on FROM ingestion_asset a WHERE
          a.url=ANY(%s::text[]) OR kind IN ('international-worldbank-monthly','colombia-fedegan-csv') OR
          (kind NOT LIKE 'international-%%' AND kind NOT LIKE 'colombia-%%' AND (
            kind IN ('monthly','inputs','inputs-municipal','coffee','coffee-pdf','rice') OR
            (kind IN ('milk','monthly-annex','inputs-annex','inputs-reference','inputs-pdf','milk-pdf','monthly-pdf') AND (observed_on IS NULL OR observed_on>=%s)) OR
            (kind IN ('daily','daily-pdf','city-zip') AND observed_on>=%s)
          )) OR ((kind LIKE 'international-%%' OR kind LIKE 'colombia-%%') AND observed_on>=%s)
          OR a.url IN (SELECT url FROM fresh WHERE turn<=3)
          ORDER BY CASE WHEN kind='coffee' THEN 0 WHEN kind='coffee-pdf' THEN 1
            WHEN a.url=ANY(%s::text[]) THEN 2 WHEN kind IN ('daily','daily-pdf','city-zip') THEN 3 ELSE 4 END,
            checked_at ASC NULLS FIRST,observed_on DESC NULLS LAST,a.url""",
        (
            roots,
            today - timedelta(days=70),
            today - timedelta(days=14),
            today - timedelta(days=14),
            roots,
        ),
    ).fetchall()


def backfill_candidates(db, limit):
    return db.execute(
        """WITH versions AS (
          SELECT *,processor_version<>coalesce(%s::jsonb->>kind,'source-v1') AS outdated
          FROM ingestion_asset
        ), eligible AS (
          SELECT * FROM versions WHERE
            (status IN ('pending','failed') OR
             (outdated AND status IN ('complete','processed','archived','review','awaiting-ocr')) OR
             (status IN ('complete','processed','archived','review') AND checked_at<now()-interval '30 days'))
            AND (checked_at IS NULL OR checked_at<now()-interval '6 hours' OR
                 (outdated AND status IN ('complete','processed','archived','review','awaiting-ocr')))
        ), fair AS (
          SELECT *,row_number() OVER(PARTITION BY kind ORDER BY
            CASE WHEN status IN ('pending','failed') OR outdated THEN 0 ELSE 1 END,
            CASE WHEN kind LIKE 'colombia-%%' OR kind LIKE 'international-%%' THEN observed_on END DESC NULLS LAST,
            CASE WHEN kind LIKE 'colombia-%%' OR kind LIKE 'international-%%' THEN discovered_at END DESC,
            coalesce(observed_on,'1900-01-01'),url) AS turn
          FROM eligible
        ) SELECT url,kind,observed_on FROM fair ORDER BY turn,
          CASE WHEN kind='city-zip' THEN 0 WHEN kind LIKE 'colombia-%%' THEN 1
               WHEN kind LIKE 'international-%%' THEN 2 ELSE 3 END,kind LIMIT %s""",
        (expected_versions(), max(1, min(int(limit), 1000))),
    ).fetchall()
