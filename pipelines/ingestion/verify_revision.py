"""Integration test against PostgreSQL, with all fixture writes rolled back.

Uses an actual local HTTP server to exercise changed bytes at one URL and 304.
Does not upload fixtures to cloud storage or publish artificial application prices.
"""

import io
import json
import os
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import openpyxl
from psycopg import Rollback

from . import worker as w


def main():
    storage = os.environ.pop("AzureWebJobsStorage", None)
    test_id = uuid.uuid4().hex
    state = {"version": 1, "requests": []}
    payloads = {}
    for v in (1, 2):
        b = openpyxl.Workbook()
        b.active.append(["test", test_id, "revision", v])
        s = io.BytesIO()
        b.save(s)
        payloads[v] = s.getvalue()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            etag = f'"revision-{state["version"]}"'
            state["requests"].append(self.headers.get("If-None-Match"))
            if self.headers.get("If-None-Match") == etag:
                self.send_response(304)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("ETag", etag)
            self.end_headers()
            self.wfile.write(payloads[state["version"]])

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/{test_id}.xlsx"
    result = {}
    try:
        with w.connect() as db:
            with db.transaction():
                w.queue(db, url, "regression-fixture")
                first = w.archive(db, url, w.fetch_asset(db, url), "regression-fixture")
                db.execute(
                    "UPDATE ingestion_asset SET status='complete',document_id=%s WHERE url=%s",
                    (first, url),
                )
                assert w.fetch_asset(db, url) is None
                state["version"] = 2
                second = w.archive(
                    db, url, w.fetch_asset(db, url), "regression-fixture"
                )
                assert first != second
                assert (
                    db.execute(
                        "SELECT count(*) FROM source_document WHERE source_url=%s",
                        (url,),
                    ).fetchone()[0]
                    == 2
                )
                assert (
                    bytes(
                        db.execute(
                            "SELECT content FROM source_document WHERE id=%s", (first,)
                        ).fetchone()[0]
                    )
                    == payloads[1]
                )
                db.execute(
                    "UPDATE ingestion_asset SET status='failed' WHERE url=%s", (url,)
                )
                assert w.fetch_asset(db, url) == payloads[2]
                assert state["requests"][-1] is None
                result = {
                    "unchanged_304": True,
                    "same_url_two_immutable_versions": True,
                    "old_bytes_preserved": True,
                    "failed_assets_retry_without_validators": True,
                }
                raise Rollback()
            assert (
                db.execute(
                    "SELECT count(*) FROM source_document WHERE source_url=%s", (url,)
                ).fetchone()[0]
                == 0
            )
            result["fixture_transaction_rolled_back"] = True
    finally:
        server.shutdown()
        server.server_close()
        if storage:
            os.environ["AzureWebJobsStorage"] = storage
    print(json.dumps(result))
    return result


if __name__ == "__main__":
    main()
