"""Disposable Unix-socket full-schema worker proof. Never opens a network DB."""

import hashlib
import io
import json
import os
import re
import shlex
import shutil
from pathlib import Path
import subprocess
import tempfile
import unittest
from datetime import date
from unittest.mock import patch

import pdfplumber
import psycopg
from psycopg.types.json import Jsonb

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PG = Path('/opt/homebrew/opt/postgresql@16/bin')
CASES = (
    ('feb', date(2014, 2, 28), '3e1265bdbff25420d9be9b44c4db0aa7564585270cdc93878810c68ebae46dc3',
     'pipelines/ingestion/testdata/input_pdf_v17_originals/feb2014.pdf', 4794, 4799,
     'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_feb_2014.pdf'),
    ('mar', date(2014, 3, 31), '2befda0f1d3d4740b7a82e3a9d5ca3e6c9d2e213193ccf011ddadf9d8d729403',
     'pipelines/ingestion/testdata/input_pdf_v17_originals/mar2014.pdf', 5706, 5709,
     'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_mar_2014.pdf'),
    ('may', date(2014, 5, 31), 'db08213afe320e1a1101d2c8311565c924f4a2c82aef56d98a3971e26a1c9d62',
     'pipelines/ingestion/testdata/input_pdf_v17_originals/may2014.pdf', 5977, 5983,
     'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_may_2014.pdf'),
)

