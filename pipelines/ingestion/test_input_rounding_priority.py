"""Do not discard structured precision merely because a rounded PDF was fetched later."""

import os
import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from . import inputs, pdf_sources, queue_plan, resumable_inputs, worker
from . import test_input_pdf_publication as publication_tests


@unittest.skipUnless(
    os.environ.get("AGRO_INPUT_PDF_PUBLICATION_POSTGRES_TEST") == "1",
    "Explicit TEMP-only PostgreSQL opt-in",
)
class InputRoundingPriority(unittest.TestCase):
    def setUp(self):
        publication_tests.InputPDFPublication.setUp(self)
        self.db.execute(
            "INSERT INTO source_document VALUES('mid','2026-09-02'),('last','2026-09-04')"
        )

    def publish(self, did, kind, price, *, municipality="El Carmen de Viboral"):
        pdf = kind == "pdf"
        series = (
            "dane-inputs-pdf"
            if pdf
            else ("dane-inputs-municipal" if municipality else "dane-inputs")
        )
        loc = (
            "PDF page 8,col 1,y 605.7; " + pdf_sources.INPUT_PDF_VERSION
            if pdf
            else "1.2!row 25836"
        )
        meta = {
            "sheet": "pdf" if pdf else "1.2",
            "category": "Fertilizantes y enmiendas",
            "presentation": "50 kilogramos",
            "department": "Antioquia",
            "municipality": municipality,
            "brand": "",
            "ica": "",
            "parser_version": pdf_sources.INPUT_PDF_VERSION if pdf else "inputs-v1",
        }
        row = worker.record(
            series,
            date(2015, 12, 31),
            "10-20-20",
            municipality or "Antioquia",
            "50 kilogramos",
            Decimal(str(price)),
            loc,
            details=meta,
        )
        with self.db.transaction():
            worker.save_rows(self.db, did, [row])
            inputs.project_inputs(self.db, did)

    def value(self, municipal=True):
        table = "input_municipal_price" if municipal else "input_price"
        return self.db.execute(
            f"SELECT price,document_id,source_locator FROM {table}"
        ).fetchone()

    def watermark(self):
        return self.db.execute(
            "SELECT (retrieved_at AT TIME ZONE 'UTC')::date::text FROM input_revision"
        ).fetchone()[0]

    def test_later_rounded_pdf_keeps_precise_xls_and_does_not_advance_watermark(self):
        self.publish("old", "xlsx", "92416.66666666667")
        self.publish("new", "pdf", "92417")
        self.assertEqual(self.value()[:2], (Decimal("92416.66666666667"), "old"))
        self.assertEqual(self.watermark(), "2026-09-01")
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM historical_price").fetchone()[0], 2
        )

    def test_older_xls_recovers_precision_without_poisoning_next_xls_revision(self):
        self.publish("new", "pdf", "92417")
        self.publish("old", "xlsx", "92416.66666666667")
        self.assertEqual(self.value()[:2], (Decimal("92416.66666666667"), "old"))
        self.assertEqual(self.watermark(), "2026-09-01")
        self.publish("new", "pdf", "92417")
        self.publish("mid", "xlsx", "92500.4")
        self.assertEqual(self.value()[:2], (Decimal("92500.4"), "mid"))
        self.assertEqual(self.watermark(), "2026-09-02")

    def test_equal_value_promotion_updates_structured_provenance(self):
        self.publish("new", "pdf", "100")
        self.publish("old", "xlsx", "100")
        self.assertEqual(self.value(), (100, "old", "1.2!row 25836"))
        self.assertEqual(self.watermark(), "2026-09-01")

    def test_same_format_versions_still_obey_retrieval_chronology(self):
        for kind in ("xlsx", "pdf"):
            with self.subTest(kind=kind):
                self.db.execute(
                    "TRUNCATE historical_price,input_price,input_municipal_price,input_revision"
                )
                self.publish("old", kind, "100")
                self.publish("new", kind, "102")
                self.publish("mid", kind, "101")
                self.assertEqual(self.value()[:2], (102, "new"))
                self.assertEqual(self.watermark(), "2026-09-03")

    def test_material_cross_format_difference_is_not_called_rounding(self):
        self.publish("old", "xlsx", "100.2")
        self.publish("new", "pdf", "105")
        self.assertEqual(self.value()[:2], (105, "new"))
        self.publish("old", "xlsx", "100.2")
        self.assertEqual(self.value()[:2], (105, "new"))
        self.assertEqual(self.watermark(), "2026-09-03")
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM historical_price").fetchone()[0], 2
        )

    def test_noninteger_pdf_has_no_whole_peso_equivalence(self):
        self.publish("old", "xlsx", "100.25")
        self.publish("new", "pdf", "100.3")
        self.assertEqual(self.value()[:2], (Decimal("100.3"), "new"))

    def test_equal_later_xls_watermark_survives_rounded_pdf(self):
        self.publish("old", "xlsx", "100.25")
        self.publish("mid", "xlsx", "100.25")
        self.publish("new", "pdf", "100")
        self.assertEqual(self.value()[:2], (Decimal("100.25"), "old"))
        self.assertEqual(self.watermark(), "2026-09-02")

    def test_unattributed_newer_watermark_cannot_be_reset_by_old_precision(self):
        self.publish("new", "pdf", "100")
        self.db.execute("UPDATE input_revision SET retrieved_at='2026-09-04'")
        self.publish("old", "xlsx", "100.25")
        self.assertEqual(self.value()[:2], (100, "new"))
        self.assertEqual(self.watermark(), "2026-09-04")

    def test_departmental_exact_identity_uses_same_rounding_policy(self):
        self.publish("new", "pdf", "100", municipality="")
        self.publish("old", "xlsx", "100.49", municipality="")
        self.assertEqual(self.value(False)[:2], (Decimal("100.49"), "old"))

    def test_completed_xls_requeues_and_new_version_resumes_durable_groups(self):
        self.db.execute("""ALTER TABLE ingestion_asset ADD COLUMN url text,
          ADD COLUMN observed_on date,ADD COLUMN checked_at timestamptz,
          ADD COLUMN discovered_at timestamptz DEFAULT now();
          CREATE TEMP TABLE source_ocr_task(document_id text,source_kind text,
          status text,checked_at timestamptz,error text)""")
        kind = "inputs-municipal"
        old_version = worker.PARSER_VERSIONS[kind]
        current = worker.parser_version(kind)
        self.assertNotEqual(current, old_version)
        self.db.execute(
            "INSERT INTO ingestion_asset(document_id,kind,processor_version,status,url,observed_on,checked_at) VALUES('old',%s,%s,'complete','https://official.example/input.xlsx','2015-12-31',now())",
            (kind, old_version),
        )
        self.assertIn(
            ("https://official.example/input.xlsx", kind, date(2015, 12, 31)),
            queue_plan.backfill_candidates(self.db, 5),
        )
        xls, pdf = [], []
        for n, price in enumerate((Decimal("92416.66666666667"), Decimal("100.25"))):
            name = f"Producto {n}"
            meta = {
                "sheet": "1.2",
                "category": "Fertilizantes",
                "presentation": "50 kilogramos",
                "department": "Antioquia",
                "municipality": "El Carmen de Viboral",
                "brand": "",
                "ica": "",
            }
            xls.append(
                worker.record(
                    "dane-inputs-municipal",
                    date(2015, 12, 31),
                    name,
                    meta["municipality"],
                    "50 kilogramos",
                    price,
                    f"1.2!row {25836 + n}",
                    details=meta,
                )
            )
            pdf.append(
                worker.record(
                    "dane-inputs-pdf",
                    date(2015, 12, 31),
                    name,
                    meta["municipality"],
                    "50 kilogramos",
                    price.quantize(Decimal(1)),
                    f"PDF page 8,col 1,y {605 + n}; {pdf_sources.INPUT_PDF_VERSION}",
                    details={
                        **meta,
                        "sheet": "pdf",
                        "parser_version": pdf_sources.INPUT_PDF_VERSION,
                    },
                )
            )
        with self.db.transaction():
            worker.save_rows(self.db, "new", pdf)
            inputs.project_inputs(self.db, "new")
        with self.db.transaction():
            worker.save_rows(self.db, "old", xls)
        for step, count in (
            ("validated", 2),
            ("native", 2),
            ("published:2015-12-31", 0),
            ("references", 0),
        ):
            self.db.execute(
                "INSERT INTO ingestion_checkpoint VALUES('old',%s,%s,%s)",
                (old_version, step, count),
            )
        clock = [0]
        normal_project = inputs.project_inputs

        def stop_after_first(*args, **kwargs):
            result = normal_project(*args, **kwargs)
            clock[0] = 20
            return result

        with (
            patch.object(inputs, "parse_inputs", side_effect=lambda _: iter(xls)),
            patch(
                "pipelines.ingestion.input_references.extract_reference_rows",
                return_value=0,
            ),
            patch.object(resumable_inputs, "PUBLICATION_BATCH_SIZE", 1),
        ):
            with (
                patch.object(
                    resumable_inputs.time, "monotonic", side_effect=lambda: clock[0]
                ),
                patch.object(inputs, "project_inputs", side_effect=stop_after_first),
                self.assertRaises(resumable_inputs.WorkDeferred),
            ):
                resumable_inputs.publish(
                    self.db,
                    b"retained",
                    "old",
                    kind,
                    date(2015, 12, 31),
                    deadline=10,
                )
            steps = dict(
                self.db.execute(
                    "SELECT step,records FROM ingestion_checkpoint WHERE document_id='old' AND processor_version=%s",
                    (current,),
                ).fetchall()
            )
            self.assertEqual(sum(s.startswith("published-group-v1:") for s in steps), 1)
            self.assertNotIn("published:2015-12-31", steps)
            with patch.object(
                inputs, "project_inputs", wraps=normal_project
            ) as project:
                self.assertEqual(
                    resumable_inputs.publish(
                        self.db, b"retained", "old", kind, date(2015, 12, 31)
                    ),
                    (2, 0),
                )
                self.assertEqual(project.call_count, 1)
        self.assertEqual(
            self.db.execute(
                "SELECT price,document_id FROM input_municipal_price ORDER BY name"
            ).fetchall(),
            [(Decimal("92416.66666666667"), "old"), (Decimal("100.25"), "old")],
        )
        with self.db.transaction():
            inputs.project_inputs(self.db, "new")
        self.assertEqual(
            self.db.execute(
                "SELECT price,document_id FROM input_municipal_price ORDER BY name"
            ).fetchall(),
            [(Decimal("92416.66666666667"), "old"), (Decimal("100.25"), "old")],
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM historical_price").fetchone()[0], 4
        )


class InputPublicationVersion(unittest.TestCase):
    def test_every_structured_price_family_includes_publication_revision(self):
        for kind in ("inputs", "inputs-municipal", "inputs-annex", "inputs-reference"):
            self.assertEqual(
                worker.parser_version(kind),
                worker.PARSER_VERSIONS[kind] + ":" + inputs.PUBLICATION_VERSION,
            )
        self.assertEqual(
            worker.parser_version("inputs-pdf"), pdf_sources.INPUT_PDF_VERSION
        )


if __name__ == "__main__":
    unittest.main()
