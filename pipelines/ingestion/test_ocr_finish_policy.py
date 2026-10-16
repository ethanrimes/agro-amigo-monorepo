"""Provider finish labels remain bounded; no partial transcription is evidence."""

from datetime import datetime, timedelta, timezone
import json
import unittest
from unittest.mock import MagicMock, patch

from . import ocr
from .ocr_finish_policy import OUTCOME_CODES, finish_code, missing_reading_state


NOW = datetime(2026, 10, 7, 12, tzinfo=timezone.utc)
SECRET = "secret-key-and-partial-source-text"


def response(body, *, status=200, ok=True):
    r = MagicMock(status_code=status, ok=ok)
    r.json.return_value = body
    return r


class FinishPolicyUnit(unittest.TestCase):
    def test_bounded_finish_codes_discard_provider_payload(self):
        cases = [
            ({"candidates": [{"finishReason": "STOP"}]}, "STOP"),
            ({"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": SECRET}]}}]}, "MAX_TOKENS"),
            ({"candidates": [{"finishReason": "SAFETY"}]}, "SAFETY"),
            ({"candidates": [{"finishReason": "RECITATION"}]}, "RECITATION"),
            ({"candidates": [{"finishReason": SECRET}]}, "OTHER_FINISH"),
            ({"promptFeedback": {"blockReason": "SAFETY", "other": SECRET}}, "SAFETY"),
            ({"promptFeedback": {"blockReason": "SAFETY"}, "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": SECRET}]}}]}, "SAFETY"),
            ({"promptFeedback": {"blockReason": SECRET}}, "NO_CANDIDATE"),
            ([], "MALFORMED_RESPONSE"),
        ]
        for body, expected in cases:
            with self.subTest(expected=expected):
                code = finish_code(body)
                self.assertEqual(code, expected)
                self.assertNotIn(SECRET, code)

    def test_one_retry_after_24_hours_and_ceiling_survives_day_reset(self):
        first = (1, NOW - timedelta(days=2), "MAX_TOKENS")
        self.assertEqual(missing_reading_state([first], NOW), "RETRY")
        self.assertEqual(missing_reading_state([first], first[1] + timedelta(hours=23, minutes=59)), "WAIT")
        # Neither a second truncated output nor a 429 may create another retry.
        for later in ("MAX_TOKENS", "HTTP_429", "NETWORK_ERROR"):
            self.assertEqual(
                missing_reading_state([first, (2, NOW - timedelta(days=1), later)], NOW),
                "REVIEW",
            )
        self.assertEqual(missing_reading_state([(1, NOW, None)], NOW), "REVIEW")
        self.assertEqual(missing_reading_state([(1, NOW, "STOP_VALID")], NOW), "REVIEW")
        self.assertEqual(missing_reading_state([(1, NOW, "HTTP_429")], NOW), "NORMAL")
        for terminal in ("SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "OTHER_FINISH", "NO_CANDIDATE", "MALFORMED_RESPONSE", "STOP_BAD_JSON", "STOP_BAD_SCHEMA", "HTTP_ERROR"):
            self.assertEqual(missing_reading_state([(1, NOW, terminal)], NOW), "REVIEW")
            self.assertEqual(missing_reading_state([(1, NOW, terminal), (2, NOW, "MAX_TOKENS")], NOW + timedelta(days=2)), "REVIEW")

    def test_transcribe_rejects_partial_max_tokens_and_sanitizes_reason(self):
        body = {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": SECRET}]}}]}
        with patch.object(ocr.requests, "post", return_value=response(body)):
            with self.assertRaises(ocr.OCRProviderOutcome) as caught:
                ocr.transcribe(b"png", key=SECRET)
        self.assertEqual(caught.exception.code, "MAX_TOKENS")
        self.assertNotIn(SECRET, str(caught.exception))

    def test_explicit_safety_block_overrides_stop_candidate(self):
        body = {"promptFeedback": {"blockReason": "SAFETY"},
                "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps({"text": "x", "tables": [], "review_notes": []})}]}}]}
        with patch.object(ocr.requests, "post", return_value=response(body)):
            with self.assertRaises(ocr.OCRProviderOutcome) as caught:
                ocr.transcribe(b"png", key=SECRET)
        self.assertEqual(caught.exception.code, "SAFETY")

    def test_stop_schema_validates_before_valid_outcome_is_possible(self):
        invalid = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps({"text": "x", "tables": [[[42]]], "review_notes": []})}]}}]}
        with patch.object(ocr.requests, "post", return_value=response(invalid)):
            with self.assertRaises(ocr.OCRProviderOutcome) as caught:
                ocr.transcribe(b"png", key=SECRET)
        self.assertEqual(caught.exception.code, "STOP_BAD_SCHEMA")
        self.assertNotIn(SECRET, str(caught.exception))
        malformed_content = {"candidates": [{"finishReason": "STOP", "content": None}]}
        with patch.object(ocr.requests, "post", return_value=response(malformed_content)):
            with self.assertRaises(ocr.OCRProviderOutcome) as caught:
                ocr.transcribe(b"png", key=SECRET)
        self.assertEqual(caught.exception.code, "STOP_BAD_SCHEMA")

    def test_429_deferred_with_sanitized_code_and_no_key_in_url(self):
        with patch.object(ocr.requests, "post", return_value=response({}, status=429, ok=False)) as post:
            with self.assertRaises(ocr.OCRDeferred) as caught:
                ocr.transcribe(b"png", key=SECRET)
        self.assertEqual(caught.exception.outcome_code, "HTTP_429")
        self.assertNotIn(SECRET, str(caught.exception))
        self.assertNotIn(SECRET, post.call_args.args[0])

    def test_no_unknown_outcome_is_writable(self):
        db = MagicMock()
        with self.assertRaises(ValueError):
            ocr._record_finish(db, 7, SECRET)
        db.execute.assert_not_called()
        self.assertIn("MAX_TOKENS", OUTCOME_CODES)


if __name__ == "__main__":
    unittest.main()