# Exact source-document bindings from the independent read-only retained-source inventory.
RETAINED_SOURCE_BINDINGS = {
    '2befda0f1d3d4740b7a82e3a9d5ca3e6c9d2e213193ccf011ddadf9d8d729403': {'id': '2befda0f1d3d4740b7a82e3a9d5ca3e6c9d2e213193ccf011ddadf9d8d729403', 'title': 'DANE - insumos_factores_de_produccion_mar_2014.pdf', 'publisher': 'DANE', 'source_url': 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_mar_2014.pdf', 'media_type': 'application/pdf', 'kind': 'original', 'reference_period': '2014-03-31', 'page_count': 64, 'metadata': {'retention': 'permanent', 'ingestion_kind': 'context-pdf', 'original_filename': 'insumos_factores_de_produccion_mar_2014.pdf'}},
    '3e1265bdbff25420d9be9b44c4db0aa7564585270cdc93878810c68ebae46dc3': {'id': '3e1265bdbff25420d9be9b44c4db0aa7564585270cdc93878810c68ebae46dc3', 'title': 'DANE - insumos_factores_de_produccion_feb_2014.pdf', 'publisher': 'DANE', 'source_url': 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_feb_2014.pdf', 'media_type': 'application/pdf', 'kind': 'original', 'reference_period': '2014-02-28', 'page_count': 56, 'metadata': {'retention': 'permanent', 'ingestion_kind': 'context-pdf', 'original_filename': 'insumos_factores_de_produccion_feb_2014.pdf'}},
    'db08213afe320e1a1101d2c8311565c924f4a2c82aef56d98a3971e26a1c9d62': {'id': 'db08213afe320e1a1101d2c8311565c924f4a2c82aef56d98a3971e26a1c9d62', 'title': 'DANE - insumos_factores_de_produccion_may_2014.pdf', 'publisher': 'DANE', 'source_url': 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_may_2014.pdf', 'media_type': 'application/pdf', 'kind': 'original', 'reference_period': '2014-05-31', 'page_count': 64, 'metadata': {'retention': 'permanent', 'ingestion_kind': 'context-pdf', 'original_filename': 'insumos_factores_de_produccion_may_2014.pdf'}},
}



def setup_cluster(root):
    data = root / 'data'
    socket = root / 'socket'
    socket.mkdir()
    subprocess.run([str(PG/'initdb'), '-D', str(data), '-A', 'trust', '-U', 'postgres', '--encoding=UTF8', '--no-instructions'],
                   check=True, stdout=subprocess.DEVNULL)
    subprocess.run([str(PG/'pg_ctl'), '-D', str(data), '-l', str(root/'postgres.log'),
                    '-o', f'-k {socket} -p 65494 -c listen_addresses= -c timezone=UTC', 'start'],
                   check=True, stdout=subprocess.DEVNULL)
    return data, socket



def _has_exact_postgres_image(lsof_output, expected_executable):
    resolved = []
    for line in lsof_output.splitlines():
        if not line.startswith('n/'):
            continue
        try:
            resolved.append(Path(line[1:]).resolve(strict=True))
        except OSError:
            # lsof may report transient unrelated files that vanish during
            # inspection; the exact expected binary must still resolve below.
            continue
    return expected_executable in resolved

def cleanup_owned_role_cluster(root, data, socket, evidence_dir):
    """Best-effort test-owned cleanup; fail closed and preserve the test error."""
    result = {'owned_root': str(root), 'owned_data': str(data), 'owned_socket': str(socket),
              'cleanup_performed': False, 'ownership_verified': False,
              'pre_stop_process_verified': False, 'stop_verified': False}
    try:
        # Resolve and validate every directory before considering a stop/removal.
        if root.is_symlink() or data.is_symlink() or socket.is_symlink():
            raise RuntimeError('symlink in test-owned cleanup path')
        root_abs = root.resolve(strict=True)
        data_abs = data.resolve(strict=True)
        socket_abs = socket.resolve(strict=True)
        if (root_abs.parent != Path('/tmp').resolve() or not root_abs.name.startswith('agro-input-v17-owned-')
                or data_abs != root_abs/'data' or socket_abs != root_abs/'socket'):
            raise RuntimeError('test-owned path did not match exact expected /tmp layout')
        if (data_abs/'PG_VERSION').read_text().strip() != '16':
            raise RuntimeError('data directory is not the expected PostgreSQL 16 cluster')
        pid_path = data_abs/'postmaster.pid'
        if not pid_path.is_file():
            raise RuntimeError('postmaster.pid absent before stop; preserve cluster')
        pid_lines = pid_path.read_text(errors='replace').splitlines()
        if len(pid_lines) < 2:
            raise RuntimeError('postmaster.pid did not contain PID and data path')
        pid = int(pid_lines[0])
        pid_data = Path(pid_lines[1]).resolve(strict=True)
        if pid_data != data_abs:
            raise RuntimeError('postmaster PID data path mismatch')
        result.update({'pg_pid': pid, 'pid_data_path': str(pid_data), 'ownership_verified': True})

        before = subprocess.run(['ps','-p',str(pid),'-o','pid=,command='],
                                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=10)
        raw = before.stdout.strip()
        if before.returncode != 0 or not raw:
            raise RuntimeError('PID was not live before stop; preserve cluster')
        split = raw.split(None,1)
        if len(split) != 2 or int(split[0]) != pid:
            raise RuntimeError('ps PID did not match postmaster.pid')
        argv = shlex.split(split[1])
        exe = Path(argv[0]).name if argv else ''
        data_arg = None
        for i, token in enumerate(argv[:-1]):
            if token in ('-D','--pgdata','--data-directory'):
                data_arg = argv[i+1]
                break
            if token.startswith('--pgdata='):
                data_arg = token.split('=',1)[1]
                break
        if exe not in ('postgres','postmaster') or data_arg is None or Path(data_arg).resolve(strict=True) != data_abs:
            raise RuntimeError('live process command did not bind exact PostgreSQL executable/data path')
        # Verify the actual executable image too; `ps` argv alone is not enough.
        image = subprocess.run(['lsof','-p',str(pid),'-a','-d','txt','-Fn'],
                               stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=10)
        expected_executable = (PG/'postgres').resolve(strict=True)
        if image.returncode != 0 or not _has_exact_postgres_image(image.stdout, expected_executable):
            raise RuntimeError('live process executable was not the exact PostgreSQL 16 binary')
        result['process_command_sha256'] = hashlib.sha256(raw.encode()).hexdigest()
        result['process_executable'] = str(expected_executable)
        result['pre_stop_process_verified'] = True

        stop = subprocess.run([str(PG/'pg_ctl'),'-D',str(data_abs),'stop','-m','immediate'],
                              stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=60)
        result.update({'stop_returncode':stop.returncode,'stop_output':stop.stdout[-2000:]})
        after = subprocess.run(['ps','-p',str(pid),'-o','pid=,command='],
                               stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=10)
        result['postmaster_pid_absent'] = not pid_path.exists()
        result['pid_absent_from_ps'] = not after.stdout.strip()
        result['stop_verified'] = (stop.returncode == 0 and not pid_path.exists()
                                  and after.returncode in (0, 1) and not after.stdout.strip())
        log_path = root_abs/'postgres.log'
        if log_path.is_file():
            log_bytes = log_path.read_bytes()
            result['postgres_log_sha256_before_cleanup'] = hashlib.sha256(log_bytes).hexdigest()
            result['postgres_log_bytes_before_cleanup'] = len(log_bytes)
        if not result['stop_verified']:
            raise RuntimeError('stop was not verified; data/socket/log retained')
        if not evidence_dir:
            result['cleanup_error'] = 'no artifact directory supplied; stopped data/socket retained'
            return result
        if not log_path.is_file():
            raise RuntimeError('postgres.log missing; data/socket retained')
        evidence = Path(evidence_dir).resolve()
        evidence.mkdir(parents=True,exist_ok=True)
        log_copy = evidence/f'ROLE_TEST_POSTGRES_{pid}_FIRST.log'
        with log_copy.open('xb') as dst:
            dst.write(log_bytes)
        copied_sha = hashlib.sha256(log_copy.read_bytes()).hexdigest()
        result.update({'preserved_log':str(log_copy),'preserved_log_sha256':copied_sha})
        if copied_sha != result['postgres_log_sha256_before_cleanup']:
            raise RuntimeError('copied postgres.log hash mismatch; data/socket retained')
        # Recheck exact path identity and that no symlink appeared before deletion.
        if root.resolve(strict=True) != root_abs or data.is_symlink() or socket.is_symlink():
            raise RuntimeError('ownership path changed before deletion; preserve data/socket')
        shutil.rmtree(data_abs)
        shutil.rmtree(socket_abs)
        result['data_removed_after_verified_stop'] = not data_abs.exists()
        result['socket_removed_after_verified_stop'] = not socket_abs.exists()
        result['cleanup_performed'] = result['data_removed_after_verified_stop'] and result['socket_removed_after_verified_stop']
        record = evidence/f'ROLE_TEST_CLEANUP_{pid}_FIRST.json'
        with record.open('x') as f:
            f.write(json.dumps(result,indent=2,sort_keys=True)+'\n')
        result['cleanup_receipt'] = str(record)
    except Exception as exc:
        result['cleanup_error'] = f'{type(exc).__name__}: {exc}'[:1000]
    return result

def install(db):
    db.execute('CREATE ROLE agro_reader')
    db.execute('CREATE ROLE agro_ingestor')
    for schema in ('demo', 'planning', 'market', 'spatial', 'ingestion'):
        if schema == 'ingestion':
            db.execute('''CREATE TABLE IF NOT EXISTS daily_price(
              observed_on date,product_name text,market_name text,
              product_id text REFERENCES product(id),price numeric NOT NULL CHECK(price>0),
              change_percent numeric,document_id text REFERENCES source_document(id),
              source_page integer,source_locator text,
              PRIMARY KEY(observed_on,product_name,market_name));
              CREATE TRIGGER demo_window BEFORE INSERT OR UPDATE ON daily_price
              FOR EACH ROW EXECUTE FUNCTION enforce_demo_window();
              GRANT SELECT ON daily_price TO agro_reader;''')
        db.execute((REPO/'pipelines'/schema/'schema.sql').read_text())
    for migration in sorted((REPO/'pipelines/ingestion/migrations').glob('*.sql')):
        source = migration.read_text()
        if re.search(r'\b(?:CREATE|DROP)\s+INDEX\s+CONCURRENTLY\b', source, re.I):
            continue
        db.execute(source)
    db.execute('GRANT CONNECT,TEMP ON DATABASE postgres TO agro_ingestor')
    db.execute('GRANT USAGE ON SCHEMA public TO agro_ingestor')
    db.execute('GRANT SELECT ON ALL TABLES IN SCHEMA public TO agro_ingestor')
    db.execute('GRANT INSERT ON official_source_review,official_price_quote,historical_price,retained_record,source_document TO agro_ingestor')
    db.execute('GRANT INSERT,UPDATE ON ingestion_run,ingestion_asset,document_alias,product,market,price_observation,coffee_reference,coffee_factor,exchange_rate,daily_price,input_price,input_municipal_price,source_pdf_page,regional_price,source_archive_member,input_reference_row,seasonal_year,supply_observation TO agro_ingestor')
    db.execute('GRANT INSERT,UPDATE ON source_ocr_task TO agro_ingestor')
    db.execute('GRANT INSERT ON regional_classification,source_ocr_scan,source_ocr_result,source_ocr_attempt TO agro_ingestor')


def main():
    from pipelines.ingestion import inputs, pdf_sources
    from pipelines.ingestion import input_pdf_v17_replay as private
    from pipelines.ingestion import worker
    candidate_pdf = pdf_sources
    candidate_inputs = inputs
    assert worker.parser_version('inputs-pdf') == private.VERSION
    assert candidate_inputs.input_pdf_version_for_document('f'*64, 'fixture://generic') == private.VERSION
    root = Path(tempfile.mkdtemp(prefix='agro-input-v17-owned-', dir='/tmp'))
    data, socket = root/'data', root/'socket'
    receipt = {'socket': str(socket), 'pg_major': 16, 'cases': [], 'terminal': 'failed'}
    try:
        data, socket = setup_cluster(root)
        receipt['socket'] = str(socket)
        with psycopg.connect(host=str(socket), port=65494, user='postgres', dbname='postgres', autocommit=True) as db:
            assert db.execute('SELECT inet_server_addr()').fetchone()[0] is None
            install(db)
            for label, day, did, path, old_expected, new_expected, url in CASES:
                body = (REPO/path).read_bytes()
                assert hashlib.sha256(body).hexdigest() == did
                with pdfplumber.open(io.BytesIO(body)) as pdf:
                    pages = len(pdf.pages)
                old = list(pdf_sources.parse_input_pdf(body, day))
                new = list(candidate_pdf.parse_input_pdf(body, day, parser_version=private.VERSION))
                assert (len(old), len(new)) == (old_expected, new_expected)
                source_binding = RETAINED_SOURCE_BINDINGS[did]
                assert source_binding['source_url'] == url
                assert source_binding['reference_period'] == day.isoformat()
                assert source_binding['page_count'] == pages
                assert source_binding['metadata']['original_filename'] == url.rsplit('/', 1)[-1]
                db.execute('INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,page_count,content,metadata) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                           (did, source_binding['title'], source_binding['publisher'], url, source_binding['media_type'], source_binding['kind'], source_binding['reference_period'], pages, body, Jsonb(source_binding['metadata'])))
                db.execute('INSERT INTO ingestion_asset(url,kind,observed_on,document_id,status,processor_version,records) VALUES(%s,%s,%s,%s,%s,%s,%s)',
                           (url,'inputs-pdf',day,did,'complete',private.OLD_VERSION,len(old)))
                db.execute('SET ROLE agro_ingestor')
                try:
                    # Seed the exact former release's v14 checkpoint while
                    # testing the integrated v17 code. The override is local
                    # to fixture setup and cannot change the replay route.
                    with patch.object(inputs, 'input_pdf_version_for_document', return_value=private.OLD_VERSION):
                        with db.transaction():
                            worker.save_rows(db,did,old)
                            inputs.project_pdf_inputs(db,did,source_url=url)
                        # save_rows uses a transaction-scoped temp table;
                        # seed representative older cohorts separately.
                        with db.transaction():
                            witness = old[0]
                            legacy_rows = [
                                (
                                    witness[0].removesuffix('inputs-pdf-v14') + f'inputs-pdf-v{version}',
                                    *witness[1:-1],
                                    {**witness[-1], 'parser_version': f'inputs-pdf-v{version}'},
                                )
                                for version in (11, 12, 13)
                            ]
                            worker.save_rows(db,did,legacy_rows)
                    checkpoint = db.execute("SELECT records FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s AND step='inputs-pdf:published'",(did,private.OLD_VERSION)).fetchone()[0]
                    assert checkpoint == sum(row[1]=='dane-inputs-pdf' for row in old)
                    before = db.execute('SELECT count(*) FROM published_input_municipal_price WHERE document_id=%s',(did,)).fetchone()[0]
                    old_xmin = db.execute("SELECT md5(string_agg(source_locator||':'||xmin::text,'|' ORDER BY source_locator)) FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s",(did,private.OLD_VERSION)).fetchone()[0]
                    legacy_xmin = db.execute("SELECT md5(string_agg(source_locator||':'||xmin::text,'|' ORDER BY source_locator)) FROM historical_price WHERE document_id=%s AND details->>'parser_version' IN ('inputs-pdf-v11','inputs-pdf-v12','inputs-pdf-v13')",(did,)).fetchone()[0]
                    assert db.execute("SELECT count(DISTINCT details->>'parser_version') FROM historical_price WHERE document_id=%s AND details->>'parser_version' IN ('inputs-pdf-v11','inputs-pdf-v12','inputs-pdf-v13')",(did,)).fetchone()[0]==3
                    assert private.retained_v14_input_pdf(db,url,'inputs-pdf',day,private.VERSION)==body
                    assert private.assert_retained_v14_vectors(db,did,old,new)==len(new)
                    with patch.object(worker,'fetch_asset',side_effect=AssertionError('HTTP forbidden')) as fetch, \
                         patch.object(worker,'archive',return_value=did), \
                         patch.object(pdf_sources,'extract_pages',return_value=0):
                        count = worker.process_asset(db,url,'inputs-pdf',day)
                        fetch.assert_not_called()
                    assert count == len(new)
                    status = db.execute('SELECT status,processor_version,records FROM ingestion_asset WHERE url=%s',(url,)).fetchone()
                    assert status==('complete',private.VERSION,len(new)),status
                    after_cp=db.execute("SELECT records FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s AND step='inputs-pdf:published'",(did,private.VERSION)).fetchone()
                    assert after_cp and after_cp[0]==sum(row[1]=='dane-inputs-pdf' for row in new),(after_cp,len(new))
                    after_xmin=db.execute("SELECT md5(string_agg(source_locator||':'||xmin::text,'|' ORDER BY source_locator)) FROM historical_price WHERE document_id=%s AND details->>'parser_version'=%s",(did,private.OLD_VERSION)).fetchone()[0]
                    assert after_xmin==old_xmin
                    assert db.execute("SELECT md5(string_agg(source_locator||':'||xmin::text,'|' ORDER BY source_locator)) FROM historical_price WHERE document_id=%s AND details->>'parser_version' IN ('inputs-pdf-v11','inputs-pdf-v12','inputs-pdf-v13')",(did,)).fetchone()[0]==legacy_xmin
                    after=db.execute('SELECT count(*) FROM published_input_municipal_price WHERE document_id=%s',(did,)).fetchone()[0]
                    receipt['cases'].append({'label':label,'source_sha256':did,'pages':pages,'old_rows':len(old),'v17_rows':len(new),'old_checkpoint':checkpoint,'new_checkpoint':after_cp[0],'old_public':before,'new_public':after,'old_xmin_unchanged':True,'v11_v12_v13_witness_xmin_unchanged':True,'asset':status})
                finally:
                    db.execute('RESET ROLE')
        receipt['terminal']='completed'
    except Exception as exc:
        receipt['error_type']=type(exc).__name__
        receipt['error']=str(exc)[:1000]
        raise
    finally:
        receipt['cleanup'] = cleanup_owned_role_cluster(
            root, data, socket, os.environ.get('AGRO_V17_ROLE_TEST_ARTIFACT_DIR'))
        print(json.dumps(receipt, indent=2, default=str))


class RetainedInputPDFV17Role(unittest.TestCase):
    def test_three_real_context_originals_upgrade_under_ingestor_acl(self):
        main()


if __name__=='__main__':
    unittest.main()
