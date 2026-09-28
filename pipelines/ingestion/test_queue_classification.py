"""A link in a context workbook cannot demote an already typed price source."""
import os
import unittest
from datetime import date
from . import worker


@unittest.skipUnless(os.environ.get('AGRO_QUEUE_POSTGRES_TEST') == '1', 'Isolated local PostgreSQL opt-in')
class QueueClassificationTests(unittest.TestCase):
    def setUp(self):
        self.db = worker.connect()
        self.addCleanup(self.db.close)
        self.assertTrue(self.db.info.host.startswith('/tmp/agro-'))
        self.db.execute("SET client_encoding='UTF8'")
        self.db.execute('SET search_path=pg_temp')
        self.db.execute('CREATE TEMP TABLE ingestion_asset(url text PRIMARY KEY, kind text, observed_on date, status text DEFAULT \'pending\', records integer DEFAULT 0)')

    def test_context_hyperlink_preserves_typed_price_kind_date_status_and_rows(self):
        for kind in ['inputs-pdf', 'daily-pdf', 'monthly-pdf', 'milk-pdf', 'dane-weekly-pdf']:
            worker.queue(self.db, kind, kind, date(2019, 2, 28))
            self.db.execute("UPDATE ingestion_asset SET status='complete',records=14366 WHERE url=%s", (kind,))
            before = self.db.execute('SELECT * FROM ingestion_asset WHERE url=%s', (kind,)).fetchone()
            worker.queue(self.db, kind, 'context-pdf')
            worker.queue(self.db, kind, 'context-pdf', date(2026, 8, 31))
            self.assertEqual(self.db.execute('SELECT * FROM ingestion_asset WHERE url=%s', (kind,)).fetchone(), before)

    def test_specific_discovery_repairs_previously_demoted_source_without_deleting_state(self):
        worker.queue(self.db, 'old', 'context-pdf')
        self.db.execute("UPDATE ingestion_asset SET status='failed',records=91 WHERE url='old'")
        worker.queue(self.db, 'old', 'inputs-pdf', date(2016, 2, 29))
        worker.queue(self.db, 'old', 'context-pdf')
        self.assertEqual(self.db.execute("SELECT kind,observed_on,status,records FROM ingestion_asset WHERE url='old'").fetchone(), ('inputs-pdf', date(2016, 2, 29), 'failed', 91))

    def test_new_context_links_are_retained_and_specific_dates_can_fill_missing_dates(self):
        worker.queue(self.db, 'context', 'context-pdf')
        worker.queue(self.db, 'context', 'context-pdf')
        worker.queue(self.db, 'priced', 'inputs-pdf')
        worker.queue(self.db, 'priced', 'inputs-pdf', date(2019, 2, 28))
        self.assertEqual(self.db.execute('SELECT count(*) FROM ingestion_asset').fetchone()[0], 2)
        self.assertEqual(self.db.execute("SELECT observed_on FROM ingestion_asset WHERE url='priced'").fetchone()[0], date(2019, 2, 28))

if __name__ == '__main__':
    unittest.main()
