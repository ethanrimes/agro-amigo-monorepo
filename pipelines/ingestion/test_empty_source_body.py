"""Loopback-only regression tests for rejecting empty source downloads.

These tests exercise the maintained worker fetch helpers with ordinary HTTP
responses. They do not require PostgreSQL, credentials, publisher access, or
Azure Blob storage.
"""
from __future__ import annotations

import socket
import threading
import unittest
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from unittest.mock import patch

import requests
from requests.adapters import HTTPAdapter

from . import worker


@dataclass
class Reply:
    status: int = 200
    body: bytes = b"source-bytes"
    headers: dict[str, str] | None = None
    transfer: str = "length"


class _Handler(BaseHTTPRequestHandler):
    routes: dict[str, list[Reply]] = {}
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        path = urlsplit(self.path).path
        replies = type(self).routes.get(path)
        if not replies:
            reply = Reply(status=404, body=b"not found")
        else:
            reply = replies.pop(0)
        self.send_response(reply.status)
        for key, value in (reply.headers or {}).items():
            self.send_header(key, value)
        if reply.transfer == "chunked":
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            self.wfile.write(b"0\r\n\r\n")
        elif reply.status == 304:
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif reply.transfer == "truncated":
            self.send_header("Content-Length", str(len(reply.body) + 5))
            self.end_headers()
            self.wfile.write(reply.body)
            self.wfile.flush()
            self.close_connection = True
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
        else:
            self.send_header("Content-Length", str(len(reply.body)))
            self.end_headers()
            if reply.body:
                self.wfile.write(reply.body)

    def log_message(self, *_args):
        pass

    def handle_error(self, request, client_address):
        # Truncated-body fixtures intentionally reset their connection.
        pass


class _LoopbackServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        # Truncated-body fixtures intentionally reset their connection.
        pass


class _TrackedResponse:
    def __init__(self, response, ledger):
        self._response = response
        self._ledger = ledger
        self.closed = False
        ledger.append(self)

    def __getattr__(self, name):
        return getattr(self._response, name)

    def close(self):
        self.closed = True
        return self._response.close()


class _Result:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class _FetchDB:
    def __init__(self, *, prior=(None, None, "pending", None), retained=None):
        self.prior = prior
        self.retained = retained
        self.statements = []

    def execute(self, sql, params=()):
        self.statements.append((sql, params))
        if "SELECT http_etag,http_last_modified,status,document_id" in sql:
            return _Result(self.prior)
        if "SELECT content FROM source_document" in sql:
            return _Result((self.retained,) if self.retained is not None else None)
        return _Result()


class EmptySourceBodyFetchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = _LoopbackServer(("127.0.0.1", 0), _Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self):
        _Handler.routes = {}
        self.responses = []
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.mount("http://", HTTPAdapter(max_retries=0))
        original_get = self.session.get

        def tracked_get(*args, **kwargs):
            # Stream the loopback response so a truncated-body read happens
            # after the response object has been returned to the worker.
            kwargs["stream"] = True
            return _TrackedResponse(original_get(*args, **kwargs), self.responses)

        self.session.get = tracked_get
        self.session_patch = patch.object(worker, "SESSION", self.session)
        self.session_patch.start()
        self.addCleanup(self.session_patch.stop)
        self.addCleanup(self.session.close)

    def url(self, path):
        return f"http://127.0.0.1:{self.server.server_port}/{path.lstrip('/')}"

    def assert_all_closed(self):
        self.assertTrue(self.responses)
        self.assertTrue(all(response.closed for response in self.responses))

    def test_fetch_closes_valid_empty_and_http_error_responses(self):
        _Handler.routes.update({
            "/valid.txt": [Reply(body=b"ok")],
            "/empty.txt": [Reply(body=b"", headers={"ETag": '"empty"'})],
            "/error.txt": [Reply(status=503, body=b"unavailable")],
        })
        self.assertEqual(worker.fetch(self.url("valid.txt")), b"ok")
        self.assertTrue(self.responses[-1].closed)

        with self.assertRaises(worker.EmptySourceBody) as empty:
            worker.fetch(self.url("empty.txt") + "?signature=private-value")
        self.assertTrue(empty.exception.retryable)
        self.assertNotIn("private-value", str(empty.exception))
        self.assertTrue(self.responses[-1].closed)

        with self.assertRaises(requests.HTTPError):
            worker.fetch(self.url("error.txt"))
        self.assert_all_closed()

    def test_fetch_asset_sets_validators_only_after_nonempty_body(self):
        _Handler.routes.update({
            "/valid.zip": [Reply(body=b"valid archive bytes", headers={"ETag": '"valid"', "Last-Modified": "Tue, 12 Oct 2026 00:00:00 GMT"})],
            "/empty.zip": [Reply(body=b"", headers={"ETag": '"empty"'})],
            "/chunked-empty.zip": [Reply(body=b"", headers={"ETag": '"chunked"'}, transfer="chunked")],
            "/error.zip": [Reply(status=503, body=b"unavailable")],
        })
        db = _FetchDB()
        self.assertEqual(worker.fetch_asset(db, self.url("valid.zip")), b"valid archive bytes")
        self.assertTrue(any("SET http_etag" in sql for sql, _ in db.statements))
        self.assertTrue(self.responses[-1].closed)

        for path in ("empty.zip", "chunked-empty.zip"):
            with self.subTest(path=path):
                before_updates = len([1 for sql, _ in db.statements if "SET http_etag" in sql])
                with self.assertRaises(worker.EmptySourceBody):
                    worker.fetch_asset(db, self.url(path))
                after_updates = len([1 for sql, _ in db.statements if "SET http_etag" in sql])
                self.assertEqual(after_updates, before_updates)
                self.assertTrue(self.responses[-1].closed)

        with self.assertRaises(requests.HTTPError):
            worker.fetch_asset(db, self.url("error.zip"))
        self.assert_all_closed()

    def test_body_read_failure_closes_response_without_validator_promotion(self):
        _Handler.routes["/truncated.zip"] = [Reply(body=b"PK", headers={"ETag": '"bad"'}, transfer="truncated")]
        db = _FetchDB()
        with self.assertRaises(requests.RequestException):
            worker.fetch_asset(db, self.url("truncated.zip"))
        self.assertFalse(any("SET http_etag" in sql for sql, _ in db.statements))
        self.assert_all_closed()

    def test_conditional_304_closes_and_double_unconditional_304_closes_both_responses(self):
        _Handler.routes.update({
            "/conditional.zip": [Reply(status=304)],
            "/retained.zip": [Reply(status=304), Reply(status=304)],
            "/empty-retained.zip": [Reply(status=304), Reply(status=304)],
        })
        conditional = _FetchDB(prior=('"current"', None, "complete", "prior-id"))
        self.assertIsNone(worker.fetch_asset(conditional, self.url("conditional.zip")))
        self.assertEqual(sum("checked_at=now()" in sql for sql, _ in conditional.statements), 1)
        self.assertTrue(self.responses[-1].closed)

        retained = _FetchDB(prior=(None, None, "complete", "prior-id"), retained=b"retained bytes")
        before = len(self.responses)
        self.assertEqual(worker.fetch_asset(retained, self.url("retained.zip")), b"retained bytes")
        self.assertTrue(all(response.closed for response in self.responses[before:]))
        self.assertEqual(len(self.responses[before:]), 2)

        empty_retained = _FetchDB(prior=(None, None, "complete", "empty-id"), retained=b"")
        before = len(self.responses)
        with self.assertRaises(worker.EmptySourceBody):
            worker.fetch_asset(empty_retained, self.url("empty-retained.zip"))
        self.assertTrue(all(response.closed for response in self.responses[before:]))
        self.assertEqual(len(self.responses[before:]), 2)

        # A pending asset has no accepted original to fall back to after two
        # unconditional 304s. Keep this distinct from the completed legacy
        # parser-upgrade path above.
        pending = _FetchDB(prior=(None, None, "pending", None))
        _Handler.routes["/pending-304.zip"] = [Reply(status=304), Reply(status=304)]
        before = len(self.responses)
        with self.assertRaisesRegex(ValueError, "HTTP 304 without a conditional asset request"):
            worker.fetch_asset(pending, self.url("pending-304.zip"))
        self.assertTrue(all(response.closed for response in self.responses[before:]))
        self.assertEqual(len(self.responses[before:]), 2)


if __name__ == "__main__":
    unittest.main()
