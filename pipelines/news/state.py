"""Durable discovery backlog and immutable publication/first-seen timestamps."""
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

def stamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

class State:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=1)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS source_state(source TEXT PRIMARY KEY, last_attempt TEXT, last_success TEXT, result TEXT);
            CREATE TABLE IF NOT EXISTS candidates(url TEXT PRIMARY KEY, source TEXT NOT NULL, first_seen TEXT NOT NULL,
                headline TEXT, date_hint TEXT, checked_at TEXT, next_attempt TEXT, attempts INTEGER NOT NULL DEFAULT 0, outcome TEXT);
            CREATE TABLE IF NOT EXISTS stories(id TEXT PRIMARY KEY, url TEXT UNIQUE NOT NULL, source TEXT NOT NULL, record TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS revisions(id INTEGER PRIMARY KEY, story_id TEXT, changed_at TEXT, previous TEXT);
            CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, started_at TEXT, finished_at TEXT, report TEXT);
            CREATE TABLE IF NOT EXISTS runner_lock(id INTEGER PRIMARY KEY CHECK(id=1), token TEXT, expires_at TEXT);
            CREATE TABLE IF NOT EXISTS host_backoff(host TEXT PRIMARY KEY, until_epoch REAL NOT NULL);
        ''')

    def close(self): self.db.close()

    def backoffs(self):
        return dict(self.db.execute('SELECT host,until_epoch FROM host_backoff'))

    def save_backoffs(self, values):
        self.db.executemany('INSERT OR REPLACE INTO host_backoff VALUES(?,?)', values.items())
        self.db.commit()

    @contextmanager
    def lock(self, duration_hours=6):
        token = hashlib.sha256(stamp().encode()).hexdigest()
        now = datetime.now(timezone.utc)
        try:
            self.db.execute('BEGIN IMMEDIATE')
            row = self.db.execute('SELECT expires_at FROM runner_lock WHERE id=1').fetchone()
            if row and datetime.fromisoformat(row[0]) > now: raise RuntimeError('Another news run holds the state lease')
            self.db.execute('INSERT OR REPLACE INTO runner_lock VALUES(1,?,?)', (token,(now+timedelta(hours=duration_hours)).isoformat()))
            self.db.commit()
        except Exception:
            self.db.rollback(); raise
        try: yield
        finally:
            self.db.execute('DELETE FROM runner_lock WHERE id=1 AND token=?', (token,)); self.db.commit()

    def checkpoint(self, source):
        row = self.db.execute('SELECT last_success FROM source_state WHERE source=?', (source,)).fetchone()
        return row[0] if row else None

    def finish_source(self, source, success, report, started_at):
        previous = self.checkpoint(source)
        self.db.execute('INSERT OR REPLACE INTO source_state VALUES(?,?,?,?)',
                        (source, stamp(), started_at if success else previous, json.dumps(report)))
        self.db.commit()

    def enqueue(self, source, entries):
        self.db.executemany('INSERT OR IGNORE INTO candidates(url,source,first_seen,headline,date_hint) VALUES(?,?,?,?,?)',
            [(e['url'],source,stamp(),e.get('headline',''),e.get('listing_date_hint')) for e in entries])
        self.db.commit()

    def pending(self, source, limit):
        # The backlog outlives a discovery watermark; a successful listing scan
        # never makes unprocessed article URLs disappear.
        rows = self.db.execute('''SELECT url FROM candidates WHERE source=? AND (next_attempt IS NULL OR next_attempt<=?)
            AND (outcome IS NULL OR outcome IN ('error','retry'))
            ORDER BY attempts ASC, first_seen ASC, rowid ASC LIMIT ?''', (source,stamp(),limit)).fetchall()
        return [r[0] for r in rows]

    def rechecks(self, source, limit):
        records = self.stories(source)
        now = datetime.now(timezone.utc)
        return [s['original_url'] for s in records if s.get('decision') == 'include' and
                s.get('display_expires_at') and datetime.fromisoformat(s['display_expires_at']) > now and
                s.get('review_at') and datetime.fromisoformat(s['review_at']) <= now and
                s.get('status') not in ('retracted','superseded','corrected')][:limit]

    def candidate_result(self, url, outcome, retry_seconds=0):
        next_attempt = (datetime.now(timezone.utc)+timedelta(seconds=retry_seconds)).isoformat() if retry_seconds else None
        self.db.execute('UPDATE candidates SET checked_at=?,next_attempt=?,attempts=attempts+1,outcome=? WHERE url=?',
                        (stamp(),next_attempt,outcome,url)); self.db.commit()

    def backlog(self, source):
        return self.db.execute("SELECT COUNT(*) FROM candidates WHERE source=? AND (outcome IS NULL OR outcome IN ('error','retry'))", (source,)).fetchone()[0]

    def upsert(self, source, record):
        url = record['canonical_url']
        row = self.db.execute('SELECT record FROM stories WHERE url=?', (url,)).fetchone()
        previous = json.loads(row[0]) if row else None
        record['id'] = hashlib.sha256(url.encode()).hexdigest()[:24]
        record['first_seen_at'] = previous['first_seen_at'] if previous else stamp()
        record['retrieved_at'] = stamp()
        if previous:
            for k in ('published_at','date_precision'):
                if previous.get(k): record[k] = previous[k]
            unchanged = (previous['content_sha256'] == record['content_sha256'] and
                         previous['headline_sha256'] == record['headline_sha256'])
            if unchanged and record['language']['accepted'] and not record['date_conflict']:
                for k in ('decision','status','classification','factual_label_es','colombia_relevance_es','story_kind',
                          'display_expires_at','review_at','event_id','priority','classified_by','classified_at',
                          'classification_method','primary_category','crops','inputs','transmission_channel',
                          'impact_is_inference','relevance_kind'):
                    if k in previous: record[k] = previous[k]
                if record.get('review_at') and datetime.fromisoformat(record['review_at']) < datetime.now(timezone.utc):
                    record['review_at'] = (datetime.now(timezone.utc)+timedelta(hours=24)).isoformat()
            else:
                self.db.execute('INSERT INTO revisions(story_id,changed_at,previous) VALUES(?,?,?)',
                                (record['id'],stamp(),json.dumps(previous,ensure_ascii=False)))
                record.update(decision='review',status='review',review_reason='source_content_changed',
                              prior_content_sha256=previous['content_sha256'])
        self.save(source, record)
        return record

    def save(self, source, record):
        self.db.execute('INSERT OR REPLACE INTO stories VALUES(?,?,?,?)',
            (record['id'],record['canonical_url'],source,json.dumps(record,ensure_ascii=False)))
        self.db.commit()

    def stories(self, source=None):
        query, args = ('SELECT record FROM stories WHERE source=?', (source,)) if source else ('SELECT record FROM stories', ())
        return [json.loads(r[0]) for r in self.db.execute(query,args)]

    def finish_run(self, run_id, started_at, report):
        self.db.execute('INSERT OR REPLACE INTO runs VALUES(?,?,?,?)', (run_id,started_at,stamp(),json.dumps(report,ensure_ascii=False)))
        self.db.commit()
