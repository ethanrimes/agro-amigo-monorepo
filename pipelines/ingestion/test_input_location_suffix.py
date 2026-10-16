"""Exact April 2016 publisher continuation suffix and immutable publication repair."""

import hashlib
import json
import os
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from . import inputs, pdf_sources, worker
from .special_prices import DEPARTMENTS
from . import test_input_pdf_publication as publication_tests

FIXTURE = Path(__file__).parent / "testdata/6cba3d6b39f1-Bol_Insumos_abr_2016.pdf"
ORACLE = Path(__file__).parent / "testdata/6cba3d6b39f1-input-continuacion-oracle.json"
DID = "6cba3d6b39f171d2ae0f6e13b8afb7ab468e6dc4d2d807febc1f2a1c2731b2fc"
OLD = "PDF page 72,col 1,y 163.3; inputs-pdf-v13"
NEW = "PDF page 72,col 1,y 163.3; inputs-pdf-v14"
PERIOD = date(2016, 4, 30)


class ActualContinuationSuffixOriginal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.oracle = json.loads(ORACLE.read_text())
        body = FIXTURE.read_bytes()
        assert hashlib.sha256(body).hexdigest() == cls.oracle["sha256"] == DID
        cls.rows = list(pdf_sources.parse_input_pdf(body, PERIOD))

    def test_only_the_printed_suffix_is_removed_after_department_binding(self):
        self.assertEqual(len(self.rows), 9179)
        self.assertEqual({r[-1]["department"] for r in self.rows} - set(DEPARTMENTS) - {"Bogotá, D.C."}, set())
        corrected = [r for r in self.rows if r[0] == NEW]
        self.assertEqual(len(corrected), 1)
        row = corrected[0]
        expected = self.oracle["expected"]
        self.assertEqual(row[1], "dane-inputs-pdf")
        self.assertEqual(row[2], PERIOD)
        self.assertEqual(row[3:8], (expected["product_name"], expected["municipality"], expected["presentation"], expected["price_cop"], expected["change_percent"]))
        self.assertEqual((row[-1]["municipality"], row[-1]["department"]), (expected["municipality"], expected["department"]))
        self.assertEqual(row[-1]["printed_location_lines"], [self.oracle["printed_market"]])
        self.assertEqual(row[-1]["printed_location_suffix"], "(continuación)")
        self.assertEqual([r for r in self.rows if r[-1].get("printed_location_suffix")], corrected)
        for cell in self.oracle["independent_adjacent_cells"]:
            self.assertEqual(
                len([r for r in self.rows if r[-1]["page"] == 72
                     and r[3] == cell["product_name"] and r[5] == cell["presentation"]
                     and r[4] == cell["municipality"] and r[-1]["department"] == cell["department"]
                     and r[6] == cell["price_cop"]]),
                1, cell,
            )

    def test_only_terminal_continuation_after_a_valid_department_is_normalized(self):
        self.assertEqual(pdf_sources._input_pdf_place("Villavicencio (Meta)(continuación)"), ("Villavicencio", "Meta", True))
        self.assertEqual(pdf_sources._input_pdf_place("Villa de San Diego de Ubaté (Cundinamarca)"), ("Villa de San Diego de Ubaté", "Cundinamarca", False))
        self.assertEqual(pdf_sources._input_pdf_place("Bogotá, D. C."), ("Bogotá, D.C.", "Bogotá, D.C.", False))
        for invalid in ("Villavicencio (continuación)", "Villavicencio (Meta)(other)",
                        "Villavicencio (Unknown)", "Villavicencio (Meta)(continuación) extra"):
            self.assertIsNone(pdf_sources._input_pdf_place(invalid), invalid)


