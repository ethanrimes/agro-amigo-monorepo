"""Official daily query publication and failure retention in TEMP PostgreSQL."""

import hashlib
import os
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from . import dane_daily_query, query_publication, worker
from .test_dane_daily_query import BROKEN, DAY, fake_fetcher


@unittest.skipUnless(
    os.environ.get("AGRO_QUERY_PUBLICATION_POSTGRES_TEST") == "1",
    "Explicit opt-in for PostgreSQL TEMP-only query recovery checks",
)
class QueryPublicationTests(unittest.TestCase):
    def setUp(self):
        self.db = worker.connect()
        self.addCleanup(self.db.close)
        self.db.execute("SET search_path=pg_temp")
        self.db.execute("SET statement_timeout='20s'")
        for table in (
            "source_document",
            "document_alias",
            "historical_price",
            "official_price_quote",
            "official_source_review",
            "official_catalog_current",
            "ingestion_checkpoint",
            "retained_record",
            "ingestion_asset",
        ):
            self.db.execute(
                f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL)"
            )
            self.assertEqual(
                self.db.execute(
                    "SELECT relpersistence FROM pg_class WHERE oid=to_regclass(%s)",
                    (table,),
                ).fetchone(),
                ("t",),
            )
        self.db.execute(
            "INSERT INTO ingestion_asset(url,kind,observed_on,status) VALUES(%s,'daily',%s,'failed')",
            (BROKEN, DAY),
        )
        self.fetcher = fake_fetcher
        self.enterContext(patch.dict(os.environ, {"AzureWebJobsStorage": ""}))
        self.enterContext(
            patch.object(
                worker.SESSION,
                "get",
                side_effect=lambda url, **_: self.response(url, None),
            )
        )
        self.enterContext(
            patch.object(
                worker.SESSION,
                "post",
                side_effect=lambda url, data, **_: self.response(url, data),
            )
        )

    def response(self, url, params):
        return SimpleNamespace(
            content=self.fetcher(url, params), raise_for_status=lambda: None
        )

    def counts(self):
        return self.db.execute(
            "SELECT (SELECT count(*) FROM source_document),(SELECT count(*) FROM historical_price),(SELECT count(*) FROM official_price_quote),(SELECT count(*) FROM official_catalog_current WHERE payload IS NOT NULL)"
        ).fetchone()

    def test_full_recovery_replay_keeps_raw_json_prices_ranges_and_public_catalog(self):
        for _ in range(2):
            self.assertEqual(query_publication.recover(self.db, BROKEN, 404, DAY), 3)
        self.assertEqual(self.counts(), (5, 3, 3, 3))
        self.assertEqual(
            self.db.execute("SELECT status,records FROM ingestion_asset").fetchone(),
            ("complete", 3),
        )
        self.assertEqual(
            self.db.execute(
                "SELECT DISTINCT series,currency,basis FROM official_price_quote"
            ).fetchall(),
            [
                (
                    "dane-daily-query",
                    "COP",
                    "Precio mayorista diario · promedio publicado",
                )
            ],
        )
        row = self.db.execute(
            "SELECT price,min_price,max_price,unit,source_page FROM official_price_quote WHERE product_name='Pimentón'"
        ).fetchone()
        self.assertEqual(row, (1417, 1333, 1500, "kg", None))
        self.assertEqual(
            self.db.execute(
                "SELECT unit FROM official_price_quote WHERE product_name='Huevo rojo A'"
            ).fetchone(),
            ("unit",),
        )
        self.assertEqual(
            self.db.execute(
                "SELECT unit FROM official_price_quote WHERE product_name='Aceite vegetal mezcla'"
            ).fetchone(),
            ("litre",),
        )
        self.assertEqual(
            self.db.execute(
                "SELECT DISTINCT source_url FROM source_document"
            ).fetchall(),
            [(dane_daily_query.EXPLORER_URL,)],
        )
        self.assertEqual(
            self.db.execute(
                "SELECT count(*) FROM retained_record WHERE table_name='official_query_response'"
            ).fetchone(),
            (5,),
        )

    def test_malformed_last_response_is_archived_with_prior_responses_without_prices(
        self,
    ):
        def fetch(url, params):
            return (
                b'{"unexpected":"publisher changed schema"}'
                if params and params["dataAccessId"] == "qryTabla"
                else fake_fetcher(url, params)
            )

        self.fetcher = fetch
        with self.assertRaisesRegex(ValueError, "resultset"):
            query_publication.recover(self.db, BROKEN, 404, DAY)
        self.assertEqual(self.counts(), (5, 0, 0, 0))
        self.assertEqual(
            self.db.execute(
                "SELECT count(*) FROM retained_record WHERE table_name='official_query_response'"
            ).fetchone(),
            (5,),
        )

    def test_later_network_failure_retains_downloaded_request_evidence(self):
        def fetch(url, params):
            if params and params["dataAccessId"] == "qryArticulo":
                raise TimeoutError("temporary provider failure")
            return fake_fetcher(url, params)

        self.fetcher = fetch
        with self.assertRaises(TimeoutError):
            query_publication.recover(self.db, BROKEN, 404, DAY)
        self.assertEqual(self.counts(), (3, 0, 0, 0))

    def test_supplemental_query_preserves_valid_archive_identity_and_status(self):
        did = worker.archive(self.db, BROKEN, b"original archive", "city-zip", DAY)
        self.db.execute(
            "UPDATE ingestion_asset SET document_id=%s,status='complete',records=969",
            (did,),
        )
        self.assertEqual(
            query_publication.recover(
                self.db,
                BROKEN,
                404,
                DAY,
                original_id=did,
                preserve_original_status=True,
            ),
            3,
        )
        self.assertEqual(
            self.db.execute(
                "SELECT document_id,status,records FROM ingestion_asset"
            ).fetchone(),
            (did, "complete", 969),
        )
        self.assertEqual(
            self.db.execute(
                "SELECT count(*) FROM official_catalog_current WHERE payload IS NOT NULL"
            ).fetchone(),
            (3,),
        )

    def test_conflicting_original_stays_reviewed_and_parent_linked(self):
        body = b"contradictory original fixture"
        did = worker.archive(self.db, BROKEN, body, "daily", date(2013, 4, 19))
        self.db.execute(
            "UPDATE ingestion_asset SET document_id=%s,status='review'", (did,)
        )
        approved = {BROKEN: (DAY, hashlib.sha256(body).hexdigest())}
        with patch.object(dane_daily_query, "VERIFIED_DATE_CONFLICTS", approved):
            self.assertEqual(
                query_publication.recover(
                    self.db, BROKEN, None, DAY, original_data=body, original_id=did
                ),
                3,
            )
        self.assertEqual(
            self.db.execute(
                "SELECT document_id,status FROM ingestion_asset"
            ).fetchone(),
            (did, "review"),
        )
        self.assertEqual(
            self.db.execute(
                "SELECT count(*) FROM official_catalog_current WHERE payload IS NOT NULL"
            ).fetchone(),
            (3,),
        )
        parents = self.db.execute(
            "SELECT metadata->'parents' FROM source_document WHERE metadata->>'original_filename' LIKE '%daily-prices.json'"
        ).fetchone()[0]
        self.assertIn(did, parents)
