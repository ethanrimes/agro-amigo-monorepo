from __future__ import annotations

from hashlib import sha256
import inspect
import unittest
from unittest.mock import MagicMock, patch

from . import city_rar_decoder as decoder
from . import city_rar_probe as probe

PROBE_BODY = decoder.RAR5_MAGIC + b"pinned"


class _Cursor:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class _ReadOnlyDB:
    def __init__(self, row_factory):
        self.row_factory = row_factory
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if sql.startswith("SET LOCAL TRANSACTION READ ONLY"):
            return _Cursor(None)
        return _Cursor(self.row_factory(len([c for c in self.calls if c[0] == probe._PARENT_SELECT])))


def _parent_row(*, title=None, publisher=None, url=None, media=None, kind=None,
                period=None, body=None, metadata=None, xmin="123"):
    return (
        decoder.AUG19_TITLE if title is None else title,
        decoder.AUG19_PUBLISHER if publisher is None else publisher,
        decoder.AUG19_URL if url is None else url,
        decoder.AUG19_MEDIA_TYPE if media is None else media,
        decoder.AUG19_KIND if kind is None else kind,
        decoder.AUG19_REFERENCE_PERIOD if period is None else period,
        PROBE_BODY if body is None else body,
        decoder.AUG19_METADATA if metadata is None else metadata,
        xmin,
    )


