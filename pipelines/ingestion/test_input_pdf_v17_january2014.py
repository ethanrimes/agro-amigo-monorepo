"""Source-bound PostgreSQL regression for the January 2014 input PDF."""
from __future__ import annotations

import gzip
import hashlib
import importlib
import importlib.util
import json
import os
import re
import sys
import unittest
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import psycopg
from psycopg.types.json import Jsonb

HERE = Path(__file__).resolve().parent
REPO = next(parent for parent in HERE.parents if (parent / 'pipelines/ingestion/schema.sql').is_file())
TD = HERE / 'testdata/input_pdf_v17_jan2014'
MANIFEST = json.loads((TD / 'JANUARY_PRIVATE_CASE_MANIFEST.json').read_text())
CASE = MANIFEST
DID = CASE['document_id']
URL = CASE['url']
DAY = date.fromisoformat(CASE['observed_on'])
XLS_DID = CASE['consolidated_source']['document_id']
CANDIDATE_PATH = HERE / "input_pdf_v17_replay.py"
MODULE_KEY = 'pipelines.ingestion.input_pdf_v17_replay'


def read_gz(name):
    with gzip.open(TD / name, 'rt', encoding='utf-8') as stream:
        return json.load(stream)


def old_rows():
    rows = read_gz('2014-01-31_V14_FULL_VECTOR_FIRST_B.json.gz')['rows']
    return [(r['source_locator'], r['series'], date.fromisoformat(r['observed_on']),
             r['product_name'], r['market_name'], r['unit'], Decimal(str(r['price'])),
             Decimal(str(r['change_percent'])) if r['change_percent'] is not None else None,
             r['details']) for r in rows]


def current_history_rows():
    rows = read_gz('CURRENT_KEYS_exact_historical_witnesses_FIRST_I.json.gz')
    return [(r['document_id'], r['source_locator'], r['series'], date.fromisoformat(r['observed_on']),
             r['product_name'], r['market_name'], r['unit'], Decimal(str(r['price'])),
             Decimal(str(r['change_percent'])) if r['change_percent'] is not None else None,
             r['details']) for r in rows]


def input_rows():
    rows = read_gz('CURRENT_KEYS_input_municipal_price_FIRST_I.json.gz')
    return [(r['id'], r['department'], date.fromisoformat(r['observed_on']), r['name'], r['category'],
             r['presentation'], Decimal(str(r['price'])), r['document_id'], r['source_locator'],
             r['brand'], r['registration'], r['product_line'], r['municipality']) for r in rows]


def revision_rows():
    rows = read_gz('CURRENT_KEYS_input_revision_FIRST_K.json.gz')
    return [(r['id'], r['department'], r['municipality'], date.fromisoformat(r['observed_on']),
             datetime.fromisoformat(r['retrieved_at'])) for r in rows]


def checkpoint_rows():
    rows = read_gz('CURRENT_KEYS_checkpoints_FIRST_I.json.gz')
    return [(r['document_id'], r['processor_version'], r['step'], int(r['records'])) for r in rows]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_number(value):
    if value is None:
        return None
    number = Decimal(str(value))
    return '0' if number == 0 else format(number.normalize(), 'f')


def vector_hash(rows):
    payload = []
    for row in rows:
        payload.append([row[0], row[1], row[2].isoformat() if hasattr(row[2], 'isoformat') else str(row[2]),
                        row[3], row[4], row[5], canonical_number(row[6]), canonical_number(row[7]), row[8]])
    payload.sort(key=lambda row: row[0])
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def canonical_projection(rows):
    def primitive(value, field=None):
        # JSON export prices are decimal strings; PostgreSQL NUMERIC values are Decimal.
        # Normalize only the declared numeric business field, never text identifiers/labels.
        if field == 'price':
            return canonical_number(value)
        if hasattr(value, 'isoformat'):
            return value.isoformat()
        if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
            return canonical_number(value)
        if isinstance(value, dict):
            return {k: primitive(v, k) for k, v in value.items()}
        if isinstance(value, (tuple, list)):
            return [primitive(v) for v in value]
        return value
    return sorted((primitive(dict(row)) for row in rows),
                  key=lambda r: json.dumps(r, sort_keys=True, ensure_ascii=False))


