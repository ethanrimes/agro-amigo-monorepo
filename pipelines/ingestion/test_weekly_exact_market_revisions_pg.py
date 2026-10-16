"""Full-schema retained publication of two exact weekly market-wrap originals.

Opt in only with an empty, disposable local PostgreSQL database. No source HTTP
or provider call is made. The immutable old quote versions remain in place.
"""

import hashlib
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import psycopg
from psycopg.types.json import Jsonb

from . import dane_weekly as weekly, official_sources, worker, write_pacing
from .resumable_inputs import WorkDeferred
from .retained_pdf_upgrade import retained_pdf_upgrade


SOURCES = (
    (weekly.JANUARY_2017_JAN13_URL, weekly.JANUARY_2017_JAN13_SHA,
     "official-v2:dane-weekly-v24", "testdata/weekly_market_wrap_originals", 4674, 4523),
    (weekly.NOVEMBER_2016_MEDELLIN_WRAP_URL, weekly.NOVEMBER_2016_MEDELLIN_WRAP_SHA,
     "official-v2:dane-weekly-v24",
     "testdata/weekly_2016_schematic", 4709, 4560),
)


@unittest.skipUnless(os.environ.get("AGRO_WEEKLY_MARKET_TEST_DSN")
                     or os.environ.get("AGRO_WEEKLY_EXACT_REPLAY_TEST_DSN")
                     or os.environ.get("AGRO_WEEKLY_MARKET_POSTGRES_TEST") == "1",
                     "Explicit empty disposable PostgreSQL database required")
class ExactWeeklyMarketRevisionPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn = (os.environ.get("AGRO_WEEKLY_MARKET_TEST_DSN")
                   or os.environ.get("AGRO_WEEKLY_EXACT_REPLAY_TEST_DSN")
                   or os.environ.get("DATABASE_URL", ""))
        if not cls.dsn:
            raise RuntimeError("Owned weekly PostgreSQL DSN is required")
        cls.db = psycopg.connect(cls.dsn, autocommit=True)
        if (not str(cls.db.info.host).startswith("/tmp/agro-weekly-")
                or not cls.db.info.dbname.startswith("agro_weekly_")):
            cls.db.close()
            raise RuntimeError("Only a fresh owned local weekly database is allowed")
        if cls.db.execute("SELECT inet_server_addr()").fetchone()[0] is not None:
            cls.db.close()
            raise RuntimeError("Weekly replay database must use a Unix socket")
        if cls.db.execute("SELECT count(*) FROM source_document").fetchone()[0]:
            cls.db.close()
            raise RuntimeError("Weekly replay database is not empty")
        cls.db.execute("SET statement_timeout='90s'")

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def setUp(self):
        self.enterContext(patch.dict(os.environ, {"DATABASE_URL": self.dsn}))

    def _old_rows(self, body, url):
        native_column = weekly._native_column

        def prior_column(*args, **kwargs):
            return native_column(*args, **{
                **kwargs, "january_2017_market_wrap": False,
                "november_2016_medellin_wrap": False,
            })

        constant = ("JANUARY_2017_JAN13_URL" if url == SOURCES[0][0]
                    else "NOVEMBER_2016_MEDELLIN_WRAP_URL")
        with (patch.object(weekly, "_native_column", side_effect=prior_column),
              patch.object(weekly, constant, "_prior_grid_")):
            return weekly.parse_pdf(body, url)

    def _replay(self, spec):
        url, did, old_asset_version, directory, all_count, priced_count = spec
        body = (Path(__file__).parent / directory / f"{did}.pdf").read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(), did)
        old_rows = self._old_rows(body, url)
        new_rows = weekly.parse_pdf(body, url)
        self.assertEqual((len(old_rows), len(new_rows)), (all_count, all_count))
        self.assertEqual(sum(r["price"] is not None for r in new_rows), priced_count)
        self.assertEqual([r["source_locator"] for r in old_rows],
                         [r["source_locator"] for r in new_rows])
        new_version = worker.parser_version("dane-weekly-pdf", url)
        self.assertEqual(worker.asset_parser_version("dane-weekly-pdf", url), new_version)
        self.db.execute(
            "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,"
            "reference_period,page_count,content,metadata) VALUES(%s,'DANE weekly','DANE',%s,"
            "'application/pdf','original','2016-11/2017-01',%s,%s,%s)",
            (did, url, 44 if did == SOURCES[0][1] else 48, body,
             Jsonb({"ingestion_kind": "dane-weekly-pdf"})),
        )
        self.db.execute(
            "INSERT INTO ingestion_asset(url,kind,status,processor_version,document_id,"
            "observed_on,checked_at,records) VALUES(%s,'dane-weekly-pdf','complete',%s,%s,"
            "%s,now()-interval '7 hours',%s)",
            (url, old_asset_version, did,
             "2017-01-13" if did == SOURCES[0][1] else "2016-11-04", priced_count),
        )
        with patch.object(write_pacing.time, "sleep"):
            self.assertEqual(official_sources.publish_rows(
                self.db, old_rows, did, "dane-weekly-pdf"), priced_count)
        old_xmins = dict(self.db.execute(
            "SELECT source_locator,xmin::text FROM official_price_quote "
            "WHERE document_id=%s AND parser_version=%s", (did, worker.parser_version("dane-weekly-pdf"))
        ).fetchall())
        self.assertEqual(len(old_xmins), priced_count)
        self.assertEqual(retained_pdf_upgrade(
            self.db, url, "dane-weekly-pdf", new_version, new_version), body)
        with (patch.object(worker, "fetch_asset", side_effect=AssertionError("HTTP forbidden")),
              patch("pipelines.ingestion.blob_archive.retain_original_blob"),
              patch.object(write_pacing, "pause_between_batches",
                           side_effect=WorkDeferred("forced after first batch"))):
            with self.assertRaises(WorkDeferred):
                worker._process_asset(self.db, url, "dane-weekly-pdf", None)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM official_price_quote WHERE document_id=%s AND parser_version=%s",
            (did, new_version)).fetchone()[0], 256)
        self.assertIsNone(self.db.execute(
            "SELECT 1 FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s "
            "AND step='official:complete'", (did, new_version)).fetchone())
        self.assertEqual(self.db.execute("SELECT status FROM ingestion_asset WHERE url=%s",
                                         (url,)).fetchone()[0], "pending")
        self.assertEqual(retained_pdf_upgrade(
            self.db, url, "dane-weekly-pdf", new_version, new_version), body)
        if did == SOURCES[1][1]:
            for prior_version, expected in (
                ("official-v2:dane-weekly-v24:nov2016-medellin-market-wrap-v1", body),
                ("official-v2:dane-weekly-v23", None),
            ):
                with self.assertRaisesRegex(RuntimeError, "probe rollback"):
                    with self.db.transaction():
                        self.db.execute("UPDATE ingestion_asset SET processor_version=%s "
                                        "WHERE url=%s", (prior_version, url))
                        self.assertEqual(retained_pdf_upgrade(
                            self.db, url, "dane-weekly-pdf", new_version, new_version), expected)
                        raise RuntimeError("probe rollback")
        # A missing locator with a forged same-version value must fail before
        # the publisher can silently skip that immutable primary key.
        existing = {r[0] for r in self.db.execute(
            "SELECT source_locator FROM official_price_quote WHERE document_id=%s "
            "AND parser_version=%s", (did, new_version)).fetchall()}
        missing = next(r["source_locator"] for r in new_rows
                       if r["price"] is not None and r["source_locator"] not in existing)
        with self.assertRaisesRegex(ValueError, "collides"):
            with self.db.transaction():
                self.db.execute(
                    "INSERT INTO official_price_quote(document_id,source_locator,parser_version,"
                    "quote_key,product_id,product_name,category,publisher,series,basis,currency,unit,"
                    "market,observed_on,period_start,price,min_price,max_price,source_page,details) "
                    "SELECT document_id,source_locator,%s,quote_key,product_id,product_name,category,"
                    "publisher,series,basis,currency,unit,market,observed_on,period_start,price+1,"
                    "min_price,max_price,source_page,details FROM official_price_quote "
                    "WHERE document_id=%s AND source_locator=%s AND parser_version=%s",
                    (new_version, did, missing, worker.parser_version("dane-weekly-pdf")),
                )
                official_sources.publish_rows(self.db, new_rows, did, "dane-weekly-pdf", source_url=url)
        with (patch.object(worker, "fetch_asset", side_effect=AssertionError("HTTP forbidden")),
              patch("pipelines.ingestion.blob_archive.retain_original_blob"),
              patch.object(write_pacing.time, "sleep")):
            self.assertEqual(worker.process_asset(self.db, url, "dane-weekly-pdf", None),
                             priced_count)
            new_xmins = dict(self.db.execute(
                "SELECT source_locator,xmin::text FROM official_price_quote "
                "WHERE document_id=%s AND parser_version=%s", (did, new_version)
            ).fetchall())
            self.assertEqual(official_sources.publish_rows(
                self.db, new_rows, did, "dane-weekly-pdf", source_url=url), priced_count)
            self.assertEqual(dict(self.db.execute(
                "SELECT source_locator,xmin::text FROM official_price_quote "
                "WHERE document_id=%s AND parser_version=%s", (did, new_version)
            ).fetchall()), new_xmins)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM official_price_quote WHERE document_id=%s AND parser_version=%s",
            (did, new_version)).fetchone()[0], priced_count)
        self.assertEqual(self.db.execute(
            "SELECT records FROM ingestion_checkpoint WHERE document_id=%s "
            "AND processor_version=%s AND step='official:complete'", (did, new_version)
        ).fetchone()[0], priced_count)
        self.assertEqual(dict(self.db.execute(
            "SELECT source_locator,xmin::text FROM official_price_quote WHERE document_id=%s "
            "AND parser_version=%s", (did, worker.parser_version("dane-weekly-pdf"))
        ).fetchall()), old_xmins)
        # Every corrected quote is a current winner for its own locator and
        # every false old identity remains raw but is withdrawn from the view.
        changed = [(old, new) for old, new in zip(old_rows, new_rows)
                   if old["price"] is not None and old["market"] != new["market"]]
        self.assertTrue(changed)
        for old, new in changed[:3]:
            winner = self.db.execute(
                "SELECT market,price,parser_version FROM published_official_price "
                "WHERE document_id=%s AND source_locator=%s",
                (did, new["source_locator"]),
            ).fetchone()
            self.assertEqual((winner[0], float(winner[1]), winner[2]),
                             (new["market"], float(new["price"]), new_version))
            old_key = self.db.execute(
                "SELECT quote_key FROM official_price_quote WHERE document_id=%s "
                "AND source_locator=%s AND parser_version=%s",
                (did, old["source_locator"], worker.parser_version("dane-weekly-pdf")),
            ).fetchone()[0]
            self.assertIsNone(self.db.execute(
                "SELECT 1 FROM published_official_price WHERE document_id=%s "
                "AND source_locator=%s AND quote_key=%s", (did, old["source_locator"], old_key)
            ).fetchone())
        if did == SOURCES[0][1]:
            for market, price in (("Manizales (Caldas)", 2217),
                                  ("Medellín, Central Mayorista de Antioquia", 1500)):
                target = next(r for r in new_rows if r["product_name"] == "Coliflor"
                              and r["source_page"] == 9 and r["market"] == market
                              and r["price"] == price)
                winner = self.db.execute(
                    "SELECT market,price,parser_version,quote_key FROM published_official_price "
                    "WHERE document_id=%s AND source_locator=%s",
                    (did, target["source_locator"]),
                ).fetchone()
                self.assertEqual((winner[0], float(winner[1]), winner[2]),
                                 (market, price, new_version))
                payload, dirty = self.db.execute(
                    "SELECT payload,dirty FROM official_catalog_current WHERE quote_key=%s",
                    (winner[3],),
                ).fetchone()
                self.assertFalse(dirty)
                self.assertIsNotNone(payload)
        return {"document_id": did, "all": all_count, "priced": priced_count,
                "changed_priced": len(changed)}

    def test_jan13_exact_original_replay(self):
        self._replay(SOURCES[0])

    def test_nov04_exact_original_replay(self):
        self._replay(SOURCES[1])


if __name__ == "__main__":
    unittest.main()
