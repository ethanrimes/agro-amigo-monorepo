"""Archive/member OCR happens only after genuine native layout failure."""

import hashlib
import io
import os
import unittest
from unittest.mock import patch

import openpyxl
from openpyxl.drawing.image import Image as WorkbookImage
from PIL import Image, ImageDraw

from . import daily_archives as adapter
from . import ocr
from .test_daily_archives import ArchivePublicationPostgres, bundle, workbook


def image_workbook(native=None):
    book = openpyxl.load_workbook(io.BytesIO(native)) if native else openpyxl.Workbook()
    if not native:
        book.active.title = "Precios en imagen"
        book.active.append(["SIPSA precios mayoristas"])
        book.active.append(["31 de diciembre de 2021"])
        book.active.append(["Bogotá, Corabastos"])
    image = Image.new("RGB", (900, 250), "white")
    draw = ImageDraw.Draw(image)
    draw.text(
        (20, 20), "Producto | Presentacion | Unidades | Minimo | Maximo", fill="black"
    )
    draw.text(
        (20, 90), "Limon tahiti | Bulto | 24 Kilogramo | 60000 | 72000", fill="black"
    )
    png = io.BytesIO()
    image.save(png, format="PNG")
    book.active.add_image(WorkbookImage(io.BytesIO(png.getvalue())), "A8")
    out = io.BytesIO()
    book.save(out)
    book.close()
    return out.getvalue(), png.getvalue()


class ArchiveOcrEligibility(unittest.TestCase):
    def test_headings_and_image_have_real_native_failure_despite_readable_cells(self):
        body, png = image_workbook()
        self.assertEqual(list(ocr.spreadsheet_images(body, failed_only=True)), [])
        self.assertEqual(
            list(
                ocr.spreadsheet_images(
                    body, failed_only=True, normal_extraction_failed=True
                )
            ),
            [("Precios en imagen!image 1,anchor row 8,col 1", png)],
        )
        with self.assertRaises(adapter.NativeLayoutUnavailable):
            adapter.parse_member(body)


@unittest.skipUnless(
    os.environ.get("AGRO_DAILY_ZIP_POSTGRES_TEST") == "1",
    "Explicit isolated TEMP PostgreSQL opt-in",
)
class ArchiveOcrPublication(ArchivePublicationPostgres):
    # Reuse isolated native/storage fixtures, without duplicating inherited tests.
    __unittest_skip__ = False

    def setUp(self):
        super().setUp()
        self.db.execute(
            "CREATE TEMP TABLE source_ocr_scan(document_id text,version text,scanned_at timestamptz default now(),PRIMARY KEY(document_id,version))"
        )
        self.db.execute(
            "CREATE TEMP TABLE source_ocr_task(document_id text,source_locator text,image_id text,source_kind text,source_page integer,status text default 'pending',created_at timestamptz default now(),checked_at timestamptz,error text,PRIMARY KEY(document_id,source_locator))"
        )
        self.enterContext(
            patch.object(
                ocr,
                "transcribe",
                side_effect=AssertionError(
                    "No provider requests allowed in native scan"
                ),
            )
        )

    def test_actual_image_object_archived_and_queued_once_after_native_failure(self):
        body, png = image_workbook()
        data = bundle([("image.xlsx", body)])
        _did, result = self.retain_publish(data)
        self.assertEqual((result[0], len(result[1])), (0, 1))
        self.assertIn(
            "Typed daily ZIP image publication remains unsupported",
            result[1][0]["ocr_status"],
        )
        task = self.db.execute(
            "SELECT document_id,source_locator,image_id,source_kind,status FROM source_ocr_task"
        ).fetchone()
        self.assertEqual(
            task,
            (
                hashlib.sha256(body).hexdigest(),
                "Precios en imagen!image 1,anchor row 8,col 1",
                hashlib.sha256(png).hexdigest(),
                "daily-zip-member",
                "pending",
            ),
        )
        self.assertEqual(
            self.db.execute(
                "SELECT content FROM source_document WHERE id=%s", (task[2],)
            ).fetchone()[0],
            png,
        )
        self.assertEqual(self.retain_publish(data)[1], result)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM source_ocr_task").fetchone(), (1,)
        )
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM regional_price").fetchone(), (0,)
        )

    def test_successful_native_table_with_image_never_scans(self):
        body, _ = image_workbook(workbook())
        with patch.object(
            ocr,
            "scan_document",
            side_effect=AssertionError("Native extraction succeeded"),
        ):
            self.assertEqual(
                self.retain_publish(bundle([("native.xlsx", body)]))[1], (1, [])
            )

    def test_explicit_native_date_conflict_never_scans(self):
        body, _ = image_workbook(workbook())
        self.day = self.day.replace(day=30)
        with patch.object(
            ocr,
            "scan_document",
            side_effect=AssertionError("Do not OCR conflicting native dates"),
        ):
            result = self.retain_publish(bundle([("future.xlsx", body)]))[1]
        self.assertEqual((result[0], len(result[1])), (0, 1))
        self.assertNotIn("ocr_status", result[1][0])

    def test_readable_date_conflict_on_image_only_sheet_never_scans(self):
        body, _ = image_workbook()
        self.day = self.day.replace(day=30)
        with patch.object(
            ocr,
            "scan_document",
            side_effect=AssertionError("Native date overrides no image guesses"),
        ):
            result = self.retain_publish(
                bundle([("image-with-wrong-date.xlsx", body)])
            )[1]
        self.assertEqual((result[0], len(result[1])), (0, 1))
        self.assertNotIn("ocr_status", result[1][0])

    def test_recognized_daily_tab_image_grid_still_queues_after_native_failure(self):
        body, _ = image_workbook()
        book = openpyxl.load_workbook(io.BytesIO(body))
        book.active.title = "Boletín diario"
        buffer = io.BytesIO()
        book.save(buffer)
        book.close()
        result = self.retain_publish(bundle([("boletin.xlsx", buffer.getvalue())]))[1]
        self.assertEqual((result[0], len(result[1])), (0, 1))
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM source_ocr_task").fetchone(), (1,)
        )

    def test_malformed_native_range_is_reviewed_without_ocr(self):
        book = openpyxl.load_workbook(io.BytesIO(workbook()))
        book.active.cell(8, 4, 72000)
        book.active.cell(8, 5, 60000)
        b = io.BytesIO()
        book.save(b)
        book.close()
        body, _ = image_workbook(b.getvalue())
        with patch.object(
            ocr,
            "scan_document",
            side_effect=AssertionError("Native bad numeric range needs review"),
        ):
            result = self.retain_publish(bundle([("malformed.xlsx", body)]))[1]
        self.assertEqual((result[0], len(result[1])), (0, 1))
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM official_source_review").fetchone(),
            (1,),
        )


# Only the four new OCR methods are inherited into the PostgreSQL subclass.
for _name in tuple(ArchivePublicationPostgres.__dict__):
    if _name.startswith("test_") and _name not in ArchiveOcrPublication.__dict__:
        setattr(ArchiveOcrPublication, _name, None)

if __name__ == "__main__":
    unittest.main()