def load_candidate():
    spec = importlib.util.spec_from_file_location(MODULE_KEY, CANDIDATE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AlteredResult:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class AlteredReadOnlyDB:
    """Return a deliberately corrupted read view without mutating the fixture."""
    def __init__(self, conn, mode):
        self.conn, self.mode = conn, mode

    def execute(self, query, params=None):
        result = self.conn.execute(query, params)
        if params and params[0] == DID and 'FROM source_document WHERE id=%s' in query:
            row = result.fetchone()
            if row is None:
                return AlteredResult(None)
            values = list(row)
            if query.lstrip().startswith('SELECT kind,source_url,media_type,page_count,content,metadata'):
                if self.mode == 'source-body':
                    values[4] = bytes(values[4]) + b'changed'
                elif self.mode == 'source-metadata':
                    values[5] = {**values[5], 'original_filename': 'different.pdf'}
                elif self.mode == 'source-url':
                    values[1] = 'https://example.invalid/not-the-registered-source.pdf'
            elif query.lstrip().startswith('SELECT title,publisher,reference_period'):
                values[0] = 'different source title'
            return AlteredResult(tuple(values))
        if self.mode == 'asset-pointer' and params and params[0] == URL and 'FROM ingestion_asset WHERE url=%s' in query:
            row = result.fetchone()
            if row is None:
                return AlteredResult(None)
            values = list(row)
            values[2] = '0' * 64
            return AlteredResult(tuple(values))
        return result


@contextmanager
def candidate_module(module):
    package = importlib.import_module('pipelines.ingestion')
    previous = sys.modules.get(MODULE_KEY)
    previous_attr = getattr(package, 'input_pdf_v17_replay', None)
    sys.modules[MODULE_KEY] = module
    package.input_pdf_v17_replay = module
    try:
        yield
    finally:
        if previous is None:
            sys.modules.pop(MODULE_KEY, None)
        else:
            sys.modules[MODULE_KEY] = previous
        if previous_attr is None:
            delattr(package, 'input_pdf_v17_replay')
        else:
            package.input_pdf_v17_replay = previous_attr


class January2014RetainedInputPDF(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.candidate = load_candidate()
        cls.conn = psycopg.connect(os.environ['AGRO_INPUT_JAN2014_TEST_DSN'], autocommit=True)
        socket_path = str(cls.conn.info.host)
        if (not socket_path.startswith("/tmp/agro-input-jan2014-")
                or cls.conn.execute('SELECT inet_server_addr()').fetchone()[0] is not None
                or not cls.conn.execute('SHOW server_version').fetchone()[0].startswith('16.')
                or cls.conn.execute('SHOW TimeZone').fetchone()[0] != 'UTC'
                or cls.conn.execute('SELECT current_user').fetchone()[0] != 'postgres'
                or cls.conn.execute('SELECT count(*) FROM source_document').fetchone()[0] != 0):
            cls.conn.close()
            raise AssertionError('expected an empty owned PostgreSQL 16 full-schema database over its private Unix socket')
        cls.inputs, cls.worker = importlib.import_module('pipelines.ingestion.inputs'), importlib.import_module('pipelines.ingestion.worker')
        cls.pdf = (TD / '2014-01-31_original.pdf').read_bytes()
        cls.xlsx = (TD / '2013-2020_consolidated.xlsx').read_bytes()
        if (len(cls.pdf) != 2561852 or hashlib.sha256(cls.pdf).hexdigest() != DID
                or len(cls.xlsx) != 54065498 or hashlib.sha256(cls.xlsx).hexdigest() != XLS_DID):
            raise AssertionError('source fixture bytes do not match exact DANE DIDs')
        cls.v14 = old_rows()
        cls.history = current_history_rows()
        cls.current = input_rows()
        cls.revisions = revision_rows()
        cls.checkpoints = checkpoint_rows()
        if (len(cls.v14) != 5639 or vector_hash(cls.v14) != '71bc5a4fc6d1cbc7675b08bb54b5b20bfbc70839fc62f36e414172468a45fcea'
                or len(cls.history) != 5639 or len(cls.current) != 5639 or len(cls.revisions) != 5639
                or len(cls.checkpoints) != 17393):
            raise AssertionError('captured v14/current-key fixture shapes or source pins differ')
        cls.seed_sources_and_history()
        cls.seed_live_projection()
        cls.before = cls.snapshot()
        # The fixture's own current published projection must match the production snapshot.
        expected = read_gz('CURRENT_KEYS_published_input_municipal_price_FIRST_I.json.gz')
        actual = cls.conn.execute('SELECT id,department,observed_on,name,category,presentation,price,document_id,source_locator,brand,registration,product_line,municipality FROM published_input_municipal_price ORDER BY id,department,municipality,observed_on').fetchall()
        expected_projection = canonical_projection(expected)
        actual_projection = canonical_projection([dict(zip(('id','department','observed_on','name','category','presentation','price','document_id','source_locator','brand','registration','product_line','municipality'), row)) for row in actual])
        if actual_projection != expected_projection:
            raise AssertionError('seeded full-day published projection differs from the exact 5,639-row production witness')

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, 'conn', None):
            cls.conn.close()

    @classmethod
    def _executemany(cls, sql, rows):
        # psycopg 3 exposes executemany on a cursor, not on Connection.
        with cls.conn.cursor() as cursor:
            cursor.executemany(sql, rows)

    @classmethod
    def seed_sources_and_history(cls):
        sources = [CASE['source'], CASE['consolidated_source']]
        bodies = {DID: cls.pdf, XLS_DID: cls.xlsx}
        for source in sources:
            cls.conn.execute('''INSERT INTO source_document
                (id,title,publisher,source_url,media_type,kind,reference_period,retrieved_at,page_count,content,metadata)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (source['document_id'] if 'document_id' in source else DID,
                 source['title'], source['publisher'], source['source_url'], source['media_type'], source['kind'],
                 source['reference_period'], datetime.fromisoformat(source['retrieved_at']), source['page_count'],
                 bodies[source['document_id'] if 'document_id' in source else DID], Jsonb(source['metadata'])))
        cls.conn.execute('''INSERT INTO ingestion_asset
            (url,kind,observed_on,document_id,status,processor_version,records,error)
            VALUES(%s,'inputs-pdf',%s,%s,'failed','inputs-pdf-v17',5639,%s)''',
            (URL, DAY, DID, 'ValueError: Retained input original identity/bytes mismatch'))
        # Old v14 source rows remain immutable; the 1,503 current Excel winners are independent history.
        cls._executemany('''INSERT INTO historical_price
            (document_id,source_locator,series,observed_on,product_name,market_name,unit,price,change_percent,details)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(document_id,source_locator) DO NOTHING''',
            [(DID, *row[:8], Jsonb(row[8])) for row in cls.v14])
        cls._executemany('''INSERT INTO historical_price
            (document_id,source_locator,series,observed_on,product_name,market_name,unit,price,change_percent,details)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(document_id,source_locator) DO NOTHING''',
            [(r[0], *r[1:9], Jsonb(r[9])) for r in cls.history])
        cls._executemany('''INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records)
            VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING''', cls.checkpoints)
        # Confirm no current-history witness overwrote any captured old PDF row.
        stored_old = cls.conn.execute('''SELECT source_locator,series,observed_on,product_name,market_name,unit,price,change_percent,details
            FROM historical_price WHERE document_id=%s AND details->>'parser_version'='inputs-pdf-v14' ORDER BY source_locator''', (DID,)).fetchall()
        if vector_hash(stored_old) != '71bc5a4fc6d1cbc7675b08bb54b5b20bfbc70839fc62f36e414172468a45fcea':
            raise AssertionError('seeded v14 PDF cohort differs from captured full vector')

    @classmethod
    def seed_live_projection(cls):
        cls._executemany('''INSERT INTO input_municipal_price
            (id,department,observed_on,name,category,presentation,price,document_id,source_locator,brand,registration,product_line,municipality)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''', cls.current)
        cls._executemany('''INSERT INTO input_revision(id,department,municipality,observed_on,retrieved_at)
            VALUES(%s,%s,%s,%s,%s)''', cls.revisions)

    @classmethod
    def snapshot(cls):
        source = cls.conn.execute('SELECT xmin::text,content,metadata,source_url,reference_period,page_count,retrieved_at FROM source_document WHERE id=%s', (DID,)).fetchone()
        asset = cls.conn.execute('SELECT kind,observed_on,document_id,status,processor_version,records,error,xmin::text FROM ingestion_asset WHERE url=%s', (URL,)).fetchone()
        oldcp = cls.conn.execute("SELECT records,xmin::text FROM ingestion_checkpoint WHERE document_id=%s AND processor_version='inputs-pdf-v14' AND step='inputs-pdf:published'", (DID,)).fetchone()
        oldrows = cls.conn.execute("SELECT source_locator||':'||xmin::text FROM historical_price WHERE document_id=%s AND details->>'parser_version'='inputs-pdf-v14' ORDER BY source_locator", (DID,)).fetchall()
        xlsrows = cls.conn.execute('SELECT source_locator||\':\'||xmin::text FROM historical_price WHERE document_id=%s ORDER BY source_locator', (XLS_DID,)).fetchall()
        current = cls.conn.execute('SELECT id,department,observed_on,name,category,presentation,price,document_id,source_locator,brand,registration,product_line,municipality FROM input_municipal_price ORDER BY id,department,municipality,observed_on').fetchall()
        revision = cls.conn.execute('SELECT id,department,municipality,observed_on,retrieved_at FROM input_revision ORDER BY id,department,municipality,observed_on').fetchall()
        published = cls.conn.execute('SELECT id,department,observed_on,name,category,presentation,price,document_id,source_locator,brand,registration,product_line,municipality FROM published_input_municipal_price ORDER BY id,department,municipality,observed_on').fetchall()
        return {'source_xmin': source[0], 'source_sha256': hashlib.sha256(source[1]).hexdigest(), 'source_metadata': source[2], 'source_url': source[3], 'source_period': str(source[4]), 'source_pages': source[5], 'source_retrieved_at': source[6].isoformat(), 'asset': asset, 'old_checkpoint': oldcp, 'old_xmins': oldrows, 'xlsx_xmins': xlsrows, 'current': canonical_projection([dict(zip(('id','department','observed_on','name','category','presentation','price','document_id','source_locator','brand','registration','product_line','municipality'), r)) for r in current]), 'revisions': [(r[0],r[1],r[2],r[3].isoformat(),r[4].isoformat()) for r in revision], 'published': canonical_projection([dict(zip(('id','department','observed_on','name','category','presentation','price','document_id','source_locator','brand','registration','product_line','municipality'), r)) for r in published])}

    def test_january_native_source_replay_preserves_current_projection(self):
        from pipelines.ingestion import ocr
        self.assertEqual(self.candidate.retained_v14_input_pdf(self.conn, URL, 'inputs-pdf', DAY, self.candidate.VERSION), self.pdf)
        for mode in ('source-body','source-metadata','source-url','asset-pointer'):
            with self.assertRaises(ValueError, msg=f'{mode} must fail closed'):
                self.candidate.retained_v14_input_pdf(AlteredReadOnlyDB(self.conn,mode),URL,'inputs-pdf',DAY,self.candidate.VERSION)
            self.assertEqual(self.snapshot(),self.before,f'{mode} negative probe changed seeded state')
        with candidate_module(self.candidate):
            self.conn.execute('SET ROLE agro_ingestor')
            try:
                # A failure after parsing/publication begins must roll back as one source transaction.
                with patch.object(self.worker, 'fetch_asset', side_effect=AssertionError('network access forbidden')) as fetch, \
                     patch.object(self.worker, 'archive', return_value=DID) as archive, \
                     patch.object(self.worker, 'project', side_effect=RuntimeError('private simulated publication interruption')), \
                     patch.object(ocr, 'transcribe', side_effect=AssertionError('OCR/provider access forbidden')) as transcribe, \
                     patch.object(ocr, 'scan_document', wraps=ocr.scan_document) as scan:
                    with self.assertRaisesRegex(RuntimeError, 'private simulated publication interruption'):
                        self.worker.process_asset(self.conn, URL, 'inputs-pdf', DAY)
                    fetch.assert_not_called()
                    archive.assert_called_once_with(self.conn, URL, self.pdf, 'inputs-pdf', DAY)
                    transcribe.assert_not_called()
                    scan.assert_called_once()
                self.assertEqual(self.conn.execute('SELECT count(*) FROM source_ocr_task WHERE document_id=%s',(DID,)).fetchone()[0],0)
                interrupted = self.snapshot()
                for key in self.before:
                    if key != 'asset':
                        self.assertEqual(interrupted[key], self.before[key], f'interrupted worker changed {key}')
                old_asset, pending_asset = self.before['asset'], interrupted['asset']
                self.assertEqual(pending_asset[:3], old_asset[:3])
                self.assertEqual(pending_asset[3], 'pending')
                self.assertEqual(pending_asset[4:7], old_asset[4:7])
                # The worker records a pending attempt before per-page cache commits; only its xmin may advance.
                self.assertEqual(self.conn.execute("SELECT count(*) FROM historical_price WHERE document_id=%s AND details->>'parser_version'='inputs-pdf-v17'",(DID,)).fetchone()[0],0)
                self.assertIsNone(self.conn.execute("SELECT 1 FROM ingestion_checkpoint WHERE document_id=%s AND processor_version='inputs-pdf-v17' AND step='inputs-pdf:published'",(DID,)).fetchone())
                with patch.object(self.worker, 'fetch_asset', side_effect=AssertionError('network access forbidden')) as fetch, \
                     patch.object(self.worker, 'archive', return_value=DID) as archive, \
                     patch.object(ocr, 'transcribe', side_effect=AssertionError('OCR/provider access forbidden')) as transcribe, \
                     patch.object(ocr, 'scan_document', wraps=ocr.scan_document) as scan:
                    count = self.worker.process_asset(self.conn, URL, 'inputs-pdf', DAY)
                    fetch.assert_not_called()
                    archive.assert_called_once_with(self.conn, URL, self.pdf, 'inputs-pdf', DAY)
                    transcribe.assert_not_called()
                    scan.assert_called_once()
                self.assertEqual(self.conn.execute('SELECT count(*) FROM source_ocr_task WHERE document_id=%s',(DID,)).fetchone()[0],0)
                self.assertEqual(self.conn.execute("SELECT count(*) FROM source_document WHERE metadata->>'parent_document_id'=%s AND kind='ocr-image'",(DID,)).fetchone()[0],0)
                self.assertEqual(self.conn.execute('SELECT count(*) FROM source_pdf_page WHERE document_id=%s',(DID,)).fetchone()[0],59)
                self.assertEqual(self.conn.execute('SELECT count(*) FROM source_ocr_scan WHERE document_id=%s',(DID,)).fetchone()[0],1)
                self.assertEqual(count, 5639)
                asset = self.conn.execute('SELECT status,processor_version,records,error FROM ingestion_asset WHERE url=%s',(URL,)).fetchone()
                self.assertEqual(asset,('complete','inputs-pdf-v17',5639,None))
                v17 = self.conn.execute("SELECT source_locator,series,observed_on,product_name,market_name,unit,price,change_percent,details FROM historical_price WHERE document_id=%s AND details->>'parser_version'='inputs-pdf-v17' ORDER BY source_locator",(DID,)).fetchall()
                self.assertEqual(len(v17),5639)
                self.assertEqual(vector_hash(v17),'9a41e5e3fce93d3fab54b7e6a9f50700f15fdbe2b5683dd6dfc0e1a7015ffe79')
                self.assertEqual(self.conn.execute("SELECT records FROM ingestion_checkpoint WHERE document_id=%s AND processor_version='inputs-pdf-v17' AND step='inputs-pdf:published'",(DID,)).fetchone(),(5639,))
                after = self.snapshot()
                self.assertEqual(after['source_xmin'],self.before['source_xmin'])
                self.assertEqual(after['source_sha256'],DID)
                self.assertEqual(after['source_metadata'],self.before['source_metadata'])
                self.assertEqual(after['old_checkpoint'],self.before['old_checkpoint'])
                self.assertEqual(after['old_xmins'],self.before['old_xmins'])
                self.assertEqual(after['xlsx_xmins'],self.before['xlsx_xmins'])
                self.assertEqual(after['revisions'],self.before['revisions'])
                # 1,503 consolidated-workbook winners retain their exact current business values and attribution.
                before_xls=[r for r in self.before['current'] if r['document_id']==XLS_DID]
                after_xls=[r for r in after['current'] if r['document_id']==XLS_DID]
                self.assertEqual(len(before_xls),1503)
                self.assertEqual(after_xls,before_xls)
                self.assertEqual(len(after['current']),5639)
                expected_pdf=[dict(r) for r in self.before['current'] if r['document_id']==DID]
                actual_pdf=[r for r in after['current'] if r['document_id']==DID]
                self.assertEqual(len(expected_pdf),4136)
                for row in expected_pdf:
                    row['source_locator']=re.sub(r'; inputs-pdf-v14$','; inputs-pdf-v17',row['source_locator'])
                self.assertEqual(actual_pdf,expected_pdf)
                self.assertEqual(after['published'],after['current'])
                # The next ordinary worker call may refetch conditionally; same body must be a no-op.
                with patch.object(self.worker,'fetch_asset',return_value=self.pdf) as fetch, \
                     patch.object(self.worker,'archive',return_value=DID) as archive, \
                     patch.object(ocr,'transcribe',side_effect=AssertionError('OCR/provider access forbidden')) as transcribe, \
                     patch.object(ocr,'scan_document',wraps=ocr.scan_document) as scan:
                    self.assertEqual(self.worker.process_asset(self.conn,URL,'inputs-pdf',DAY),0)
                    fetch.assert_called_once_with(self.conn,URL,force=False)
                    archive.assert_called_once_with(self.conn,URL,self.pdf,'inputs-pdf',DAY)
                    transcribe.assert_not_called()
                    scan.assert_not_called()
                no_op = self.snapshot()
                for key in after:
                    if key != 'asset':
                        self.assertEqual(no_op[key], after[key], f'same-body refetch changed {key}')
                # Normal refresh records checked_at/attempts, advancing only the asset xmin.
                self.assertEqual(no_op['asset'][:7], after['asset'][:7])
            finally:
                self.conn.execute('RESET ROLE')


if __name__ == '__main__':
    unittest.main(verbosity=2)
