"""Fetch SHA-verified immutable workbook originals without repeated TOAST reads.

Authorization is deliberately outside this cache: the HTTP route checks the
current public-source metadata for every request before it calls ``original``.
"""

import hashlib
import os
import re
import threading
from collections import OrderedDict
from concurrent.futures import Future


MAX_CACHE_BYTES = 128 * 1024 * 1024
_EXTENSIONS = {
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
}


class OriginalUnavailable(Exception):
    """Neither archive contains bytes matching the content-addressed ID."""


class ImmutableByteCache:
    """Bounded LRU storage and in-flight sharing for immutable byte results."""

    def __init__(self, capacity=MAX_CACHE_BYTES):
        self.capacity = capacity
        self._bytes = 0
        self._items = OrderedDict()
        self._inflight = {}
        self._lock = threading.Lock()

    def get(self, did, loader):
        with self._lock:
            cached = self._items.get(did)
            if cached is not None:
                self._items.move_to_end(did)
                return cached
            future = self._inflight.get(did)
            owner = future is None
            if owner:
                future = Future()
                self._inflight[did] = future
        if not owner:
            return future.result()
        try:
            data = bytes(loader())
            with self._lock:
                if len(data) <= self.capacity:
                    while self._items and self._bytes + len(data) > self.capacity:
                        _, old = self._items.popitem(last=False)
                        self._bytes -= len(old)
                    self._items[did] = data
                    self._bytes += len(data)
                del self._inflight[did]
                future.set_result(data)
            return data
        except Exception as exc:
            with self._lock:
                del self._inflight[did]
                future.set_exception(exc)
            raise


class OriginalCache(ImmutableByteCache):
    """Only cache originals whose bytes match their content-addressed ID."""

    def get(self, did, loader):
        def verified():
            data = bytes(loader())
            if hashlib.sha256(data).hexdigest() != did:
                raise OriginalUnavailable("Workbook original SHA-256 mismatch")
            return data

        return super().get(did, verified)


_CACHE = OriginalCache()


def _blob_original(did, extension, connection):
    from azure.storage.blob import BlobServiceClient

    blob = BlobServiceClient.from_connection_string(
        connection, retry_total=0, retry_connect=0, retry_read=0, retry_status=0,
        connection_timeout=3, read_timeout=10,
    ).get_blob_client(
        "source-archive", did + extension
    )
    return blob.download_blob(
        max_concurrency=1, timeout=20, connection_timeout=3, read_timeout=10
    ).readall()


def original(did, media_type, pg_loader, *, storage_connection=None, cache=None):
    """Prefer the archived Blob, fall back to PG, and cache only exact bytes.

    ``pg_loader`` opens its own short-lived connection only on a cache miss
    after Blob retrieval fails. An archive mismatch never enters the cache.
    """
    if not re.fullmatch(r"[a-f0-9]{64}", did) or media_type not in _EXTENSIONS:
        raise ValueError("Unsupported workbook original")
    storage_connection = (
        os.environ.get("AzureWebJobsStorage")
        if storage_connection is None else storage_connection
    )

    def load():
        if storage_connection:
            try:
                body = _blob_original(did, _EXTENSIONS[media_type], storage_connection)
                if hashlib.sha256(body).hexdigest() == did:
                    return body
            except Exception:
                pass  # Exact original remains available from the database.
        try:
            body = pg_loader()
        except Exception as exc:
            raise OriginalUnavailable("Workbook original unavailable") from exc
        if body is None:
            raise OriginalUnavailable("Workbook original missing")
        return body

    return (cache or _CACHE).get(did, load)
