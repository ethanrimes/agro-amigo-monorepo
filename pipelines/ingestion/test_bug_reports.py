"""Private outbox isolation, concurrent limits and SMTP retry without sending mail."""
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import smtplib
import unittest
import uuid
from unittest.mock import MagicMock, patch

import psycopg
from psycopg import sql
from psycopg.pq import TransactionStatus

from . import bug_reports

SETTINGS = {"SMTP_HOST": "smtp.invalid", "SMTP_PORT": "587", "SMTP_USER": "fixture", "SMTP_PASSWORD": "fixture-secret", "SMTP_FROM": "fixture@example.invalid", "BUG_REPORT_TO": "owner@example.invalid"}


class BugReportMailTests(unittest.TestCase):
    def test_tls_authentication_and_fixed_recipient_preserve_reply_address(self):
        with patch.dict(os.environ, SETTINGS), patch.object(bug_reports.smtplib, "SMTP") as factory:
            client = factory.return_value.__enter__.return_value
            bug_reports.send((uuid.uuid4(), "Mensaje enviado por una persona", "reply@example.invalid", "/product/lulo?market=Bogota", None), bug_reports.smtp_settings())
            client.starttls.assert_called_once()
            client.login.assert_called_once_with("fixture", "fixture-secret")
            mail = client.send_message.call_args.args[0]
            self.assertEqual(mail["To"], "owner@example.invalid")
            self.assertEqual(mail["Reply-To"], "reply@example.invalid")
            self.assertIn("market=Bogota", mail.get_content())

    def test_missing_configuration_does_not_claim_or_send(self):
        with patch.dict(os.environ, {key: "" for key in SETTINGS}), patch.object(bug_reports, "send") as send:
            db = MagicMock()
            self.assertFalse(bug_reports.deliver_pending(db)["configured"])
            db.execute.assert_not_called(); send.assert_not_called()

    def test_authenticated_remote_check_never_sends_a_message(self):
        with patch.dict(os.environ, SETTINGS), patch.object(bug_reports.smtplib, "SMTP") as factory:
            client = factory.return_value.__enter__.return_value
            self.assertEqual(bug_reports.check_smtp_connection(), {"configured": True, "authenticated": True, "message_sent": False})
            client.login.assert_called_once(); client.send_message.assert_not_called()

    def test_caller_transaction_cannot_send_an_uncommitted_report(self):
        with patch.dict(os.environ, SETTINGS), patch.object(bug_reports, "send") as send:
            db = MagicMock(autocommit=False)
            with self.assertRaisesRegex(RuntimeError, "committed, idle"):
                bug_reports.deliver_pending(db)
            send.assert_not_called()


