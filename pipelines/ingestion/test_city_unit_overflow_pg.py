"""Two complete retained ZIPs publish all native prices after unit recovery."""
import os
import unittest
import zipfile
from datetime import date
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from psycopg.pq import TransactionStatus

from . import city_reports
from . import test_city_publication as publication_tests
from .resumable_inputs import WorkDeferred


DATA = Path(__file__).parent / 'testdata/city_unit_overflow_202201'
PARENTS = (
    ('jan3', date(2022,1,3), '9b7bbbcefbbddd8c023a100ea3db3032214050f44a9cef2bc9a20aabfb953878',
     'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/sipsa-03-01-2022.zip', 15, 623),
    ('jan4', date(2022,1,4), '6af11307e0ffdb6c98b36071ef134ad32110e07a4c82d6e72f2313537d23029f',
     'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/sipsa-04-01-2022.zip', 11, 1239),
)
CHILDREN = {
    '867232775a722b2a3d2c3c40307e2d892fe7edbb9a4e634780d85ff9e11d1943': 56,
    'b194d4270d98bfc32414526e46cc75db54495957bf51805b01ca8867b9ae2156': 106,
    '8440cada34d16f78dd1f8ca024a4201c39a87511756a4e97b6d1ac6c8841c88c': 134,
    '81df4ba0c7453d4610e82644e52b12f9bb5a43f56bc1cfe94d2c7715156535dd': 120,
}


@unittest.skipUnless(os.environ.get('AGRO_CITY_POSTGRES_TEST') == '1',
                     'Explicit private PostgreSQL city publication opt-in')
class CityUnitOverflowPublication(unittest.TestCase):
    local_archive = staticmethod(publication_tests.CityPublicationPostgresTests.local_archive)

    def setUp(self):
        publication_tests.CityPublicationPostgresTests.setUp(self)
        self.assertIsNone(self.db.execute('SELECT inet_server_addr()').fetchone()[0])
        self.assertTrue(self.db.info.host.startswith('/tmp/agro-'))
        self.parents = []
        for label,day,digest,url,members,count in PARENTS:
            body = (DATA/f'official-{label}.zip').read_bytes()
            self.assertEqual(sha256(body).hexdigest(),digest)
            with zipfile.ZipFile(DATA/f'official-{label}.zip') as bundle:
                self.assertEqual(len(bundle.infolist()),members)
                self.assertEqual(sum(len(list(city_reports.parse_city_pdf(bundle.read(member),day)))
                                     for member in bundle.infolist()),count)
            self.parents.append((label,day,digest,url,body,members,count))

    def publish(self, item):
        label,day,digest,url,body,_,_ = item
        self.local_archive(self.db,url,body,'city-zip')
        return city_reports.publish_city_zip(self.db,body,digest,url,day)

    def test_two_whole_official_zips_publish_1862_and_replay_idempotently(self):
        self.assertEqual([self.publish(item) for item in self.parents],[623,1239])
        self.assertEqual(self.db.execute('SELECT count(*) FROM regional_price').fetchone()[0],1862)
        self.assertEqual(self.db.execute('SELECT count(*) FROM regional_classification').fetchone()[0],1862)
        self.assertEqual(self.db.execute('SELECT count(*) FROM published_regional_price').fetchone()[0],1862)
        self.assertEqual(self.db.execute('SELECT count(*) FROM city_pdf_publication_conflict').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM source_archive_member').fetchone()[0],26)
        for did,count in CHILDREN.items():
            self.assertEqual(self.db.execute('SELECT count(*) FROM regional_price WHERE document_id=%s',
                                             (did,)).fetchone()[0],count)
        self.assertEqual(self.db.execute('SELECT min_price,max_price,quantity,source_unit FROM regional_price '
            "WHERE document_id=%s AND source_locator='PDF page 1,table 1,row 29,round 1'",
            ('867232775a722b2a3d2c3c40307e2d892fe7edbb9a4e634780d85ff9e11d1943',)).fetchone(),
            (Decimal(40000),Decimal(40000),Decimal(25),'Unidad 454 Gr'))
        attempts_before=self.db.execute('SELECT count(*) FROM pg_temp.city_insert_attempt').fetchone()[0]
        self.assertEqual([self.publish(item) for item in self.parents],[623,1239])
        self.assertEqual(self.db.execute('SELECT count(*) FROM regional_price').fetchone()[0],1862)
        self.assertEqual(self.db.execute('SELECT count(*) FROM pg_temp.city_insert_attempt').fetchone()[0],attempts_before)

    def test_old_review_retained_and_deferred_parent_resumes_without_false_complete(self):
        jan4=self.parents[1]
        self.local_archive(self.db,jan4[3],jan4[4],'city-zip')
        self.db.execute('INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records) '
                        'VALUES(%s,%s,%s,0)',(jan4[2],'city-v7','city-review:retained-old-evidence'))
        original=city_reports.time.monotonic
        with patch.object(city_reports.time,'monotonic',side_effect=lambda:
            100 if self.db.execute("SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s "
                                   "AND processor_version=%s AND step LIKE 'city-member:%%'",
                                   (jan4[2],city_reports.VERSION)).fetchone()[0] else 0):
            from .worker import RUN_DEADLINE
            token=RUN_DEADLINE.set(50)
            try:
                with self.assertRaises(WorkDeferred):self.publish(jan4)
            finally:RUN_DEADLINE.reset(token)
        self.assertEqual(self.db.execute('SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s '
            "AND processor_version=%s AND step LIKE 'city-member:%%'",
            (jan4[2],city_reports.VERSION)).fetchone()[0],1)
        self.assertGreater(self.db.execute('SELECT count(*) FROM regional_price').fetchone()[0],0)
        self.assertLess(self.db.execute('SELECT count(*) FROM regional_price').fetchone()[0],1239)
        self.assertEqual(self.publish(jan4),1239)
        self.assertEqual(self.db.execute('SELECT count(*) FROM regional_price').fetchone()[0],1239)
        self.assertEqual(self.db.execute('SELECT count(*) FROM ingestion_checkpoint WHERE document_id=%s '
            "AND processor_version='city-v7' AND step='city-review:retained-old-evidence'",
            (jan4[2],)).fetchone()[0],1)
        self.assertEqual(self.db.info.transaction_status,TransactionStatus.IDLE)


if __name__=='__main__':unittest.main()
