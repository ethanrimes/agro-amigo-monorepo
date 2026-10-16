"""Deliver consented reports to one configured owner from a durable private outbox."""
import os
import smtplib
import ssl
import time
from contextlib import contextmanager
from email.message import EmailMessage

import certifi
from psycopg.pq import TransactionStatus

LOCK = 419810301


def delivery_health(db):
    pending, overdue, last_sent = db.execute("""SELECT
      count(*) FILTER(WHERE status<>'sent'),
      count(*) FILTER(WHERE status<>'sent' AND created_at<now()-interval '2 hours'),
      max(sent_at) FROM bug_report""").fetchone()
    return {"pending": pending, "overdue": overdue, "last_sent": last_sent}


def smtp_settings():
    keys = ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM", "BUG_REPORT_TO")
    values = {key: os.environ.get(key, "") for key in keys}
    try:
        values["SMTP_PORT"] = int(os.environ.get("SMTP_PORT", "587"))
    except ValueError:
        return None
    if not all(values[key] for key in keys) or values["SMTP_PORT"] not in (465, 587):
        return None
    if any("\r" in values[key] or "\n" in values[key] for key in ("SMTP_FROM", "BUG_REPORT_TO")):
        return None
    return values


@contextmanager
def authenticated_smtp(settings):
    context = ssl.create_default_context(cafile=certifi.where())
    secure = settings["SMTP_PORT"] == 465
    klass = smtplib.SMTP_SSL if secure else smtplib.SMTP
    with klass(settings["SMTP_HOST"], settings["SMTP_PORT"], timeout=10,
               **({"context": context} if secure else {})) as smtp:
        smtp.ehlo()
        if not secure:
            smtp.starttls(context=context)
            smtp.ehlo()
        smtp.login(settings["SMTP_USER"], settings["SMTP_PASSWORD"])
        yield smtp


def check_smtp_connection():
    settings = smtp_settings()
    if not settings:
        return {"configured": False, "authenticated": False}
    with authenticated_smtp(settings):
        pass
    return {"configured": True, "authenticated": True, "message_sent": False}


def send(report, settings):
    ident, message, reply, path, source = report
    mail = EmailMessage()
    mail["Subject"] = "AgroAmigo · Reporte de un problema"
    mail["From"] = settings["SMTP_FROM"]
    mail["To"] = settings["BUG_REPORT_TO"]
    mail["Message-ID"] = f"<{ident}@agroamigo.app>"
    if reply:
        mail["Reply-To"] = reply
    mail.set_content(f"Reporte: {ident}\nPantalla y filtros: {path or '(no indicados)'}\n"
                     f"Original: {source or '(no indicado)'}\n\n{message}\n")
    with authenticated_smtp(settings) as smtp:
        smtp.send_message(mail)


def deliver_pending(db, *, limit=10, seconds=45):
    result = {"sent": 0, "retry": 0, "configured": False}
    settings = smtp_settings()
    if not settings:
        return result
    result["configured"] = True
    if not db.autocommit or db.info.transaction_status != TransactionStatus.IDLE:
        raise RuntimeError("Bug report delivery requires committed, idle outbox access")
    if not db.execute("SELECT pg_try_advisory_lock(%s)", (LOCK,)).fetchone()[0]:
        result["overlap"] = True
        return result
    deadline = time.monotonic() + seconds
    try:
        for _ in range(limit):
            if time.monotonic() >= deadline:
                break
            # Claim commits before SMTP. A worker restart leaves a five-minute
            # lease; the next timer retries rather than losing the message.
            with db.transaction():
                row = db.execute("""WITH candidate AS (
                    SELECT id FROM bug_report WHERE
                      (status='queued' AND next_attempt_at<=now()) OR
                      (status='sending' AND leased_until<now())
                    ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED
                  ) UPDATE bug_report b SET status='sending',attempts=attempts+1,
                    leased_until=now()+interval '5 minutes'
                  FROM candidate c WHERE b.id=c.id
                  RETURNING b.id,b.message,b.reply_email,b.page_path,b.source_document_id""").fetchone()
            if not row:
                break
            try:
                send(row, settings)
            except Exception as exc:
                db.execute("""UPDATE bug_report SET status='queued',leased_until=NULL,
                  next_attempt_at=now()+make_interval(secs=>least(21600,900*power(2,least(attempts-1,5)))::int),
                  delivery_error=%s WHERE id=%s""", (type(exc).__name__, row[0]))
                result["retry"] += 1
            else:
                db.execute("UPDATE bug_report SET status='sent',sent_at=now(),leased_until=NULL,delivery_error=NULL WHERE id=%s", (row[0],))
                result["sent"] += 1
    finally:
        db.execute("SELECT pg_advisory_unlock(%s)", (LOCK,))
    return result
