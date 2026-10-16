"""The May 2024 administrative member is skipped only with exact source proof."""

import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from reportlab.pdfgen import canvas

from pipelines.ingestion import city_nonprice_context as subject


_PRIVATE_PARENT = (
    Path(__file__).resolve().parents[2]
    / "artifacts/qa-resumed-20261001/ios/city-nonprice-private-20261006-i/retained-parent.zip"
)


def _sanitized_pdf(*, heading="FORMATO VALORACIÓN A LA GESTIÓN", pages=2):
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    for page in range(pages):
        pdf.drawString(40, 760, heading)
        pdf.drawString(40, 730, "METAS ESTABLECIDAS Y LOGRADAS")
        pdf.drawString(40, 700, "Texto administrativo sin observaciones comerciales.")
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


class _Result:
    def __init__(self, value):
        self.value = value

    def fetchone(self):
        return self.value

    def fetchall(self):
        return self.value


class _DB:
    def __init__(self, parent, child, *, price_table=None, checkpoints=None):
        self.parent = parent
        self.child = child
        self.price_table = price_table
        self.checkpoints = checkpoints or {}
        self.mapping = subject.MEMBER_SHA256
        self.committed = []

    @contextmanager
    def transaction(self):
        yield

    def execute(self, sql, args):
        if "FROM ingestion_asset" in sql:
            return _Result((subject.URL, "city-zip", subject.DAY, subject.PARENT_SHA256, "review"))
        if "FROM source_document" in sql:
            return _Result(self.parent if args[0] == subject.PARENT_SHA256 else self.child)
        if "FROM source_archive_member" in sql:
            return _Result((self.mapping,) if self.mapping else None)
        if sql.startswith("SELECT 1 FROM"):
            table = sql.split("FROM ", 1)[1].split(" ", 1)[0]
            return _Result((1,) if table == self.price_table else None)
        if "FROM ingestion_checkpoint" in sql:
            if "AND step=%s" in sql:
                value = self.checkpoints.get(args[2])
                return _Result((value,) if value is not None else None)
            return _Result(list(self.checkpoints.items()))
        if sql.startswith("INSERT INTO ingestion_checkpoint"):
            self.checkpoints.setdefault(args[2], 0)
            self.committed.append("checkpoint")
            return _Result(None)
        if sql.startswith("INSERT INTO source_archive_member"):
            self.mapping = args[2]
            self.committed.append("mapping")
            return _Result(None)
        raise AssertionError(sql)


