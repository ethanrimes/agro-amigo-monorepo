"""DANE monthly price bulletin and press release have distinct index identities."""

import json
import os
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from . import queue_plan, worker


EVIDENCE = Path("artifacts/qa-resumed-20261001/dane-intake-readonly-20261003/monthly-march-index-links.json")
PRESS = "https://www.dane.gov.co/files/operaciones/SIPSA/cp-SIPSAMensual-mar2026.pdf"
TECHNICAL = "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSAMensual-mar2026.pdf"
ANNEX = "https://www.dane.gov.co/files/operaciones/SIPSA/anex-SIPSAMensual-mar2026.xlsx"
HISTORY = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/anex_mensual_serie_historica.xlsx"
ARCHIVE = worker.MONTHLY + "/mayoristas-boletin-mensual-sipsa-historicos"
DAY = date(2026, 3, 31)


def index_links():
    return [("Serie histórica", HISTORY), ("Históricos", ARCHIVE)]


def archive_links():
    return [("Boletín técnico", TECHNICAL), ("Comunicado de prensa", PRESS), ("Anexos", ANNEX)]


class MonthlyPressDiscoveryTests(unittest.TestCase):
    def test_exact_official_index_labels_and_urls_are_retained_as_oracles(self):
        evidence = json.loads(EVIDENCE.read_text())
        self.assertEqual(evidence["march_2026_links"], [list(link) for link in archive_links()])
        self.assertTrue(worker.is_monthly_press_release("Comunicado de prensa", PRESS))
        self.assertFalse(worker.is_monthly_press_release("Boletín técnico", TECHNICAL))
        self.assertFalse(worker.is_monthly_press_release("Comunicado de prensa", TECHNICAL))
        self.assertFalse(worker.is_monthly_press_release("Boletín técnico", PRESS))
        self.assertFalse(worker.is_monthly_press_release(
            "Comunicado de prensa", PRESS.replace("www.dane.gov.co", "dane.gov.co.evil.example")))

    def test_press_is_not_queued_but_bulletin_and_every_excel_remain(self):
        class EmptyDb:
            def execute(self, *_args):
                return self

            def fetchall(self):
                return []

        extra_excel = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/anex_mensual_oct_2018.xlsx"
        with (patch.object(worker, "links", side_effect=[index_links(), archive_links() + [("Anexo octubre 2018", extra_excel)]]),
              patch.object(worker, "queue") as queue):
            worker.discover_monthly(EmptyDb())
        queued = {(call.args[1], call.args[2], call.args[3] if len(call.args) > 3 else None)
                  for call in queue.call_args_list}
        self.assertNotIn(PRESS, {url for url, _, _ in queued})
        self.assertIn((TECHNICAL, "monthly-pdf", DAY), queued)
        self.assertIn((ANNEX, "monthly-annex", DAY), queued)
        self.assertIn((extra_excel, "monthly-annex", date(2018, 10, 31)), queued)
        self.assertIn((HISTORY, "monthly", None), queued)


@unittest.skipUnless(os.environ.get("AGRO_MONTHLY_PRESS_POSTGRES_TEST") == "1",
                     "Explicit private PostgreSQL TEMP-table opt-in")
class MonthlyPressPostgresTests(unittest.TestCase):
    def setUp(self):
        self.db = worker.connect()
        self.addCleanup(self.db.close)
        self.assertTrue(self.db.info.host.startswith("/tmp/agro-"))
        self.db.execute("SET search_path=pg_temp")
        for table in ("source_document", "ingestion_asset", "official_price_quote", "official_source_review"):
            self.db.execute(f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL)")
        self.enterContext(patch.object(worker, "links", side_effect=lambda url:
                                    index_links() if url == worker.MONTHLY else archive_links()))

    def add(self, url, *, status="failed", error="HTTPError: 404 Client Error",
            document_id=None, records=0, kind="monthly-pdf"):
        self.db.execute(
            """INSERT INTO ingestion_asset(url,kind,observed_on,status,error,document_id,records,
                       processor_version,checked_at)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,now()-interval '31 days')""",
            (url, kind, DAY, status, error, document_id, records, "monthly-pdf-v0"),
        )

    def test_atomic_retirement_keeps_old_failed_url_and_excludes_only_its_review(self):
        self.add(PRESS)
        unrelated = PRESS.replace("mar2026", "feb2026")
        null_review = TECHNICAL.replace("mar2026", "oct2026")
        self.add(unrelated)
        self.add(null_review, status="review", error=None)
        self.db.execute("UPDATE ingestion_asset SET observed_on=%s WHERE url=%s",
                        (date.today(), null_review))
        worker.discover_monthly(self.db)
        state = self.db.execute(
            "SELECT url,kind,status,error,document_id,records,processor_version FROM ingestion_asset WHERE url=%s",
            (PRESS,)).fetchone()
        self.assertEqual(state[:3], (PRESS, "monthly-pdf", "review"))
        self.assertEqual(state[4:6], (None, 0))
        self.assertTrue(state[3].startswith(worker.MONTHLY_PRESS_REVIEW))
        self.assertIn("HTTPError: 404", state[3])
        self.assertEqual(state[6], worker.parser_version("monthly-pdf"))
        self.assertEqual(self.db.execute("SELECT status FROM ingestion_asset WHERE url=%s", (unrelated,)).fetchone(), ("failed",))
        for candidates in (queue_plan.backfill_candidates(self.db, 200),
                           queue_plan.daily_candidates(self.db, date.today())):
            urls = {row[0] for row in candidates}
            self.assertNotIn(PRESS, urls)
            self.assertIn(null_review, urls)
        self.assertEqual(self.db.execute("SELECT count(*) FROM source_document").fetchone(), (0,))
        self.assertEqual(self.db.execute("SELECT count(*) FROM official_price_quote").fetchone(), (0,))

    def test_archived_or_priced_or_nonfailed_press_asset_is_never_reconciled(self):
        retained_id = "a" * 64
        self.db.execute("INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content) "
                        "VALUES(%s,'Press original','DANE',%s,'application/pdf','original','2026-03',%s)",
                        (retained_id, PRESS, b"retained"))
        self.add(PRESS, document_id=retained_id)
        worker.discover_monthly(self.db)
        self.assertEqual(self.db.execute("SELECT status,error,document_id FROM ingestion_asset WHERE url=%s", (PRESS,)).fetchone(),
                         ("failed", "HTTPError: 404 Client Error", retained_id))
        self.db.execute("UPDATE ingestion_asset SET document_id=NULL,records=1 WHERE url=%s", (PRESS,))
        worker.discover_monthly(self.db)
        self.assertEqual(self.db.execute("SELECT status FROM ingestion_asset WHERE url=%s", (PRESS,)).fetchone(), ("failed",))
        self.db.execute("UPDATE ingestion_asset SET records=0 WHERE url=%s", (PRESS,))
        worker.discover_monthly(self.db)
        self.assertEqual(self.db.execute("SELECT status FROM ingestion_asset WHERE url=%s", (PRESS,)).fetchone(), ("failed",))


if __name__ == "__main__":
    unittest.main()
