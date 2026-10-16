"""Immutable workbook originals stay bounded and never bypass the public guard."""

import hashlib
import io
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from openpyxl import Workbook

from . import workbook_archive
from .workbook_preview import preview


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def pair(data):
    return hashlib.sha256(data).hexdigest(), data


class OriginalCacheTests(unittest.TestCase):
    def test_concurrent_same_document_loads_once_and_returns_exact_bytes(self):
        did, body = pair(b"unique immutable workbook")
        cache = workbook_archive.OriginalCache(128)
        entered = threading.Event()
        release = threading.Event()
        calls = []

        def load():
            calls.append(True)
            entered.set()
            self.assertTrue(release.wait(3))
            return body

        with ThreadPoolExecutor(max_workers=8) as pool:
            first = pool.submit(cache.get, did, load)
            self.assertTrue(entered.wait(3))
            others = [pool.submit(cache.get, did, load) for _ in range(7)]
            time.sleep(0.03)
            release.set()
            self.assertEqual([future.result(3) for future in [first, *others]], [body] * 8)
        self.assertEqual(len(calls), 1)
        self.assertEqual(cache.get(did, lambda: self.fail("cache miss")), body)

    def test_lru_byte_cap_evicts_and_oversized_original_is_not_cached(self):
        a, one = pair(b"123456")
        b, two = pair(b"abcdef")
        c, three = pair(b"xy")
        cache = workbook_archive.OriginalCache(10)
        for did, body in ((a, one), (b, two), (c, three)):
            self.assertEqual(cache.get(did, lambda body=body: body), body)
        self.assertLessEqual(cache._bytes, 10)
        self.assertNotIn(a, cache._items)
        self.assertEqual(cache.get(a, lambda: one), one)
        huge_id, huge = pair(b"x" * 15)
        self.assertEqual(cache.get(huge_id, lambda: huge), huge)
        self.assertNotIn(huge_id, cache._items)
        self.assertLessEqual(cache._bytes, 10)

    def test_failed_owner_unblocks_waiters_and_does_not_cache_failure(self):
        did, body = pair(b"later valid original")
        cache = workbook_archive.OriginalCache(128)
        entered = threading.Event()
        release = threading.Event()
        calls = []

        def fail():
            calls.append(True)
            entered.set()
            self.assertTrue(release.wait(3))
            raise OSError("blob and PG unavailable")

        with ThreadPoolExecutor(max_workers=4) as pool:
            owner = pool.submit(cache.get, did, fail)
            self.assertTrue(entered.wait(3))
            waiters = [pool.submit(cache.get, did, fail) for _ in range(3)]
            time.sleep(0.03)
            release.set()
            for future in [owner, *waiters]:
                with self.assertRaises(OSError):
                    future.result(3)
        self.assertEqual(len(calls), 1)
        self.assertEqual(cache.get(did, lambda: body), body)

    def test_blob_hash_mismatch_and_download_failure_fall_back_to_pg(self):
        did, body = pair(b"literal source workbook")
        cache = workbook_archive.OriginalCache(128)
        for blob_result in (b"different", OSError("storage unavailable")):
            with self.subTest(blob_result=type(blob_result).__name__):
                cache = workbook_archive.OriginalCache(128)
                with patch.object(
                    workbook_archive, "_blob_original",
                    side_effect=blob_result if isinstance(blob_result, Exception) else None,
                    return_value=blob_result if isinstance(blob_result, bytes) else None,
                ) as blob:
                    calls = []
                    actual = workbook_archive.original(
                        did, XLSX, lambda: calls.append(True) or body,
                        storage_connection="test-only", cache=cache,
                    )
                self.assertEqual(actual, body)
                blob.assert_called_once_with(did, ".xlsx", "test-only")
                self.assertEqual(len(calls), 1)
        with patch.object(workbook_archive, "_blob_original", return_value=b"wrong"):
            with self.assertRaises(workbook_archive.OriginalUnavailable):
                workbook_archive.original(
                    did, XLSX, lambda: b"also wrong", storage_connection="test-only",
                    cache=workbook_archive.OriginalCache(128),
                )

    def test_valid_blob_avoids_pg_and_disables_slow_sdk_retries(self):
        did, body = pair(b"archived xlsx bytes")
        with patch("azure.storage.blob.BlobServiceClient.from_connection_string") as factory:
            blob = factory.return_value.get_blob_client.return_value
            blob.download_blob.return_value.readall.return_value = body
            data = workbook_archive.original(
                did, XLSX, lambda: self.fail("PG transfer on valid Blob"),
                storage_connection="test-only", cache=workbook_archive.OriginalCache(128),
            )
        self.assertEqual(data, body)
        factory.assert_called_once()
        self.assertEqual(factory.call_args.kwargs["retry_total"], 0)
        self.assertEqual(factory.call_args.kwargs["read_timeout"], 10)
        factory.return_value.get_blob_client.assert_called_once_with(
            "source-archive", did + ".xlsx"
        )
        self.assertEqual(blob.download_blob.call_args.kwargs["max_concurrency"], 1)

    def test_missing_original_and_unsupported_media_never_cache(self):
        did, _ = pair(b"missing")
        cache = workbook_archive.OriginalCache(128)
        with self.assertRaises(workbook_archive.OriginalUnavailable):
            workbook_archive.original(
                did, XLSX, lambda: None, storage_connection="", cache=cache
            )
        with self.assertRaises(workbook_archive.OriginalUnavailable):
            workbook_archive.original(
                did, XLSX, lambda: (_ for _ in ()).throw(OSError("PG busy")),
                storage_connection="", cache=cache,
            )
        self.assertFalse(cache._items)
        with self.assertRaises(ValueError):
            workbook_archive.original(did, "application/pdf", lambda: b"PDF", cache=cache)

    def test_exact_xlsx_preview_values_survive_cached_original(self):
        book = Workbook()
        sheet = book.active
        sheet.title = "Precios"
        sheet.append(["Producto", "COP"])
        sheet.append(["Arroz", 9639.74178])
        out = io.BytesIO()
        book.save(out)
        did, body = pair(out.getvalue())
        cache = workbook_archive.OriginalCache(128 * 1024)
        pg_calls = []

        def pg():
            pg_calls.append(True)
            return body

        first = workbook_archive.original(
            did, XLSX, pg, storage_connection="", cache=cache
        )
        second = workbook_archive.original(
            did, XLSX, pg, storage_connection="", cache=cache
        )
        self.assertEqual(pg_calls, [True])
        self.assertEqual(preview(first, "Precios", 2, 1), preview(body, "Precios", 2, 1))
        self.assertEqual(preview(second, "Precios", 2, 1)["rows"][0][1]["value"], 9639.74178)


if __name__ == "__main__":
    unittest.main()
