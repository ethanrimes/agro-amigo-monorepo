"""Real streamed HTTP responses must close even when backoff persistence fails."""

from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import unittest
from unittest.mock import Mock, patch

import requests

from . import worker
from .source_http_backoff import HostRateLimited


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(429 if self.path == "/limited" else 200)
        self.send_header("Retry-After", "7200")
        self.send_header("Content-Length", "4")
        self.end_headers()
        self.wfile.write(b"test")

    def log_message(self, *_args):
        pass


class ResponseCleanup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def call(self, path, cooldown):
        token = worker.HOST_COOLDOWNS.set(cooldown)
        self.addCleanup(worker.HOST_COOLDOWNS.reset, token)
        session = requests.Session()
        self.addCleanup(session.close)
        received = []
        actual_get = session.get

        def observed_get(*args, **kwargs):
            response = actual_get(*args, **kwargs)
            received.append(response)
            return response

        with patch.object(worker, "SESSION", session), patch.object(session, "get", side_effect=observed_get):
            try:
                return worker._get(self.url + path, stream=True, timeout=(2, 2)), received
            except Exception as error:
                return error, received

    def test_streamed_429_without_database_preserves_retry_after_and_closes(self):
        before = datetime.now(timezone.utc)
        error, received = self.call("/limited", None)
        self.assertIsInstance(error, HostRateLimited)
        self.assertEqual((error.host, error.literal_header), ("127.0.0.1", "7200"))
        self.assertGreaterEqual(error.retry_at, before + timedelta(hours=2))
        self.assertEqual(len(received), 1)
        self.assertTrue(received[0].raw.closed)

    def test_persisted_backoff_is_returned_and_response_is_closed(self):
        error = HostRateLimited("127.0.0.1", datetime.now(timezone.utc) + timedelta(hours=2), "7200")
        cooldown = Mock()
        cooldown.record.return_value = error
        actual, received = self.call("/limited", cooldown)
        self.assertIs(actual, error)
        cooldown.check.assert_called_once_with(self.url + "/limited")
        cooldown.record.assert_called_once_with(self.url + "/limited", received[0])
        self.assertTrue(received[0].raw.closed)

    def test_failed_backoff_write_still_closes_response(self):
        cooldown = Mock()
        cooldown.record.side_effect = RuntimeError("test backoff write failure")
        error, received = self.call("/limited", cooldown)
        self.assertIsInstance(error, RuntimeError)
        self.assertEqual(str(error), "test backoff write failure")
        self.assertTrue(received[0].raw.closed)

    def test_successful_response_remains_owned_by_caller(self):
        response, received = self.call("/ok", None)
        self.assertIs(response, received[0])
        try:
            self.assertFalse(response.raw.closed)
            self.assertEqual(response.content, b"test")
        finally:
            response.close()


if __name__ == "__main__":
    unittest.main()
