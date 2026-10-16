"""A cached OCR retry keeps the old review and never calls a provider."""

import copy
import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from .ocr import OLD_DISAGREEMENT, VERSION, requeue_cached_typed_reviews


FIXTURES = Path(__file__).resolve().parents[2] / "artifacts" / "official-sources"


class TypedRetry(unittest.TestCase):
    def fixture(self, name):
        path = FIXTURES / name
        if not path.exists():
            self.skipTest("Downloaded original fixture unavailable")
        return path.read_bytes()

    def run_retry(self, changed_price=False):
        body = self.fixture("semana-4-marzo-2020.pdf")
        did = hashlib.sha256(body).hexdigest()
        tasks = [
            (f"PDF page {page}", page, f"image-{page}", "review", OLD_DISAGREEMENT)
            for page in (2, 3)
        ]
        cached = []
        for page in (2, 3):
            for reading in (0, 1):
                result = json.loads(self.fixture(f"pork-2020-page{page}-reading{reading}.json"))
                if changed_price and page == 2 and reading == 1:
                    result = copy.deepcopy(result)
                    result["tables"][0][3][1] = "$ 5,287"
                cached.append((page, reading, result))
        db = MagicMock()
        responses = [
            ("fetchall", [(did, "colombia-pork-pdf")]),
            ("fetchall", tasks),
            ("fetchall", cached),
            ("fetchone", (body, "https://porkcolombia.co/semana-4-marzo-2020.pdf")),
        ]

        def execute(sql, params):
            cursor = MagicMock()
            if responses:
                method, value = responses.pop(0)
                getattr(cursor, method).return_value = value
            return cursor

        db.execute.side_effect = execute
        outcome = requeue_cached_typed_reviews(db, limit=1)
        statements = [call.args[0] for call in db.execute.call_args_list]
        self.assertEqual(responses, [])
        self.assertTrue(any("source_ocr_scan" in sql for sql in statements))
        self.assertTrue(all(call.args[1][0] != VERSION for call in db.execute.call_args_list
                            if "source_ocr_scan(document_id,version)" in call.args[0]))
        return outcome, statements

    def test_agreed_original_preserves_both_prior_reviews_then_requeues(self):
        outcome, sql = self.run_retry()
        self.assertEqual(outcome, {"checked": 1, "requeued_documents": 1,
                                   "requeued_tasks": 2})
        self.assertEqual(sum("INSERT INTO source_ocr_review_history" in s for s in sql), 2)
        self.assertEqual(sum("UPDATE source_ocr_task SET status='pending'" in s for s in sql), 2)

    def test_changed_price_keeps_review_and_only_records_policy_decision(self):
        outcome, sql = self.run_retry(changed_price=True)
        self.assertEqual(outcome, {"checked": 1, "requeued_documents": 0,
                                   "requeued_tasks": 0})
        self.assertFalse(any("source_ocr_review_history" in s for s in sql))
        self.assertFalse(any("UPDATE source_ocr_task" in s for s in sql))


if __name__ == "__main__":
    unittest.main()
