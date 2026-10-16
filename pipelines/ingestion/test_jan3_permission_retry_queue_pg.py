"""Maintained TEMP-PG regression for narrow Jan 3 permission-error eligibility.

Opt-in only: AGRO_CITY_POSTGRES_TEST=1 and JAN3_QUEUE_TEST_DSN/SOCKET are
provided by the separately reviewed owned-PG operator. Never uses worker's
ambient connector. Negative cases compare the exact-error candidate against
the same mutated asset under its ordinary error, proving the exception adds no
eligibility without hiding unrelated generic queue paths.
"""
import os
import unittest

from pipelines.ingestion import worker, queue_plan
from pipelines.ingestion import city_source_adjudication as engine
from pipelines.ingestion import test_city_source_adjudication_pg as city_fixture
from psycopg.types.json import Jsonb

URL='https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/bol-reg-03-01-2023.zip'
DID='220e0d23060a337f4307b5f93e729fa4f777e89e4373228cb6552a68b8da2c04'
ERROR='InsufficientPrivilege: permission denied for table source_document'
BASELINE_ERROR='ValueError: retained candidate does not match Jan 3 retry exception'
SOCKET_PREFIXES=('/tmp/agro-jan3-queue-', '/tmp/agro-sep2013-worker-')


def _guarded_connector():
    # Installed only after setUp validates the exact operator DSN/socket pair.
    # Verify the connected server on every call as a second guard.
    import psycopg
    dsn=os.environ['JAN3_QUEUE_TEST_DSN']
    expected_socket=os.environ['JAN3_QUEUE_TEST_SOCKET']
    from psycopg.conninfo import conninfo_to_dict
    parsed=conninfo_to_dict(dsn)
    if (parsed.get('host') != expected_socket or not str(parsed.get('port','')).isdigit()
            or parsed.get('dbname') != 'postgres' or parsed.get('user') != 'postgres'
            or parsed.get('hostaddr') or parsed.get('service')):
        raise RuntimeError('refusing DSN outside the exact owned Unix-socket PostgreSQL target')
    conn=psycopg.connect(dsn,autocommit=True,
      options='-c statement_timeout=30000 -c lock_timeout=2000 -c idle_in_transaction_session_timeout=15000')
    try:
        version=conn.execute('SHOW server_version').fetchone()[0]
        server=conn.execute('SELECT inet_server_addr()').fetchone()[0]
        if str(conn.info.host)!=expected_socket or server is not None or not version.startswith('16.'):
            raise RuntimeError('refusing connector outside the exact owned Unix-socket PostgreSQL 16 server')
        return conn
    except BaseException:
        conn.close()
        raise


@unittest.skipUnless(os.environ.get('AGRO_CITY_POSTGRES_TEST')=='1',
                     'Requires root GO and exact owned Unix-socket TEMP PostgreSQL 16')
