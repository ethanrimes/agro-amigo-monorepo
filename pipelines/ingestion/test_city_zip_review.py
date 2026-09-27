"""A date-conflicting city PDF must not prevent its valid peers publishing."""

import io
import json
import unittest
import zipfile
from datetime import date
from hashlib import sha256
from unittest.mock import MagicMock, patch

from .city_reports import CityZipPartialReview, _review_step, publish_city_zip
from .worker import SourceDateMismatch


def bundle_bytes(names):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as bundle:
        for name in names:
            bundle.writestr(name, name.encode())
    return output.getvalue()


class CityZipReview(unittest.TestCase):
    def test_review_key_remains_bounded_for_long_unicode_member_names(self):
        step = _review_step(
            {
                "filename": "🌽" * 500,
                "document_id": "a" * 64,
                "error": "🍅" * 1500,
                "error_type": "SourceDateMismatch",
            }
        )
        self.assertLess(len(step.encode("utf-8")), 2000)
        self.assertEqual(
            json.loads(step.removeprefix("review:"))["document_id"], "a" * 64
        )

    def publish(self, names, parser, db=None):
        db = db or MagicMock()
        with (
            patch(
                "pipelines.ingestion.worker.archive",
                side_effect=lambda db, url, data, *args, **kwargs: sha256(
                    data
                ).hexdigest(),
            ) as archive,
            patch("pipelines.ingestion.pdf_sources.extract_pages") as native,
            patch(
                "pipelines.ingestion.city_reports.parse_archived_city_pdf",
                side_effect=parser,
            ),
            patch("pipelines.ingestion.city_reports.save_classifications") as classify,
        ):
            try:
                result = publish_city_zip(
                    db,
                    bundle_bytes(names),
                    "archive-sha",
                    "https://www.dane.gov.co/cities.zip",
                    date(2026, 9, 17),
                    processor_version="city-v4",
                )
            except CityZipPartialReview as exc:
                result = exc
        return db, result, archive, native, classify

    def test_valid_peers_publish_before_and_after_conflicting_member(self):
        row = ("PDF page 1,table 1,row 4,round 1", date(2026, 9, 17))

        def parser(db, data, did, day):
            if data == b"conflict.pdf":
                raise SourceDateMismatch(
                    "City PDF has unverifiable or future internal date"
                )
            return [row]

        names = ["first.pdf", "conflict.pdf", "last.pdf"]
        db, result, archive, native, classify = self.publish(names, parser)
        self.assertIsInstance(result, CityZipPartialReview)
        self.assertEqual(result.count, 2)
        self.assertEqual(len(result.failures), 1)
        self.assertEqual(result.failures[0]["filename"], "conflict.pdf")
        self.assertEqual(result.failures[0]["error_type"], "SourceDateMismatch")
        self.assertEqual(archive.call_count, 3)
        self.assertEqual(native.call_count, 3)
        self.assertEqual(classify.call_count, 2)
        inserts = db.cursor.return_value.__enter__.return_value.copy.return_value.__enter__.return_value.write_row.call_args_list
        self.assertEqual(
            [call.args[0] for call in inserts],
            [
                (sha256(name.encode()).hexdigest(), *row)
                for name in (names[0], names[2])
            ],
        )
        reviews = [
            call
            for call in db.execute.call_args_list
            if "INSERT INTO ingestion_checkpoint" in call.args[0]
            and call.args[1][2].startswith("review:")
        ]
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0].args[1][:2], ("archive-sha", "city-v4"))
        self.assertEqual(
            json.loads(reviews[0].args[1][2].removeprefix("review:")),
            result.failures[0],
        )
        self.assertIn("ON CONFLICT DO NOTHING", reviews[0].args[0])
        self.assertFalse(
            any(
                "UPDATE source_document" in call.args[0]
                for call in db.execute.call_args_list
            )
        )

    def test_all_valid_members_keep_successful_result(self):
        db, result, _, _, _ = self.publish(
            ["one.pdf", "two.pdf"], lambda *args: [("native",)]
        )
        self.assertEqual(result, 2)
        checkpoints = [
            call
            for call in db.execute.call_args_list
            if "INSERT INTO ingestion_checkpoint" in call.args[0]
        ]
        self.assertEqual(len(checkpoints), 2)
        self.assertTrue(
            all(call.args[1][2].startswith("city-member:") for call in checkpoints)
        )

    def test_every_conflict_stays_review_with_no_regional_rows(self):
        def parser(*args):
            raise SourceDateMismatch("Internal date is later than archive date")

        db, result, _, _, _ = self.publish(["one.pdf", "two.pdf"], parser)
        self.assertEqual(result.count, 0)
        self.assertEqual(len(result.failures), 2)
        db.cursor.return_value.__enter__.return_value.copy.assert_not_called()

    def test_unexpected_failure_is_not_reclassified_or_swallowed(self):
        def parser(*args):
            raise RuntimeError("Connection failed")

        with self.assertRaisesRegex(RuntimeError, "Connection failed"):
            self.publish(["one.pdf"], parser)

    def test_review_checkpoint_failure_is_not_swallowed(self):
        db = MagicMock()

        def execute(sql, *args):
            if "INSERT INTO ingestion_checkpoint" in sql:
                raise RuntimeError("Checkpoint unavailable")
            return MagicMock()

        def parser(*args):
            raise SourceDateMismatch("Conflicting date")

        db.execute.side_effect = execute
        with self.assertRaisesRegex(RuntimeError, "Checkpoint unavailable"):
            self.publish(["one.pdf"], parser, db)


if __name__ == "__main__":
    unittest.main()