@unittest.skipUnless(os.environ.get("AGRO_BUG_REPORT_POSTGRES_TEST") == "1", "Explicit private PostgreSQL opt-in")
class BugReportPostgresTests(unittest.TestCase):
    def setUp(self):
        self.dsn = os.environ["DATABASE_URL"]
        self.db = psycopg.connect(self.dsn, autocommit=True)
        self.addCleanup(self.db.close)
        # Refuse the live DB even if an opt-in flag is accidentally inherited.
        self.assertTrue(self.db.info.host.startswith("/tmp/"), "Outbox tests require a private local PostgreSQL socket")
        self.schema = "bug_report_test_" + uuid.uuid4().hex
        self.db.execute(sql.SQL("CREATE SCHEMA {};").format(sql.Identifier(self.schema)))
        self.addCleanup(lambda: self.db.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema))))
        self.db.execute(sql.SQL("SET search_path TO {},pg_catalog").format(sql.Identifier(self.schema)))
        self.db.execute("DO $$ BEGIN IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='agro_reader') THEN CREATE ROLE agro_reader; END IF; IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='agro_ingestor') THEN CREATE ROLE agro_ingestor; END IF; END $$")
        self.db.execute("CREATE TABLE source_document(id text PRIMARY KEY)")
        migration = Path(__file__).with_name("migrations").joinpath("20261001_041_bug_reports.sql").read_text()
        migration = migration.replace("public.", self.schema + ".").replace("pg_catalog,public", "pg_catalog," + self.schema)
        self.db.execute(migration)
        self.db.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO agro_reader,agro_ingestor").format(sql.Identifier(self.schema)))
        self.key = "a" * 64
        self.environment = patch.dict(os.environ, SETTINGS)
        self.environment.start(); self.addCleanup(self.environment.stop)

    def submit(self, key=None, consent=True, reply="", path="/products?category=Frutas"):
        return self.db.execute("SELECT submit_bug_report(%s,%s,%s,'',%s,%s)", ("Una descripción suficientemente larga", reply, path, key or self.key, consent)).fetchone()[0]

    def test_read_only_role_can_submit_but_never_enumerate_private_reports(self):
        self.db.execute("SET ROLE agro_reader")
        try:
            ident = self.submit()
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                self.db.execute("SELECT * FROM bug_report")
        finally:
            self.db.execute("RESET ROLE")
        self.assertEqual(self.db.execute("SELECT id,status FROM bug_report").fetchone(), (ident, "queued"))
        for options in ({"consent": False}, {"reply": "user@example.invalid\r\nBcc: someone@invalid"}, {"path": "//external.invalid"}):
            with self.assertRaises(psycopg.Error) as caught:
                self.submit(**options)
            self.assertEqual(caught.exception.sqlstate, "PBR01")
        self.assertEqual(self.db.execute("SELECT count(*) FROM bug_report").fetchone()[0], 1)

    def test_concurrent_submissions_are_limited_across_server_instances(self):
        def submit_one(_):
            with psycopg.connect(self.dsn, autocommit=True) as db:
                db.execute(sql.SQL("SET search_path TO {},pg_catalog").format(sql.Identifier(self.schema)))
                db.execute("SET ROLE agro_reader")
                try:
                    db.execute("SELECT submit_bug_report('Un problema en el precio','','/products','',%s,true)", (self.key,))
                    return "queued"
                except psycopg.Error as exc:
                    return exc.sqlstate
        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(submit_one, range(8)))
        self.assertEqual(outcomes.count("queued"), 5)
        self.assertEqual(outcomes.count("PBR02"), 3)

    def test_committed_claim_failure_backoff_and_eventual_delivery(self):
        ident = self.submit()
        def unavailable(row, settings):
            self.assertEqual(self.db.info.transaction_status, TransactionStatus.IDLE)
            self.assertEqual(row[0], ident)
            self.assertEqual(self.db.execute("SELECT status,attempts FROM bug_report").fetchone(), ("sending", 1))
            raise smtplib.SMTPAuthenticationError(535, b"private provider diagnostics")
        with patch.object(bug_reports, "send", side_effect=unavailable):
            result = bug_reports.deliver_pending(self.db)
        self.assertEqual(result["retry"], 1)
        status, attempts, pending, diagnostic = self.db.execute("SELECT status,attempts,next_attempt_at>now(),delivery_error FROM bug_report").fetchone()
        self.assertEqual((status,attempts,pending,diagnostic), ("queued",1,True,"SMTPAuthenticationError"))
        self.db.execute("UPDATE bug_report SET next_attempt_at=now()-interval '1 second'")
        with patch.object(bug_reports, "send") as send:
            result = bug_reports.deliver_pending(self.db)
        self.assertEqual(result["sent"], 1); send.assert_called_once()
        self.assertEqual(self.db.execute("SELECT status,attempts,sent_at IS NOT NULL,delivery_error FROM bug_report").fetchone(), ("sent",2,True,None))

    def test_restart_reclaims_expired_lease_and_overlap_does_not_duplicate(self):
        self.submit()
        self.db.execute("UPDATE bug_report SET status='sending',leased_until=now()-interval '1 second',attempts=1")
        with patch.object(bug_reports, "send") as send:
            self.assertEqual(bug_reports.deliver_pending(self.db)["sent"], 1)
            self.assertEqual(bug_reports.deliver_pending(self.db)["sent"], 0)
        send.assert_called_once()
        self.assertEqual(self.db.execute("SELECT attempts FROM bug_report").fetchone()[0], 2)
