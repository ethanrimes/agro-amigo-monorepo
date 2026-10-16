"""Interrupted page extraction resumes immutable cached pages without publishing partial prices."""
from contextlib import nullcontext
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from . import pdf_sources, worker
from .resumable_inputs import WorkDeferred


class PageCache:
    def __init__(self):
        self.pages = set()

    def execute(self, statement, params):
        if statement.startswith("SELECT page"):
            return SimpleNamespace(fetchall=lambda: [(page,) for page in self.pages])
        if statement.startswith("INSERT INTO source_pdf_page"):
            self.pages.add(params[1])
        if statement.startswith("SELECT metadata"):
            return SimpleNamespace(fetchone=lambda: ("context-pdf",))


class PDFBudgetTests(unittest.TestCase):
    def setUp(self):
        token = worker.RUN_DEADLINE.set(1)
        self.addCleanup(worker.RUN_DEADLINE.reset, token)

    def test_cached_pages_survive_budget_yield_and_are_not_extracted_again(self):
        pages = [SimpleNamespace(extract_text=Mock(return_value="native"), extract_tables=Mock(return_value=[]), close=Mock()) for _ in range(2)]
        db = PageCache()
        with patch.object(pdf_sources.pdfplumber, "open", return_value=nullcontext(SimpleNamespace(pages=pages))), patch.object(pdf_sources.time, "monotonic", side_effect=[0,2]), patch("pipelines.ingestion.ocr.scan_document") as scan:
            with self.assertRaises(WorkDeferred):
                pdf_sources.extract_pages(db,b"original","sha")
            scan.assert_not_called()
        self.assertEqual(db.pages,{1})
        with patch.object(pdf_sources.pdfplumber, "open", return_value=nullcontext(SimpleNamespace(pages=pages))), patch.object(pdf_sources.time, "monotonic", return_value=0), patch("pipelines.ingestion.ocr.scan_document") as scan:
            self.assertEqual(pdf_sources.extract_pages(db,b"original","sha"),2)
            scan.assert_called_once()
        self.assertEqual(db.pages,{1,2})
        for page in pages:
            page.extract_text.assert_called_once(); page.extract_tables.assert_called_once()

    def test_native_input_price_validation_stops_before_an_unbudgeted_page(self):
        page = SimpleNamespace(extract_text=Mock(return_value="No price grid"),close=Mock())
        with patch.object(pdf_sources.pdfplumber,"open",return_value=nullcontext(SimpleNamespace(pages=[page]))), patch.object(pdf_sources.time,"monotonic",return_value=2):
            with self.assertRaises(WorkDeferred):
                list(pdf_sources.parse_input_pdf(b"original",SimpleNamespace(year=2020,month=1)))
        page.extract_text.assert_not_called()
