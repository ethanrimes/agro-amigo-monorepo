"""Retain contradictory printed continuation labels without guessing units."""

import json
import os
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pdfplumber

from . import inputs, pdf_sources, worker
from . import test_input_pdf_publication as publication_tests

FIXTURES = Path(
    os.environ.get(
        "AGRO_INPUT_HEADER_FIXTURES",
        "artifacts/source-verification-2026-09-28/inputs-milk/residual-context",
    )
)
PERIOD = date(2019, 1, 31)


def context(name="Tripen LA", unit="6 M.U.I.", page=46, column=2, table="3"):
    return {
        "identity": (name, unit),
        "heading": f"{name}, {unit}",
        "page": page,
        "column": column,
        "table": (table, "Antibióticos", PERIOD),
    }


class ContinuationBoundaries(unittest.TestCase):
    def test_contradictory_unit_and_product_are_reviewed_not_rewritten(self):
        prior = context()
        current = context(unit="3 M.U.I.", page=47, column=1)
        for entry in [current, context(name="Other product", page=47, column=1)]:
            result = pdf_sources._input_continuation_review(entry, prior)
            self.assertIn("conflicts", result["reason"])
            self.assertEqual(result["preceding_heading"], "Tripen LA, 6 M.U.I.")
        self.assertEqual(current["identity"], ("Tripen LA", "3 M.U.I."))

    def test_same_identity_continues_and_reviews_follow_the_ambiguous_block(self):
        prior = context()
        current = context(page=47, column=1)
        self.assertIsNone(pdf_sources._input_continuation_review(current, prior))
        prior["continuation_review"] = {"reason": "previous contradiction"}
        self.assertEqual(
            pdf_sources._input_continuation_review(current, prior),
            prior["continuation_review"],
        )

    def test_other_tables_periods_and_nonadjacent_pages_are_not_identity_evidence(self):
        prior = context()
        for entry in [
            context(unit="3 M.U.I.", table="4"),
            context(unit="3 M.U.I.", page=48),
            context(unit="3 M.U.I.", column=1),
        ]:
            self.assertIsNone(pdf_sources._input_continuation_review(entry, prior))
        current = context(unit="3 M.U.I.", page=47, column=1)
        current["table"] = ("3", "Antibióticos", date(2019, 2, 28))
        self.assertIsNone(pdf_sources._input_continuation_review(current, prior))
        self.assertIsNone(pdf_sources._input_continuation_review(current, None))


@unittest.skipUnless((FIXTURES / "jan2019.pdf").exists(), "Retained original required")
class ActualContinuationOriginal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = list(
            pdf_sources.parse_input_pdf((FIXTURES / "jan2019.pdf").read_bytes(), PERIOD)
        )
        cls.old = json.loads((FIXTURES / "jan2019-v9-rows.json").read_text())

    def test_all_literal_cells_preserved_and_exact_fifteen_rows_reviewed(self):
        self.assertEqual(len(self.rows), len(self.old))
        self.assertEqual(len(self.rows), 14458)
        changed = []
        for old, new in zip(self.old, self.rows):
            self.assertEqual(old[0].split(";")[0], new[0].split(";")[0])
            self.assertEqual(tuple(old[3:8]), new[3:8])
            self.assertEqual(old[2], str(new[2]))
            if new[-1]["quality_issue"]:
                changed.append(new)
                self.assertEqual(new[1], "dane-inputs-pdf-unresolved")
                self.assertEqual(new[-1]["printed_heading"], old[-1]["printed_heading"])
                self.assertIn(
                    "continuación", " ".join(new[-1]["literal_heading_lines"])
                )
            else:
                self.assertEqual(new[1], old[1])
        self.assertEqual(len(changed), 15)
        tripen = [r for r in changed if r[-1]["page"] == 47]
        negasunt = [r for r in changed if r[-1]["page"] == 55]
        self.assertEqual(len(tripen), 12)
        self.assertEqual(len(negasunt), 3)
        self.assertEqual({r[5] for r in tripen}, {"3 M.U.I."})
        self.assertEqual({r[5] for r in negasunt}, {"300 centímetros cúbicos"})
        self.assertEqual(
            [r[6] for r in tripen],
            [
                16033,
                18767,
                20500,
                21100,
                15437,
                21725,
                20000,
                16871,
                17000,
                22500,
                16030,
                20667,
            ],
        )
        self.assertEqual([r[6] for r in negasunt], [17725, 18386, 18333])
        self.assertTrue(
            all(
                "6 M.U.I." in r[-1]["continuation_review"]["preceding_heading"]
                for r in tripen
            )
        )
        self.assertTrue(
            all(
                "430 centímetros cúbicos"
                in r[-1]["continuation_review"]["preceding_heading"]
                for r in negasunt
            )
        )