class CityRarProbeTests(unittest.TestCase):
    def setUp(self):
        self._source_hash_patches = [
            patch.object(decoder, "AUG19_SHA256", sha256(PROBE_BODY).hexdigest()),
            patch.object(decoder, "AUG19_DOCUMENT_ID", sha256(PROBE_BODY).hexdigest()),
        ]
        for context in self._source_hash_patches:
            context.start()
            self.addCleanup(context.stop)
        self.fake_reader = type("Reader", (), {
            "read": lambda _, name, limit: (b"%PDF-" + name.encode())
        })()
        self.fake_manifest = {
            name: (len(b"%PDF-" + name.encode()), sha256(b"%PDF-" + name.encode()).hexdigest())
            for name in decoder.AUG19_MEMBERS
        }

    def test_probe_has_no_caller_controlled_source_arguments_and_marks_transaction_read_only_first(self):
        self.assertEqual(list(inspect.signature(probe.run_aug19_decoder_probe).parameters), ["db"])
        db = _ReadOnlyDB(lambda _: _parent_row())
        with patch.object(decoder, "AUG19_MEMBERS", self.fake_manifest), patch.object(
            decoder, "AUG19_MAX_MEMBER_BYTES", max(size for size, _ in self.fake_manifest.values())
        ), patch.object(decoder, "decode_pinned_aug19_source", return_value=(self.fake_reader, (7, 21, 0), "test-platform")):
            result = probe.run_aug19_decoder_probe(db)
        self.assertEqual(db.calls[0], ("SET LOCAL TRANSACTION READ ONLY", None))
        self.assertEqual(len([c for c in db.calls if c[0] == probe._PARENT_SELECT]), 2)
        self.assertEqual(result["native_decoder_version"], "7.21.0")
        self.assertEqual(result["platform"], "test-platform")
        self.assertEqual(result["member_count"], 17)
        self.assertEqual(result["expanded_bytes"], sum(size for size, _ in self.fake_manifest.values()))
        self.assertEqual(len(result["member_hashes"]), 17)
        self.assertEqual(set(result), {
            "source_sha256", "native_decoder_version", "platform", "member_count",
            "expanded_bytes", "member_hashes", "elapsed_ms",
        })

    def test_wrong_retained_source_fields_body_hash_and_metadata_fail_closed(self):
        bad_rows = [
            _parent_row(title="other"),
            _parent_row(publisher="other"),
            _parent_row(url=decoder.AUG19_URL + "?alias=1"),
            _parent_row(media="application/octet-stream"),
            _parent_row(kind="derived"),
            _parent_row(period="2022-08-20"),
            _parent_row(body=b"Rar!wrong"),
            _parent_row(metadata={"retention": "temporary"}),
            None,
        ]
        for row in bad_rows:
            with self.subTest(row=row):
                db = _ReadOnlyDB(lambda _: row)
                with self.assertRaises(probe.CityRarProbeError):
                    probe.run_aug19_decoder_probe(db)
                self.assertEqual(db.calls[0][0], "SET LOCAL TRANSACTION READ ONLY")
                self.assertEqual(len([c for c in db.calls if c[0] == probe._PARENT_SELECT]), 1)

    def test_native_load_failure_is_concise_and_occurs_after_parent_pin(self):
        db = _ReadOnlyDB(lambda _: _parent_row())
        with patch.object(decoder, "decode_pinned_aug19_source", side_effect=ImportError("/secret/path/module.so details")):
            with self.assertRaisesRegex(probe.CityRarProbeError, "RAR decoder probe failed: ImportError") as err:
                probe.run_aug19_decoder_probe(db)
        self.assertNotIn("/secret/path", str(err.exception))
        self.assertEqual(len([c for c in db.calls if c[0] == probe._PARENT_SELECT]), 1)

    def test_xmin_change_during_decode_fails_closed(self):
        db = _ReadOnlyDB(lambda query_no: _parent_row(xmin="123" if query_no == 1 else "124"))
        with patch.object(decoder, "AUG19_MEMBERS", self.fake_manifest), patch.object(
            decoder, "AUG19_MAX_MEMBER_BYTES", max(size for size, _ in self.fake_manifest.values())
        ), patch.object(decoder, "decode_pinned_aug19_source", return_value=(self.fake_reader, (7, 21, 0), "test-platform")):
            with self.assertRaisesRegex(probe.CityRarProbeError, "xmin changed"):
                probe.run_aug19_decoder_probe(db)

    def test_decoder_rejects_wrong_url_or_source_hash_without_loading_native_module(self):
        from .city_rar_decoder import ArchiveCandidateError, Unrar2Rar5Reader

        with self.assertRaisesRegex(ArchiveCandidateError, "exact official"):
            Unrar2Rar5Reader(
                decoder.RAR5_MAGIC + b"not-the-retained-body", decoder.AUG19_URL,
                expected_members=decoder.AUG19_MEMBERS, max_members=17,
                max_member_bytes=decoder.AUG19_MAX_MEMBER_BYTES,
                max_total_bytes=decoder.AUG19_EXPANDED_BYTES,
            )

    def test_status_probe_uses_fresh_connection_and_explicit_transaction_before_read(self):
        from . import function_app

        events = []

        class Transaction:
            def __enter__(self):
                events.append("transaction-enter")

            def __exit__(self, *args):
                events.append("transaction-exit")

        class Connection:
            def transaction(self):
                events.append("transaction-created")
                return Transaction()

        connection = Connection()
        connection_context = MagicMock()
        connection_context.__enter__.return_value = connection
        with (
            patch.object(function_app, "connect", return_value=connection_context) as connect,
            patch.object(probe, "run_aug19_decoder_probe", side_effect=lambda db: events.append("probe") or {"member_count": 17}) as run_probe,
            patch.object(function_app, "run") as ingestion_run,
        ):
            result = function_app._pinned_city_archive_decoder_probe()

        self.assertEqual(result, {"available": True, "member_count": 17})
        self.assertEqual(events, ["transaction-created", "transaction-enter", "probe", "transaction-exit"])
        connect.assert_called_once_with()
        run_probe.assert_called_once_with(connection)
        ingestion_run.assert_not_called()

    def test_status_probe_fails_closed_on_probe_error_without_starting_work(self):
        from . import function_app

        connection_context = MagicMock()
        connection_context.__enter__.return_value = MagicMock()
        with (
            patch.object(function_app, "connect", return_value=connection_context),
            patch.object(probe, "run_aug19_decoder_probe", side_effect=probe.CityRarProbeError("native module missing")),
            patch.object(function_app, "run") as ingestion_run,
        ):
            result = function_app._pinned_city_archive_decoder_probe()

        self.assertEqual(result, {"available": False, "reason": "native module missing"})
        ingestion_run.assert_not_called()

    def test_status_only_calls_archive_probe_for_exact_opt_in_value(self):
        from . import function_app

        db = MagicMock()
        db.execute.return_value.fetchall.return_value = []
        db.execute.return_value.fetchone.return_value = (None, None, 0)
        connection_context = MagicMock()
        connection_context.__enter__.return_value = db
        delivery = patch("pipelines.ingestion.bug_reports.delivery_health", return_value={"overdue": {}})
        with (
            patch.object(function_app, "connect", return_value=connection_context),
            patch.object(function_app, "automation_health", return_value={"status": "ok"}),
            delivery,
            patch.object(function_app, "_pinned_city_archive_decoder_probe", return_value={"available": True, "member_count": 17}) as decoder_probe,
            patch.object(function_app, "_archive_decoder_capability") as general_capability,
        ):
            ordinary = function_app.status.build().get_user_function()(MagicMock(params={}))
            self.assertEqual(ordinary.status_code, 200)
            self.assertNotIn("pinned_city_archive_decoder", ordinary.get_body().decode())
            decoder_probe.assert_not_called()

            opted_in = function_app.status.build().get_user_function()(
                MagicMock(params={"archive-decode": "aug19-2022"})
            )
            self.assertEqual(opted_in.status_code, 200)
            self.assertIn('"pinned_city_archive_decoder": {"available": true, "member_count": 17}', opted_in.get_body().decode())
            decoder_probe.assert_called_once_with()
            general_capability.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