class CityNonpriceContextTests(unittest.TestCase):
    def test_shared_registry_is_exact(self):
        subject._scope()

    def test_registry_allows_other_sources_but_fails_exact_mutation_or_duplicate(self):
        original = json.loads(subject._REGISTRY.read_text())
        unrelated = {
            "document_id": "f" * 64, "archive_id": "e" * 64,
            "archive_entry": "other.pdf", "scope": "other-reviewed-scope",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scope.json"
            with patch.object(subject, "_REGISTRY", path):
                path.write_text(json.dumps({**original, "documents": original["documents"] + [unrelated]}))
                subject._scope()
                path.write_text(json.dumps({**original, "documents": original["documents"] * 2}))
                with self.assertRaises(ValueError):
                    subject._scope()
                changed = {**original["documents"][0], "bytes": subject.MEMBER_BYTES + 1}
                path.write_text(json.dumps({**original, "documents": [changed]}))
                with self.assertRaises(ValueError):
                    subject._scope()

    @unittest.skipUnless(_PRIVATE_PARENT.exists(), "retained private exact parent unavailable")
    def test_retained_original_and_wrong_bindings(self):
        parent = _PRIVATE_PARENT.read_bytes()
        verified = subject.verify_exact_nonprice_parent(
            subject.URL, parent, subject.PARENT_SHA256, subject.DAY,
        )
        self.assertEqual(len(verified.content), subject.MEMBER_BYTES)
        self.assertEqual(len(verified.peer_steps), 32)
        self.assertIsNone(subject.verify_exact_nonprice_parent(
            "https://example.invalid/other.zip", parent, subject.PARENT_SHA256, subject.DAY,
        ))
        altered = bytearray(parent)
        altered[-1] ^= 1
        for url, body, digest, day in (
            (subject.URL, bytes(altered), subject.PARENT_SHA256, subject.DAY),
            (subject.URL, parent, "0" * 64, subject.DAY),
            (subject.URL, parent, subject.PARENT_SHA256, subject.DAY.replace(day=30)),
        ):
            with self.assertRaises(ValueError):
                subject.verify_exact_nonprice_parent(url, body, digest, day)

    def test_sanitized_pdf_native_controls_reject_price_page_and_missing_page(self):
        for heading, pages, good in (
            ("FORMATO VALORACIÓN A LA GESTIÓN", 2, True),
            ("PRECIOS DE VENTA MAYORISTA", 2, False),
            ("FORMATO VALORACIÓN A LA GESTIÓN", 1, False),
        ):
            content = _sanitized_pdf(heading=heading, pages=pages)
            with patch.object(subject, "MEMBER_SHA256", hashlib.sha256(content).hexdigest()), patch.object(
                subject, "MEMBER_BYTES", len(content),
            ):
                if good:
                    subject._verify_native_nonprice_pdf(content)
                else:
                    with self.assertRaises(ValueError):
                        subject._verify_native_nonprice_pdf(content)

    def _bound_db(self):
        parent_bytes, child_bytes = b"synthetic parent", b"synthetic child"
        parent_digest = hashlib.sha256(parent_bytes).hexdigest()
        child_digest = hashlib.sha256(child_bytes).hexdigest()
        parent = (
            parent_digest, subject.URL, "application/zip", "original", len(parent_bytes), parent_bytes,
            {"retention": "permanent", "ingestion_kind": "city-zip", "original_filename": subject._PARENT_FILENAME}, None,
        )
        child = (
            child_digest, subject.URL, "application/pdf", "original", len(child_bytes), child_bytes,
            {"retention": "permanent", "ingestion_kind": "city-pdf", "original_filename": subject.MEMBER_NAME,
             "archive_entry": subject.MEMBER_NAME, "parents": [parent_digest]}, 2,
        )
        return parent_bytes, parent_digest, child_digest, _DB(parent, child)

    def test_transactional_zero_marker_then_unchanged_generic_peer_publisher(self):
        parent, parent_sha, child_sha, db = self._bound_db()
        verified = subject.VerifiedNonpriceMember(b"synthetic child", "city-member:admin", frozenset({"city-member:peer"}))
        with patch.object(subject, "PARENT_SHA256", parent_sha), patch.object(
            subject, "MEMBER_SHA256", child_sha,
        ), patch.object(subject, "MEMBER_BYTES", len(verified.content)), patch.object(
            subject, "verify_exact_nonprice_parent", return_value=verified,
        ), patch.object(subject, "_check_existing_peer_parity"), patch.object(
            subject.city_reports, "publish_city_zip", return_value=17,
        ) as generic:
            db.mapping = child_sha
            self.assertEqual(subject.maybe_publish_exact_nonprice_city_zip(
                db, subject.URL, parent, parent_sha, subject.DAY,
            ), 17)
            self.assertEqual(db.checkpoints, {verified.step: 0})
            generic.assert_called_once_with(
                db, parent, parent_sha, subject.URL, subject.DAY,
                processor_version=subject.VERSION,
            )
            # Replay is idempotent; a completed sibling is an allowed marker.
            db.checkpoints["city-member:peer"] = 17
            self.assertEqual(subject.maybe_publish_exact_nonprice_city_zip(
                db, subject.URL, parent, parent_sha, subject.DAY,
            ), 17)
            self.assertEqual(db.checkpoints[verified.step], 0)

    def test_old_price_or_new_version_collision_fails_before_marker(self):
        parent, parent_sha, child_sha, db = self._bound_db()
        verified = subject.VerifiedNonpriceMember(b"synthetic child", "city-member:admin", frozenset({"city-member:peer"}))
        with patch.object(subject, "PARENT_SHA256", parent_sha), patch.object(
            subject, "MEMBER_SHA256", child_sha,
        ), patch.object(subject, "MEMBER_BYTES", len(verified.content)), patch.object(
            subject, "verify_exact_nonprice_parent", return_value=verified,
        ), patch.object(subject, "_check_existing_peer_parity"), patch.object(
            subject.city_reports, "publish_city_zip",
        ) as generic:
            db.mapping = child_sha
            db.price_table = "regional_classification"
            with self.assertRaisesRegex(ValueError, "existing agricultural row"):
                subject.maybe_publish_exact_nonprice_city_zip(db, subject.URL, parent, parent_sha, subject.DAY)
            self.assertEqual(db.checkpoints, {})
            db.price_table = None
            db.checkpoints = {"city-member:peer": 17}
            with self.assertRaisesRegex(ValueError, "checkpoint collision"):
                subject.maybe_publish_exact_nonprice_city_zip(db, subject.URL, parent, parent_sha, subject.DAY)
            generic.assert_not_called()

    def test_positive_peer_checkpoint_requires_full_native_17_field_parity(self):
        row = (
            "PDF page 1,table 1,row 1,round 1", subject.DAY, "product", "Product",
            "Market", "Category > Leaf", "Kilogramo", 1, "Kilogramo", 1,
            "Ronda 1", 100, 200, "kg", 100, 200, 1,
        )
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("price.pdf", b"synthetic price PDF")
        with zipfile.ZipFile(io.BytesIO(archive.getvalue())) as bundle:
            step = subject.city_reports._member_step(bundle.infolist()[0], subject.DAY)

        class PeerDB:
            def __init__(self, stored):
                self.stored = stored

            def execute(self, sql, _args):
                if "FROM regional_price" in sql:
                    return _Result(self.stored)
                if "FROM regional_classification" in sql:
                    return _Result([(row[0], ["Category", "Leaf"])])
                raise AssertionError(sql)

        with patch.object(subject.city_reports, "parse_city_pdf", side_effect=lambda *_: iter([row])):
            subject._check_existing_peer_parity(PeerDB([row]), archive.getvalue(), {step: 1})
            with self.assertRaisesRegex(ValueError, "17-field"):
                subject._check_existing_peer_parity(
                    PeerDB([row[:11] + (101,) + row[12:]]), archive.getvalue(), {step: 1},
                )
            with self.assertRaisesRegex(ValueError, "checkpoint"):
                subject._check_existing_peer_parity(PeerDB([row]), archive.getvalue(), {step: 2})


if __name__ == "__main__":
    unittest.main()
