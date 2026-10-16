"""A scheduled city slot reaches real retained PDF children and resumes safely."""

import io
import os
import unittest
import zipfile
from datetime import date
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from psycopg.pq import TransactionStatus

from . import city_reports, worker
from . import test_city_catchup_queue as city_queue_tests
from . import test_city_publication as publication_tests


ORIGINAL = Path(__file__).parent / "testdata/bol-SIPSADiario-regionales-19ago2025.zip"
DAY = date(2025, 8, 19)
NAMES = ("Arauca (Arauca)-19-08-2025.pdf", "Armenia, Mercar-19-08-2025.pdf")
ORIGINAL_SHA = "054c4d08214f7c1e5bc5cbec71ae40fa902be3d084864d2b209c8d8704dcabe9"
CHILD_SHAS = (
    "adca5c7bead893fca0fcec420ca7ba72a86b2f492eff32b7aa45878e3c9b2ebd",
    "56886fce8383435b6abb01117d018f8c51b9a4db31e9d7bb9b78fa9cf901fb34",
)
ORIGINAL_URL = "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-regionales-19ago2025.zip"
# This TEMP-only two-child bundle is deliberately given a distinct URL: the
# official ZIP has 68 members and must never be identified by the repacked SHA.
SOURCE_URL = "https://example.invalid/native-city-two-members.zip"
TEST_VERSION = city_reports.VERSION + "-lane-test"


@unittest.skipUnless(os.environ.get("AGRO_CITY_POSTGRES_TEST") == "1",
                     "Explicit private PostgreSQL city publication opt-in")
class CityCatchupNativePublication(unittest.TestCase):
    local_archive = staticmethod(publication_tests.CityPublicationPostgresTests.local_archive)
    run_case = city_queue_tests.WorkerCityLane.run_case

    def setUp(self):
        # Reuse the existing production-shaped TEMP schema, real native parser,
        # and archive edge; the private connection has no persistent writes.
        publication_tests.CityPublicationPostgresTests.setUp(self)
        assert self.db.execute("SELECT inet_server_addr()").fetchone()[0] is None
        assert self.db.info.host.startswith("/tmp/agro-")
        self.assertEqual(sha256(ORIGINAL.read_bytes()).hexdigest(), ORIGINAL_SHA)
        self.assertIn("bol-SIPSADiario-regionales-19ago2025.zip", ORIGINAL_URL)
        with zipfile.ZipFile(ORIGINAL) as original:
            self.entries = [(name, original.read(name)) for name in NAMES]
        self.assertEqual(tuple(sha256(body).hexdigest() for _, body in self.entries),
                         CHILD_SHAS)
        parsed = [list(city_reports.parse_city_pdf(body, DAY)) for _, body in self.entries]
        self.assertEqual([len(rows) for rows in parsed], [49, 50])
        self.assertEqual(
            (parsed[0][0][0], parsed[0][0][3], parsed[0][0][4],
             parsed[0][0][11], parsed[0][0][12], parsed[0][0][13]),
            ("PDF page 1,table 1,row 7,round 1", "Mandarina común",
             "Arauca (Arauca)", Decimal(65000), Decimal(75000), "kg"),
        )
        self.assertEqual(
            (parsed[1][0][0], parsed[1][0][3], parsed[1][0][4],
             parsed[1][0][11], parsed[1][0][12], parsed[1][0][13]),
            ("PDF page 1,table 1,row 7,round 1", "Limón tahití",
             "Armenia, Mercar", Decimal(2200), Decimal(2400), "kg"),
        )
        self.data = publication_tests.bundle(self.entries)
        self.did = self.local_archive(self.db, SOURCE_URL, self.data, "city-zip")

    def publish(self):
        return city_reports.publish_city_zip(
            self.db, self.data, self.did, SOURCE_URL, DAY,
            processor_version=TEST_VERSION,
        )

    def test_real_children_defer_then_resume_without_false_completion(self):
        rows = [(SOURCE_URL, "city-zip", DAY)]

        def first_attempt(url, kind, day):
            self.assertEqual((url, kind, day), rows[0])
            with patch.object(city_reports.time, "monotonic", side_effect=lambda:
                    100 if self.db.execute("SELECT count(*) FROM ingestion_checkpoint "
                                           "WHERE document_id=%s AND processor_version=%s "
                                           "AND step LIKE 'city-member:%%'",
                                           (self.did, TEST_VERSION)).fetchone()[0] else 0):
                return self.publish()

        first, observed, _ = self.run_case(city=rows, process_callback=first_attempt)
        self.assertEqual([row[0] for row in observed], [SOURCE_URL])
        self.assertEqual(first["assets"], 0)
        self.assertEqual(len(first["deferred"]), 1)
        self.assertEqual(self.db.info.transaction_status, TransactionStatus.IDLE)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s "
            "AND processor_version=%s AND step LIKE 'city-member:%%'",
            (self.did, TEST_VERSION),
        ).fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT count(*) FROM regional_price").fetchone()[0], 49)

        second, observed, _ = self.run_case(city=rows, process_callback=lambda *_: self.publish())
        self.assertEqual([row[0] for row in observed], [SOURCE_URL])
        self.assertEqual(second["rows"], 99)
        self.assertEqual(self.db.execute("SELECT count(*) FROM regional_price").fetchone()[0], 99)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s "
            "AND processor_version=%s AND step LIKE 'city-member:%%'",
            (self.did, TEST_VERSION),
        ).fetchone()[0], 2)
        self.assertEqual(self.publish(), 99)
        self.assertEqual(self.db.execute("SELECT count(*) FROM regional_price").fetchone()[0], 99)
        self.assertEqual(self.db.execute("SELECT count(*) FROM city_pdf_publication_conflict").fetchone()[0], 0)
        self.assertEqual(sha256(self.data).hexdigest(), self.did)

    def test_existing_changed_child_price_never_gets_current_completion(self):
        child_name, child_bytes = self.entries[0]
        child_id = self.local_archive(self.db, SOURCE_URL, child_bytes, "city-pdf",
                                      filename=child_name)
        native = list(city_reports.parse_city_pdf(child_bytes, DAY))
        self.assertEqual(len(native), 49)
        prior = list(native[0])
        prior[11] = Decimal(1)
        columns = city_reports._BULK_TABLES["regional_price"][0]
        self.db.execute(
            f"INSERT INTO regional_price({columns}) VALUES(" + ",".join(["%s"] * 18) + ")",
            (child_id, *prior),
        )
        result, observed, _ = self.run_case(
            city=[(SOURCE_URL, "city-zip", DAY)],
            process_callback=lambda *_: self.publish(),
        )
        self.assertEqual([row[0] for row in observed], [SOURCE_URL])
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(self.db.execute(
            "SELECT min_price FROM regional_price WHERE document_id=%s AND source_locator=%s",
            (child_id, prior[0]),
        ).fetchone()[0], Decimal(1))
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM published_regional_price WHERE document_id=%s",
            (child_id,),
        ).fetchone()[0], 0)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM city_pdf_publication_conflict WHERE document_id=%s",
            (child_id,),
        ).fetchone()[0], 1)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s "
            "AND processor_version=%s AND step LIKE 'city-member:%%'",
            (self.did, TEST_VERSION),
        ).fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT count(*) FROM regional_price").fetchone()[0], 51)
        self.assertEqual(sha256(child_bytes).hexdigest(), child_id)


if __name__ == "__main__":
    unittest.main()