@unittest.skipUnless(
    os.environ.get("AGRO_INPUT_PDF_PUBLICATION_POSTGRES_TEST") == "1"
    and (FIXTURES / "jan2019-conflict-publication.json").exists(),
    "Real TEMP PostgreSQL and retained original evidence required",
)
class ContinuationPublication(unittest.TestCase):
    setUp = publication_tests.InputPDFPublication.setUp

    def test_successful_revision_hides_five_old_pdf_rows_keeps_all_xls_and_raw(self):
        proof = json.loads((FIXTURES / "jan2019-conflict-publication.json").read_text())
        raw = json.loads((FIXTURES / "jan2019-v9-rows.json").read_text())
        affected = {r["locator"] for r in proof["published"]}
        affected_keys = {
            (r["key"], r["canonical"]["department"], r["canonical"]["municipality"])
            for r in proof["published"]
        }
        selected = [
            r
            for r in raw
            if (
                inputs.identity(r[3], r[-1]),
                r[-1]["department"],
                r[-1]["municipality"],
            )
            in affected_keys
        ]
        self.assertEqual(len(selected), 25)
        old = []
        new = []
        structured = []
        for entry in selected:
            r = list(entry)
            r[2] = PERIOD
            old.append(tuple(r))
            r = list(r)
            r[0] = r[0].replace("inputs-pdf-v9", "inputs-pdf-v10")
            r[-1] = {**r[-1], "parser_version": "inputs-pdf-v10"}
            if entry[0] in affected:
                r[1] = "dane-inputs-pdf-unresolved"
                r[-1]["quality_issue"] = (
                    "Printed continuation conflicts with preceding block"
                )
            new.append(tuple(r))
        for item in proof["published"]:
            for field in ["canonical", "previous_block_identity_evidence_only"]:
                row = item[field]
                if (
                    row["document_id"]
                    == proof["published"][0]["canonical"]["document_id"]
                ):
                    model = next(r for r in selected if r[0] == item["locator"])
                    meta = {**model[-1], "presentation": row["presentation"]}
                    meta.pop("parser_version", None)
                    structured.append(
                        worker.record(
                            "dane-inputs-municipal",
                            PERIOD,
                            model[3],
                            row["municipality"],
                            row["presentation"],
                            row["price"],
                            row["source_locator"],
                            details=meta,
                        )
                    )
        self.assertEqual(len(structured), 25)
        self.db.execute(
            "UPDATE source_document SET retrieved_at='2026-08-01Z' WHERE id='new'"
        )
        with self.db.transaction():
            worker.save_rows(self.db, "new", structured)
            inputs.project_inputs(self.db, "new")
        with (
            patch.object(pdf_sources, "INPUT_PDF_VERSION", "inputs-pdf-v9"),
            self.db.transaction(),
        ):
            worker.save_rows(self.db, "old", old)
            inputs.project_pdf_inputs(self.db, "old")
        self.assertEqual(
            self.db.execute(
                "SELECT count(*) FROM published_input_municipal_price WHERE document_id='old'"
            ).fetchone()[0],
            5,
        )
        before = self.db.execute(
            "SELECT * FROM historical_price ORDER BY document_id,source_locator"
        ).fetchall()
        xls = self.db.execute(
            "SELECT * FROM published_input_municipal_price WHERE document_id='new' ORDER BY id,department,municipality"
        ).fetchall()
        self.assertEqual(len(xls), 25)
        with (
            self.assertRaisesRegex(RuntimeError, "rollback"),
            patch.object(pdf_sources, "INPUT_PDF_VERSION", "inputs-pdf-v10"),
            self.db.transaction(),
        ):
            worker.save_rows(self.db, "old", new)
            inputs.project_pdf_inputs(self.db, "old")
            raise RuntimeError("rollback")
        self.assertEqual(
            self.db.execute(
                "SELECT count(*) FROM published_input_municipal_price WHERE document_id='old'"
            ).fetchone()[0],
            5,
        )
        for _ in range(2):
            with (
                patch.object(pdf_sources, "INPUT_PDF_VERSION", "inputs-pdf-v10"),
                self.db.transaction(),
            ):
                worker.save_rows(self.db, "old", new)
                inputs.project_pdf_inputs(self.db, "old")
        # Encoded URL aliases share the same immutable DID; alias status/version
        # order cannot revive the older rows after the successful v10 checkpoint.
        self.db.execute(
            "INSERT INTO ingestion_asset VALUES('old','inputs-pdf','inputs-pdf-v9','complete'),('old','context-pdf','source-v1','processed')"
        )
        with (
            patch.object(pdf_sources, "INPUT_PDF_VERSION", "inputs-pdf-v9"),
            self.db.transaction(),
        ):
            worker.save_rows(self.db, "old", old)
            inputs.project_pdf_inputs(self.db, "old")
        self.assertEqual(
            self.db.execute(
                "SELECT count(*) FROM published_input_municipal_price WHERE document_id='old'"
            ).fetchone()[0],
            0,
        )
        self.assertEqual(
            self.db.execute(
                "SELECT count(*) FROM input_municipal_price WHERE document_id='old'"
            ).fetchone()[0],
            5,
        )
        self.assertEqual(
            self.db.execute(
                "SELECT * FROM published_input_municipal_price WHERE document_id='new' ORDER BY id,department,municipality"
            ).fetchall(),
            xls,
        )
        after = self.db.execute(
            "SELECT * FROM historical_price ORDER BY document_id,source_locator"
        ).fetchall()
        self.assertTrue(all(row in after for row in before))
        self.assertEqual(len(after), len(before) + 25)
        self.assertEqual(
            self.db.execute(
                "SELECT records FROM ingestion_checkpoint WHERE document_id='old' AND processor_version='inputs-pdf-v10'"
            ).fetchone()[0],
            10,
        )