class Jan3PermissionRetryQueueMaintainedTests(unittest.TestCase):
    def setUp(self):
        # Fail closed before patching worker.connect or instantiating a fixture.
        dsn=os.environ.get('JAN3_QUEUE_TEST_DSN','')
        sock=os.environ.get('JAN3_QUEUE_TEST_SOCKET','')
        from psycopg.conninfo import conninfo_to_dict
        parsed=conninfo_to_dict(dsn)
        if (not any(sock.startswith(prefix) for prefix in SOCKET_PREFIXES)
                or parsed.get('host') != sock or not str(parsed.get('port','')).isdigit()
                or parsed.get('dbname') != 'postgres' or parsed.get('user') != 'postgres'
                or parsed.get('hostaddr') or parsed.get('service')):
            raise RuntimeError('missing exact Jan3 owned Unix-socket DSN guard')
        from unittest.mock import patch
        self.connector_patch=patch.object(worker,'connect',_guarded_connector)
        self.connector_patch.start()
        self.addCleanup(self.connector_patch.stop)
        self.fixture=city_fixture.ExactCmaPrivatePg()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.db=self.fixture.db
        self.assertEqual((self.fixture.url,self.fixture.parent),(URL,DID))
        self.target=(URL,'city-zip',engine.date(2023,1,3))
        self.source_row=self.db.execute(
            'SELECT source_url,metadata,content FROM source_document WHERE id=%s',(DID,)
        ).fetchone()
        self._set_asset(error=BASELINE_ERROR)
        self.baseline_rows=set(queue_plan.repair_candidates(self.db,8))

    def _set_asset(self,*,url=URL,document_id=DID,day='2023-01-03',version=None,
                   status='review',records=0,error=ERROR,checked='7 hours',attempts=2):
        self.db.execute("""UPDATE ingestion_asset SET url=%s,kind='city-zip',observed_on=%s,
          document_id=%s,processor_version=%s,status=%s,records=%s,error=%s,
          checked_at=now()-(%s::interval),attempts=%s WHERE kind='city-zip' """,
          (url,day,document_id,version or engine.VERSION,status,records,error,checked,attempts))
        self.db.execute('UPDATE source_document SET source_url=%s,metadata=%s,content=%s WHERE id=%s',
          (self.source_row[0],Jsonb(self.source_row[1]),self.source_row[2],DID))

    def _rows(self):
        return list(queue_plan.repair_candidates(self.db,8))

    def test_exact_permission_error_is_eligible_once_after_cooldown_and_attempt_cap(self):
        self._set_asset(error=ERROR)
        rows=self._rows()
        self.assertNotIn(self.target,self.baseline_rows)
        self.assertEqual(rows.count(self.target),1)
        self.assertEqual(set(rows)-self.baseline_rows,{self.target})
        self._set_asset(error=ERROR,checked='5 hours')
        self.assertEqual(set(self._rows()),self.baseline_rows)
        self._set_asset(error=ERROR,attempts=3)
        self.assertEqual(set(self._rows()),self.baseline_rows)

    def test_wrong_exact_case_fields_add_no_rows_to_full_result_set(self):
        cases=(
          ('url',dict(url='https://invalid.example/wrong.zip')),
          ('document id',dict(document_id='f'*64)),
          ('date',dict(day='2023-01-04')),
          ('status',dict(status='failed')),
          ('error',dict(error='InsufficientPrivilege: permission denied for table source_ocr_task')),
          ('records',dict(records=1)),
        )
        for name,kwargs in cases:
            with self.subTest(case=name):
                baseline_kwargs={**kwargs,'error':BASELINE_ERROR}
                self._set_asset(**baseline_kwargs)
                same_mutated_baseline=set(self._rows())
                self._set_asset(**kwargs)
                self.assertEqual(set(self._rows()),same_mutated_baseline)
        # The narrow exception also requires the exact immutable source identity.
        for name,sql in (
          ('source URL',"UPDATE source_document SET source_url='https://invalid.example/wrong.zip' WHERE id=%s"),
          ('retention',"UPDATE source_document SET metadata=metadata || '{\"retention\":\"temporary\"}'::jsonb WHERE id=%s"),
          ('filename',"UPDATE source_document SET metadata=metadata || '{\"original_filename\":\"wrong.zip\"}'::jsonb WHERE id=%s"),
        ):
            with self.subTest(case=name):
                self._set_asset(error=BASELINE_ERROR)
                self.db.execute(sql,(DID,))
                same_mutated_baseline=set(self._rows())
                self.db.execute('UPDATE ingestion_asset SET error=%s WHERE kind=%s',(ERROR,'city-zip'))
                self.assertEqual(set(self._rows()),same_mutated_baseline)

    def test_wrong_version_remains_eligible_through_existing_generic_route(self):
        self._set_asset(version='city-v8',error=BASELINE_ERROR)
        generic_rows=self._rows()
        self.assertEqual(generic_rows.count(self.target),1)
        self.assertIn(self.target,generic_rows)


if __name__=='__main__':
    unittest.main(verbosity=2)