@unittest.skipUnless(os.environ.get("AGRO_INPUT_PDF_PUBLICATION_POSTGRES_TEST") == "1", "Explicit TEMP-only PostgreSQL opt-in")
class ContinuationSuffixPublication(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        body = FIXTURE.read_bytes()
        assert hashlib.sha256(body).hexdigest() == DID
        cls.corrected = next(r for r in pdf_sources.parse_input_pdf(body, PERIOD) if r[0] == NEW)

    def setUp(self):
        publication_tests.InputPDFPublication.setUp(self)
        self.db.execute("""CREATE TEMP TABLE official_source_review(
            document_id text,source_locator text,parser_version text,record jsonb,reason text,
            PRIMARY KEY(document_id,source_locator,parser_version))""")
        self.db.execute("INSERT INTO source_document VALUES(%s,'2026-09-01T00:00:00Z'),('annex','2026-09-03T00:00:00Z')", (DID,))

    def old_row(self):
        row = self.corrected
        meta = {**row[-1], "parser_version": "inputs-pdf-v13", "department": "continuación", "municipality": "Villavicencio (Meta)"}
        meta.pop("printed_location_suffix", None)
        return (OLD, row[1], row[2], row[3], "Villavicencio (Meta)", row[5], row[6], row[7], meta)

    def publish(self, version, rows):
        with publication_tests.synthetic_pdf_publication_version(version), self.db.transaction():
            worker.save_rows(self.db, DID, rows)
            inputs.project_pdf_inputs(self.db, DID)

    def test_v14_review_and_checkpoint_atomically_withdraw_bad_identity_without_deletion(self):
        self.publish("inputs-pdf-v13", [self.old_row()])
        self.assertEqual(self.db.execute("SELECT count(*) FROM published_input_municipal_price WHERE department='continuación'").fetchone()[0], 1)
        # The independently archived structured row has the same date/product,
        # proper geography, and the publisher's higher-precision price.
        annex = worker.record("dane-inputs-municipal", PERIOD, "Levamisol 15%", "Villavicencio", "500 centímetros cúbicos", 21333.333333333332, "2.2!row 36882", details={"sheet": "2.2", "category": "Antibióticos, antimicóticos y antiparasitarios", "department": "Meta", "municipality": "Villavicencio", "presentation": "500 centímetros cúbicos", "brand": "", "ica": ""})
        with self.db.transaction():
            worker.save_rows(self.db, "annex", [annex])
            inputs.project_inputs(self.db, "annex")
        baseline = self.db.execute("SELECT price,document_id,source_locator FROM published_input_municipal_price WHERE department='Meta' AND municipality='Villavicencio'").fetchall()
        self.assertEqual(len(baseline), 1)
        self.assertEqual(baseline[0][1:], ("annex", "2.2!row 36882"))
        with self.assertRaisesRegex(RuntimeError, "rollback"), self.db.transaction():
            worker.save_rows(self.db, DID, [self.corrected])
            inputs.project_pdf_inputs(self.db, DID)
            raise RuntimeError("rollback")
        self.assertEqual(self.db.execute("SELECT count(*) FROM official_source_review").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT count(*) FROM published_input_municipal_price WHERE department='continuación'").fetchone()[0], 1)
        self.publish("inputs-pdf-v14", [self.corrected])
        self.assertEqual(self.db.execute("SELECT count(*) FROM published_input_municipal_price WHERE department='continuación'").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT count(*) FROM input_municipal_price WHERE department='continuación' AND source_locator=%s", (OLD,)).fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT count(*) FROM historical_price WHERE document_id=%s AND source_locator=%s", (DID, OLD)).fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT count(*) FROM historical_price WHERE document_id=%s AND source_locator=%s", (DID, NEW)).fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s AND processor_version='inputs-pdf-v14' AND step='inputs-pdf:published'", (DID,)).fetchone()[0], 1)
        review = self.db.execute("SELECT source_locator,parser_version,record,reason FROM official_source_review WHERE document_id=%s", (DID,)).fetchone()
        self.assertEqual(review[:2], (OLD, "inputs-pdf-v14"))
        self.assertEqual(review[2]["original"]["details"]["department"], "continuación")
        self.assertEqual(review[2]["corrected_department"], "Meta")
        self.assertIn("terminal (continuación)", review[3])
        self.assertEqual(self.db.execute("SELECT price,document_id,source_locator FROM published_input_municipal_price WHERE department='Meta' AND municipality='Villavicencio'").fetchall(), baseline)
        self.publish("inputs-pdf-v13", [self.old_row()])
        self.assertEqual(self.db.execute("SELECT count(*) FROM published_input_municipal_price WHERE department='continuación'").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT count(*) FROM official_source_review").fetchone()[0], 1)
