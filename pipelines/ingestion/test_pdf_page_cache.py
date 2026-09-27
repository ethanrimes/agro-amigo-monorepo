"""Immutable PDF-page reuse must preserve repair and separate OCR scan versions."""

import unittest
from unittest.mock import MagicMock, patch

from pipelines.ingestion.pdf_sources import VERSION, extract_pages


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class RetainedPages:
    """In-memory fixture for the actual (document_id,page,version) primary key."""

    def __init__(self, existing=()):
        self.pages = {key: ("retained original text", []) for key in existing}
        self.queries = []
        self.inserted = []

    def execute(self, query, params):
        self.queries.append((query, params))
        if query.startswith("SELECT page FROM source_pdf_page"):
            did, version = params
            return Cursor(
                [
                    (page,)
                    for doc, page, ver in self.pages
                    if doc == did and ver == version
                ]
            )
        if query.startswith("INSERT INTO source_pdf_page"):
            did, page, text, tables, version = params
            key = (did, page, version)
            self.pages.setdefault(key, (text, tables.obj))
            self.inserted.append(key)
            return Cursor([])
        if query.startswith("SELECT metadata->>'ingestion_kind'"):
            return Cursor([("inputs-pdf",)])
        raise AssertionError(f"Unexpected query: {query}")


def pages(count=3):
    result = []
    for n in range(1, count + 1):
        page = MagicMock()
        page.extract_text.return_value = f"Native page {n}"
        page.extract_tables.return_value = [[["Product", str(n)]]]
        result.append(page)
    return result


class PDFPageCache(unittest.TestCase):
    def run_pages(self, db, native_pages, did="sha-current"):
        document = MagicMock()
        document.__enter__.return_value.pages = native_pages
        with (
            patch(
                "pipelines.ingestion.pdf_sources.pdfplumber.open", return_value=document
            ),
            patch("pipelines.ingestion.ocr.scan_document") as scan,
        ):
            result = extract_pages(db, b"%PDF fixture", did)
        scan.assert_called_once_with(db, b"%PDF fixture", did, "inputs-pdf")
        for page in native_pages:
            page.close.assert_called_once()
        return result

    def test_exact_document_version_cache_skips_expensive_text_and_tables(self):
        db = RetainedPages([("sha-current", n, VERSION) for n in range(1, 4)])
        before = db.pages.copy()
        native = pages()
        self.assertEqual(self.run_pages(db, native), 3)
        for page in native:
            page.extract_text.assert_not_called()
            page.extract_tables.assert_not_called()
        self.assertEqual(db.pages, before)
        self.assertEqual(db.inserted, [])
        self.assertEqual(db.queries[0][1], ("sha-current", VERSION))
        self.assertNotIn("text_content", db.queries[0][0])
        self.assertNotIn("tables", db.queries[0][0])

    def test_partial_cache_repairs_only_missing_page_and_still_scans_ocr(self):
        db = RetainedPages([("sha-current", n, VERSION) for n in (1, 3)])
        native = pages()
        self.assertEqual(self.run_pages(db, native), 3)
        for n, page in enumerate(native, 1):
            self.assertEqual(page.extract_text.call_count, int(n == 2))
            self.assertEqual(page.extract_tables.call_count, int(n == 2))
        self.assertEqual(db.inserted, [("sha-current", 2, VERSION)])
        self.assertEqual(
            db.pages[("sha-current", 2, VERSION)],
            ("Native page 2", [[["Product", "2"]]]),
        )

    def test_changed_document_sha_extracts_all_pages_without_replacing_old(self):
        db = RetainedPages([("sha-old", n, VERSION) for n in range(1, 4)])
        native = pages()
        self.assertEqual(self.run_pages(db, native, "sha-new"), 3)
        self.assertEqual(len(db.pages), 6)
        for page in native:
            page.extract_text.assert_called_once()
            page.extract_tables.assert_called_once()
        self.assertTrue(all(doc == "sha-new" for doc, _, _ in db.inserted))

    def test_other_extraction_version_is_not_reused_or_overwritten(self):
        db = RetainedPages([("sha-current", n, "older-version") for n in range(1, 4)])
        native = pages()
        self.assertEqual(self.run_pages(db, native), 3)
        self.assertEqual(len(db.pages), 6)
        for page in native:
            page.extract_text.assert_called_once()
            page.extract_tables.assert_called_once()
        self.assertTrue(all(ver == VERSION for _, _, ver in db.inserted))

    def test_empty_native_page_is_valid_cached_result(self):
        db = RetainedPages([("sha-current", 1, VERSION)])
        db.pages[("sha-current", 1, VERSION)] = ("", [])
        native = pages(1)
        self.assertEqual(self.run_pages(db, native), 1)
        native[0].extract_text.assert_not_called()
        self.assertEqual(db.pages[("sha-current", 1, VERSION)], ("", []))

    def test_interrupted_extraction_reuses_finished_page_on_retry(self):
        db = RetainedPages()
        failing = pages()
        failing[1].extract_tables.side_effect = ValueError(
            "interrupted native extraction"
        )
        document = MagicMock()
        document.__enter__.return_value.pages = failing
        with (
            patch(
                "pipelines.ingestion.pdf_sources.pdfplumber.open", return_value=document
            ),
            patch("pipelines.ingestion.ocr.scan_document") as scan,
        ):
            with self.assertRaisesRegex(ValueError, "interrupted native extraction"):
                extract_pages(db, b"%PDF fixture", "sha-current")
            scan.assert_not_called()
        self.assertEqual(list(db.pages), [("sha-current", 1, VERSION)])
        repaired = pages()
        self.assertEqual(self.run_pages(db, repaired), 3)
        repaired[0].extract_text.assert_not_called()
        repaired[0].extract_tables.assert_not_called()
        self.assertEqual(len(db.pages), 3)
        self.assertEqual(db.inserted.count(("sha-current", 1, VERSION)), 1)

    def test_cached_native_pages_do_not_hide_a_new_ocr_scan_version(self):
        class OCRScanPages(RetainedPages):
            def __init__(self, existing=()):
                super().__init__(existing)
                self.versions = {("sha-current", "older-ocr-version")}

            def execute(self, query, params):
                if query.startswith("SELECT 1 FROM source_ocr_scan"):
                    return Cursor([(1,)] if params in self.versions else [])
                if query.startswith("INSERT INTO source_ocr_scan"):
                    self.versions.add(params)
                    return Cursor([])
                return super().execute(query, params)

        db = OCRScanPages([("sha-current", 1, VERSION)])
        native = pages(1)
        document = MagicMock()
        document.__enter__.return_value.pages = native
        with (
            patch(
                "pipelines.ingestion.pdf_sources.pdfplumber.open", return_value=document
            ),
            patch("pipelines.ingestion.ocr.VERSION", "new-ocr-version"),
            patch("pipelines.ingestion.ocr.needs_ocr", return_value=False) as eligible,
        ):
            # Use the real scan_document here: its own version, not the native
            # extraction cache, decides whether this page needs rescanning.
            self.assertEqual(extract_pages(db, b"%PDF fixture", "sha-current"), 1)
            self.assertEqual(extract_pages(db, b"%PDF fixture", "sha-current"), 1)
        self.assertIn(("sha-current", "new-ocr-version"), db.versions)
        native[0].extract_text.assert_called_once()
        native[0].extract_tables.assert_not_called()
        eligible.assert_called_once()


if __name__ == "__main__":
    unittest.main()