@unittest.skipUnless((FIXTURES / "aug2012.pdf").exists(), "Retained original required")
class HistoricalContinuationOriginals(unittest.TestCase):
    def native_pages(self, path, pages, day):
        with pdfplumber.open(path) as pdf:
            wrapper = MagicMock()
            wrapper.__enter__.return_value.pages = [pdf.pages[p - 1] for p in pages]
            with patch.object(pdfplumber, "open", return_value=wrapper):
                return list(pdf_sources.parse_input_pdf(b"", day))

    def test_august_2012_conflicting_name_and_mixed_headings_keep_literal_cells(self):
        rows = self.native_pages(FIXTURES / "aug2012.pdf", [15, 56], date(2012, 8, 31))
        reviewed = [r for r in rows if r[-1].get("continuation_review")]
        self.assertEqual(len(reviewed), 23)
        baxin = [r for r in reviewed if r[3] == "Baxin"]
        self.assertEqual(
            [(r[4], r[5], r[6]) for r in baxin],
            [
                ("Santander de Quilichao", "20 centímetros cúbicos", 12800),
                ("Tuluá", "20 centímetros cúbicos", 10935),
            ],
        )
        score = [r for r in reviewed if r[3].startswith("Score")]
        self.assertEqual(len(score), 21)
        self.assertEqual(
            [r[6] for r in score],
            [
                122450,
                135000,
                131400,
                115000,
                128225,
                122667,
                115900,
                115500,
                121100,
                116143,
                128500,
                118000,
                130100,
                140575,
                156600,
                138500,
                119500,
                130000,
                126400,
                117500,
                115000,
            ],
        )
        self.assertTrue(
            all(
                "250 centímetros cúbicos" in r[-1]["printed_heading"]
                and "1 litro" in r[-1]["printed_heading"]
                for r in score
            )
        )

    def test_february_2016_native_i_l_name_disagreement_is_not_silently_aliased(self):
        path = Path(
            "artifacts/extraction-robustness-2026-09-27/inputs-pdf/Bol_Insumos_feb_2016.pdf"
        )
        if not path.exists():
            self.skipTest("Retained February 2016 original required")
        rows = self.native_pages(path, [54], date(2016, 2, 29))
        reviewed = [r for r in rows if r[-1].get("continuation_review")]
        self.assertEqual(len(reviewed), 7)
        self.assertEqual({r[3] for r in reviewed}, {"Potenzol 900 SI"})
        self.assertTrue(
            all(
                r[-1]["continuation_review"]["preceding_heading"]
                == "Potenzol 900 Sl, 1 litro"
                for r in reviewed
            )
        )
        self.assertEqual(
            [r[6] for r in reviewed], [12667, 12517, 11410, 12094, 11043, 12250, 11688]
        )
