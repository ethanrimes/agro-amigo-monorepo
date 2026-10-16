"""Owned-PostgreSQL integration coverage for late-day OCR budget borrowing.

This test starts a disposable local PG16 cluster on an exact private Unix socket,
uses mocked OCR providers, and stops only the process whose PID/data path it owns.
"""
import getpass
import hashlib
import io
import os
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import psycopg
from PIL import Image
if __package__:
    from . import ocr as m
    from . import monthly_pdf_recovery
    from . import worker as w
else:  # unittest discovery with -s pipelines/ingestion imports by filename
    from pipelines.ingestion import ocr as m
    from pipelines.ingestion import monthly_pdf_recovery
    from pipelines.ingestion import worker as w

PG16_BIN = Path("/opt/homebrew/opt/postgresql@16/bin")
MIN_FREE_BYTES = 7 * 1024**3
SENSITIVE_DB_ENV = ("DATABASE_URL", "AGRO_DATABASE_URL", "AGRO_REFERENCE_TEST_DSN",
    "PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD", "PGSERVICE",
    "PGSERVICEFILE", "AGRO_DB_HOST", "AGRO_DB_PASSWORD", "AGRO_POSTGRES_DSN")

def _pg_binary(name):
    pinned = PG16_BIN / name
    return str(pinned) if pinned.is_file() else None

def _process(pid):
    result = subprocess.run(["ps", "-p", str(pid), "-o", "pid=,command="],
        capture_output=True, text=True, check=False)
    return result.stdout.strip() or None

class OCRIdleBorrowDrainPG(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  for key in SENSITIVE_DB_ENV:
   if os.environ.get(key):
    raise RuntimeError(f"Refusing OCR integration test with ambient database setting {key}")
  cls.initdb, cls.pg_ctl = _pg_binary("initdb"), _pg_binary("pg_ctl")
  cls.postgres = _pg_binary("postgres")
  if not cls.initdb or not cls.pg_ctl or not cls.postgres:
   raise RuntimeError("Disposable PostgreSQL 16 binaries are required; refusing to skip")
  if shutil.disk_usage(Path.cwd()).free < MIN_FREE_BYTES:
   raise RuntimeError("Less than 7 GiB free; refusing to start owned PostgreSQL")
  cls.directory = Path(tempfile.mkdtemp(prefix="agro-ocr-borrow-owned-", dir="/tmp")).resolve()
  if cls.directory.parent != Path("/tmp").resolve() or not cls.directory.name.startswith("agro-ocr-borrow-owned-"):
   raise RuntimeError("Owned temporary root failed its exact path guard")
  cls.cluster = cls.directory / "data"
  cls.socket_dir = cls.directory / "sock"
  cls.socket_dir.mkdir(mode=0o700)
  cls.owner_token = cls.directory / "owner.token"
  cls.owner_token.write_text(os.urandom(32).hex() + "\n")
  cls.owner_token.chmod(0o600)
  cls.owner_token_sha256 = hashlib.sha256(cls.owner_token.read_bytes()).hexdigest()
  with socket.socket() as listener:
   listener.bind(("127.0.0.1", 0))
   cls.port = listener.getsockname()[1]
  cls.start_attempted = False
  try:
   subprocess.run([cls.initdb, "-D", str(cls.cluster), "--auth=trust", "--no-locale",
       "--encoding=UTF8"], check=True, capture_output=True, text=True, timeout=90)
   cls.start_attempted = True
   start = subprocess.run([cls.pg_ctl, "-D", str(cls.cluster), "-l", str(cls.directory / "postgres.log"),
       "-o", f"-h '' -k {cls.socket_dir} -p {cls.port} -c max_connections=16 -c timezone=UTC",
       "-w", "-t", "45", "start"], check=False, capture_output=True, text=True, timeout=60)
   pid_lines = (cls.cluster / "postmaster.pid").read_text().splitlines()
   if len(pid_lines) < 2 or Path(pid_lines[1]).resolve() != cls.cluster.resolve():
    raise RuntimeError("PostgreSQL PID file does not identify the exact owned data directory")
   cls.postmaster_pid = int(pid_lines[0])
   identity = _process(cls.postmaster_pid)
   if not identity or str(cls.cluster) not in identity or "postgres" not in identity:
    raise RuntimeError("PostgreSQL process identity did not match the owned data directory")
   if start.returncode:
    raise RuntimeError(f"Pinned PostgreSQL 16 startup failed: {start.stderr[-1200:]}")
   cls.dsn = f"host={cls.socket_dir} port={cls.port} dbname=postgres user={getpass.getuser()} connect_timeout=3"
   cls.db = psycopg.connect(cls.dsn, connect_timeout=3, autocommit=True,
       options="-c statement_timeout=4000 -c timezone=UTC")
   if Path(cls.db.info.host).resolve() != cls.socket_dir.resolve():
    raise RuntimeError("Database connection escaped exact owned Unix socket")
   ident = cls.db.execute("SELECT current_database(),current_user,current_setting('TimeZone'),current_setting('data_directory'),inet_server_addr(),current_setting('server_version')").fetchone()
   if (ident[:5] != ("postgres", getpass.getuser(), "UTC", str(cls.cluster), None)
       or ident[5].split(".", 1)[0] != "16"):
    raise RuntimeError(f"Owned PostgreSQL identity mismatch: {ident!r}")
   cls.db.execute("""CREATE TABLE source_ocr_task (
    document_id text,source_locator text,image_id text,source_kind text,source_page int,
    status text default 'pending',created_at timestamptz default now(),checked_at timestamptz,error text,
    PRIMARY KEY(document_id,source_locator))""")
   cls.db.execute("""CREATE TABLE source_ocr_attempt
    (id bigint generated always as identity,image_id text,started_at timestamptz default now())""")
   cls.db.execute("""CREATE TABLE source_ocr_result
    (image_id text,version text,reading int,result jsonb,
     PRIMARY KEY(image_id,version,reading))""")
   cls.db.execute("""CREATE TABLE source_document
    (id text primary key,content bytea,media_type text,metadata jsonb,retrieved_at timestamptz default now())""")
   cls.db.execute("CREATE TABLE source_ocr_scan (document_id text,version text)")
   cls.db.execute("CREATE TABLE source_host_cooldown(host text,retry_at timestamptz)")
   cls.db.execute("CREATE TABLE ingestion_checkpoint(document_id text,processor_version text,step text,completed_at timestamptz default now())")
   cls.db.execute("CREATE TABLE ingestion_run(id uuid,mode text,status text,finished_at timestamptz,summary jsonb,started_at timestamptz default now())")
  except BaseException as startup_error:
   try:
    cls._recover_failed_startup()
   except BaseException as cleanup_error:
    raise RuntimeError(
     f"Owned PostgreSQL startup failed; preserving ambiguous directory {cls.directory}: {cleanup_error}"
    ) from startup_error
   shutil.rmtree(cls.directory)
   raise

 @classmethod
 def _recover_failed_startup(cls):
  """Stop only an exact owned server; preserve the directory on ambiguity."""
  if not cls.start_attempted:
   return
  if (not cls.owner_token.is_file()
      or hashlib.sha256(cls.owner_token.read_bytes()).hexdigest() != cls.owner_token_sha256):
   raise RuntimeError("owner token mismatch after startup attempt")
  pidfile = cls.cluster / "postmaster.pid"
  if pidfile.exists():
   lines = pidfile.read_text().splitlines()
   if len(lines) < 2 or not lines[0].isdigit() or Path(lines[1]).resolve() != cls.cluster.resolve():
    raise RuntimeError("PID file is ambiguous after startup attempt")
   pid = int(lines[0])
   identity = _process(pid)
   if not identity or str(cls.cluster) not in identity or "postgres" not in identity:
    raise RuntimeError("PID/data/process identity is ambiguous after startup attempt")
   cls.postmaster_pid = pid
   cls._stop_owned()
   return
  processes = subprocess.run(["ps", "-Ao", "pid=,command="], capture_output=True,
      text=True, check=True).stdout.splitlines()
  if any(str(cls.cluster) in line and ("postgres" in line or "postmaster" in line)
      for line in processes):
   raise RuntimeError("server process references owned data directory but PID file is absent")

 @classmethod
 def _stop_owned(cls):
  if (not cls.owner_token.is_file()
      or hashlib.sha256(cls.owner_token.read_bytes()).hexdigest() != cls.owner_token_sha256):
   raise RuntimeError("Refusing cleanup after owned PostgreSQL token mismatch")
  pidfile = cls.cluster / "postmaster.pid"
  if not pidfile.exists():
   if _process(cls.postmaster_pid):
    raise RuntimeError("Owned PID remains after PostgreSQL PID file disappeared")
   return
  lines = pidfile.read_text().splitlines()
  if len(lines) < 2 or int(lines[0]) != cls.postmaster_pid or Path(lines[1]).resolve() != cls.cluster.resolve():
   raise RuntimeError("Refusing to stop PostgreSQL with changed PID/data identity")
  ident = _process(cls.postmaster_pid)
  if not ident or str(cls.cluster) not in ident or "postgres" not in ident:
   raise RuntimeError("Refusing to stop process without exact owned PostgreSQL identity")
  subprocess.run([cls.pg_ctl, "-D", str(cls.cluster), "-m", "fast", "-w", "-t", "45", "stop"],
      check=True, capture_output=True, text=True, timeout=55)
  if pidfile.exists() or _process(cls.postmaster_pid):
   raise RuntimeError("Owned PostgreSQL did not stop cleanly")

 @classmethod
 def tearDownClass(cls):
  db = getattr(cls, "db", None)
  if db is not None:
   db.close()
  directory = getattr(cls, "directory", None)
  if directory is None:
   return
  try:
   if hasattr(cls, "postmaster_pid"):
    cls._stop_owned()
   shutil.rmtree(directory)
  except Exception:
   # Preserve an ambiguous owned cluster for diagnosis; never kill by name/PID alone.
   raise

 def setUp(self):
  self.db.execute('TRUNCATE source_ocr_task,source_ocr_attempt,source_ocr_result,source_document,source_ocr_scan,source_host_cooldown,ingestion_run')
 def task(self,did,kind='city-pdf',image=None,checked_hours_ago=None,status='pending',minutes_ago=20):
  image=image or did+'-image'
  self.db.execute('''INSERT INTO source_ocr_task(document_id,source_locator,image_id,source_kind,source_page,status,created_at,checked_at)
   VALUES(%s,'page-1',%s,%s,1,%s,now()-(%s*interval '1 minute'),CASE WHEN %s::numeric IS NULL THEN NULL ELSE now()-(%s*interval '1 hour') END)''',
   (did,image,kind,status,minutes_ago,checked_hours_ago,checked_hours_ago))
  out=io.BytesIO(); Image.new('RGB',(3,3),'white').save(out,format='PNG')
  self.db.execute("INSERT INTO source_document(id,content,media_type,metadata) VALUES(%s,%s,'image/png','{}'::jsonb) ON CONFLICT(id) DO NOTHING",(image,out.getvalue()))
  return image
 def attempts(self,image,n):
  for _ in range(n): self.db.execute('INSERT INTO source_ocr_attempt(image_id,started_at) VALUES(%s,now())',(image,))
 def cache(self,image,n=2):
  for idx in range(n): self.db.execute('INSERT INTO source_ocr_result(image_id,version,reading,result) VALUES(%s,%s,%s,%s::jsonb)',(image,m.VERSION,idx,'{"text":"cached"}'))
 def counters(self):
  r=self.db.execute("SELECT count(*),count(*) FILTER(WHERE EXISTS(SELECT 1 FROM source_ocr_task t WHERE t.image_id=a.image_id AND t.source_kind='city-pdf' AND t.created_at<=a.started_at)) FROM source_ocr_attempt a WHERE started_at >= (date_trunc('day',now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC')").fetchone()
  return r[0],r[1],r[0]-r[1]
 def drain(self,limit=5,allow=False,provider=None,utc_times=None,deadline=None,document_id=None):
  calls=[]
  def fake(content,**opts):
   calls.append(opts)
   return provider(content,**opts) if provider else {'text':'mock transcription','tables':[]}
  nowpatch=patch.object(m,'_utc_now',side_effect=utc_times) if utc_times is not None else patch.object(m,'_utc_now',return_value=datetime(2026,10,15,23,20))
  with nowpatch, patch.object(m,'retire_audited_decorative_pdf_pages',return_value=0), \
       patch.object(m,'requeue_cached_typed_reviews',return_value={'checked':0}), \
       patch.object(m,'compare_typed_task_readings',return_value=False), \
       patch.object(m,'compare_readings',return_value=False), \
       patch.object(m,'_finalize_milk_task',return_value=None), \
       patch.object(m,'retire_native_daily_tasks',return_value={'checked':0}), \
       patch.object(monthly_pdf_recovery,'retire_tasks',return_value={'checked':0}), \
       patch.object(m,'transcribe',side_effect=fake), \
       patch.dict(os.environ,{'GEMINI_API_KEY':'mock-only-no-network','GEMINI_OCR_DAILY_REQUESTS':'40'}):
   result=m.drain(self.db,limit=limit,scan_limit=0,deadline=deadline,document_id=document_id,allow_idle_city_borrow=allow)
  return result,calls

 def _scheduled_ocr_run(self, now):
  calls=[]
  def fake(content,**opts):
   calls.append(opts)
   return {'text':'mock transcription','tables':[]}
  def owned_connect():
   return psycopg.connect(self.dsn,connect_timeout=3,autocommit=True,
       options='-c statement_timeout=4000 -c timezone=UTC')
  with patch.object(m,'_utc_now',return_value=now), \
       patch.object(m,'retire_audited_decorative_pdf_pages',return_value=0), \
       patch.object(m,'requeue_cached_typed_reviews',return_value={'checked':0}), \
       patch.object(m,'compare_typed_task_readings',return_value=False), \
       patch.object(m,'compare_readings',return_value=False), \
       patch.object(m,'_finalize_milk_task',return_value=None), \
       patch.object(m,'retire_native_daily_tasks',return_value={'checked':0}), \
       patch.object(monthly_pdf_recovery,'retire_tasks',return_value={'checked':0}), \
       patch.object(m,'transcribe',side_effect=fake), \
       patch.object(w,'connect',side_effect=owned_connect), \
       patch.object(w,'refresh_catalog',return_value={'available':True}), \
       patch.dict(os.environ,{'GEMINI_API_KEY':'mock-only-no-network','GEMINI_OCR_DAILY_REQUESTS':'40'}):
   result=w.run('ocr',limit=0,time_budget=600,ocr_limit=8,ocr_scan_limit=0)
  return result,calls

 def test_cooling_noncity_task_does_not_block_idle_borrow(self):
  spent=self.task('spent'); self.attempts(spent,24); self.db.execute("UPDATE source_ocr_task SET status='review' WHERE document_id='spent'")
  self.task('weekly-cooling','dane-weekly-pdf',checked_hours_ago=1,status='deferred',minutes_ago=2)
  city=self.task('city-eligible',minutes_ago=1)
  result,calls=self.drain(limit=1,allow=True)
  self.assertEqual(len(calls),2)
  self.assertEqual(self.db.execute("SELECT status FROM source_ocr_task WHERE document_id='city-eligible'").fetchone()[0],'review')
  self.assertEqual(self.db.execute("SELECT status FROM source_ocr_task WHERE document_id='weekly-cooling'").fetchone()[0],'deferred')
  self.assertEqual(self.counters(),(26,26,0))
  self.assertEqual(result['provider_quota']['city_borrowed_allowance'],16)

 def test_document_scoped_drain_does_not_borrow_against_unknown_global_backlog(self):
  spent=self.task('spent'); self.attempts(spent,24); self.db.execute("UPDATE source_ocr_task SET status='review' WHERE document_id='spent'")
  self.task('unrelated-weekly','dane-weekly-pdf',minutes_ago=2)
  self.task('scoped-city',minutes_ago=1)
  result,calls=self.drain(limit=1,allow=True,document_id='scoped-city')
  self.assertEqual(calls,[])
  self.assertEqual(self.db.execute("SELECT status FROM source_ocr_task WHERE document_id='scoped-city'").fetchone()[0],'pending')
  self.assertEqual(result['provider_quota']['city_borrowed_allowance'],0)

 def test_normal_24_city_reserve_never_borrows(self):
  spent=self.task('spent'); self.attempts(spent,24); self.db.execute("UPDATE source_ocr_task SET status='review' WHERE document_id='spent'")
  candidate=self.task('candidate',minutes_ago=1)
  result,calls=self.drain(limit=1,allow=False,utc_times=[datetime(2026,10,15,23,20)]*8)
  self.assertEqual(calls,[])
  self.assertEqual(result['provider_quota']['selected_city'],0)
  self.assertEqual(self.counters(),(24,24,0))
  self.assertEqual(self.db.execute("SELECT status FROM source_ocr_task WHERE document_id='candidate'").fetchone()[0],'pending')

 def test_final_post_2315_idle_lane_selects_and_spends_only_to_40(self):
  spent=self.task('spent'); self.attempts(spent,24); self.db.execute("UPDATE source_ocr_task SET status='review' WHERE document_id='spent'")
  for i in range(8): self.task(f'city-{i:02d}',minutes_ago=10-i)
  result,calls=self.drain(limit=8,allow=True)
  self.assertEqual(len(calls),16)
  self.assertEqual(result['processed'],8)
  self.assertEqual(self.counters(),(40,40,0))
  self.assertEqual(result['provider_quota']['global_used'],40)
  self.assertEqual(result['provider_quota']['city_borrowed_allowance'],16)
  self.assertEqual(self.db.execute("SELECT count(*) FROM source_ocr_attempt WHERE started_at >= (date_trunc('day',now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC')").fetchone()[0],40)

 def test_pending_noncity_with_two_missing_reads_blocks_city_borrow(self):
  spent=self.task('spent'); self.attempts(spent,24); self.db.execute("UPDATE source_ocr_task SET status='review' WHERE document_id='spent'")
  self.task('weekly-pending','dane-weekly-pdf',minutes_ago=2)
  city=self.task('city-pending',minutes_ago=1)
  result,calls=self.drain(limit=1,allow=True)
  self.assertEqual(len(calls),2) # protected non-city page receives its normal lane
  self.assertEqual(self.db.execute("SELECT status FROM source_ocr_task WHERE document_id='weekly-pending'").fetchone()[0],'review')
  self.assertEqual(self.db.execute("SELECT status FROM source_ocr_task WHERE document_id='city-pending'").fetchone()[0],'pending')
  self.assertEqual(self.counters(),(26,24,2))
  self.assertEqual(result['provider_quota']['city_borrowed_allowance'],0)

 def test_pending_noncity_one_cached_read_still_blocks_borrow(self):
  spent=self.task('spent'); self.attempts(spent,24); self.db.execute("UPDATE source_ocr_task SET status='review' WHERE document_id='spent'")
  other=self.task('weekly-partial','dane-weekly-pdf',minutes_ago=2); self.cache(other,1)
  city=self.task('city-pending',minutes_ago=1)
  result,calls=self.drain(limit=1,allow=True)
  self.assertEqual(len(calls),1)
  self.assertEqual(self.db.execute("SELECT status FROM source_ocr_task WHERE document_id='weekly-partial'").fetchone()[0],'review')
  self.assertEqual(self.db.execute("SELECT status FROM source_ocr_task WHERE document_id='city-pending'").fetchone()[0],'pending')
  self.assertEqual(self.counters(),(25,24,1))

 def test_one_cached_city_read_uses_one_last_global_slot(self):
  spent=self.task('spent'); self.attempts(spent,39); self.db.execute("UPDATE source_ocr_task SET status='review' WHERE document_id='spent'")
  partial=self.task('city-partial',minutes_ago=1); self.cache(partial,1)
  result,calls=self.drain(limit=1,allow=True)
  self.assertEqual(len(calls),1)
  self.assertEqual(self.counters(),(40,40,0))
  self.assertEqual(self.db.execute("SELECT count(*) FROM source_ocr_result WHERE image_id=%s AND version=%s",(partial,m.VERSION)).fetchone()[0],2)
  self.assertEqual(result['provider_quota']['global_used'],40)

 def test_clock_rollover_between_selection_and_provider_read_fails_closed(self):
  spent=self.task('spent'); self.attempts(spent,24); self.db.execute("UPDATE source_ocr_task SET status='review' WHERE document_id='spent'")
  self.task('city-pending',minutes_ago=1)
  times=[datetime(2026,10,16,23,50,0)]*3+[datetime(2026,10,17,0,0,1)]
  result,calls=self.drain(limit=1,allow=True,utc_times=times)
  self.assertEqual(calls,[])
  self.assertEqual(self.counters(),(24,24,0))
  self.assertEqual(m._current_attempt_counts(self.db,now=datetime(2026,10,17,0,0,1)),(0,0,0))
  self.assertEqual(result['processed'],0)

 def test_midnight_between_reads_keeps_first_cache_and_uses_fresh_day_quota(self):
  spent=self.task('spent'); self.attempts(spent,24); self.db.execute("UPDATE source_ocr_task SET status='review' WHERE document_id='spent'")
  image=self.task('city-midnight',minutes_ago=1)
  times=[datetime(2026,10,16,23,50,0)]*4+[datetime(2026,10,17,0,0,1)]
  result,calls=self.drain(limit=1,allow=True,utc_times=times)
  self.assertEqual(len(calls),1)
  self.assertEqual(self.db.execute("SELECT count(*) FROM source_ocr_result WHERE image_id=%s AND version=%s AND reading=0",(image,m.VERSION)).fetchone()[0],1)
  self.assertEqual(self.db.execute("SELECT count(*) FROM source_ocr_result WHERE image_id=%s AND version=%s AND reading=1",(image,m.VERSION)).fetchone()[0],0)
  self.assertEqual(self.db.execute("SELECT status FROM source_ocr_task WHERE document_id='city-midnight'").fetchone()[0],'deferred')
  self.assertEqual(m._current_attempt_counts(self.db,now=datetime(2026,10,16,23,59,0)),(25,25,0))
  self.assertEqual(m._current_attempt_counts(self.db,now=datetime(2026,10,17,0,0,1)),(0,0,0))
  self.assertEqual(result['processed'],0)

 def test_cached_publication_can_finish_after_midnight_without_provider(self):
  spent=self.task('spent'); self.attempts(spent,24); self.db.execute("UPDATE source_ocr_task SET status='review' WHERE document_id='spent'")
  image=self.task('city-already-cached',minutes_ago=1); self.cache(image)
  times=[datetime(2026,10,16,23,59,0)]*2+[datetime(2026,10,17,0,0,1)]*8
  result,calls=self.drain(limit=1,allow=True,utc_times=times)
  self.assertEqual(calls,[])
  self.assertEqual(result['processed'],1)
  self.assertEqual(self.db.execute("SELECT status FROM source_ocr_task WHERE document_id='city-already-cached'").fetchone()[0],'review')
  self.assertEqual(m._current_attempt_counts(self.db,now=datetime(2026,10,17,0,0,1)),(0,0,0))

 def test_complete_cached_tasks_at_full_quota_make_zero_provider_calls(self):
  city=self.task('city-cached'); other=self.task('weekly-cached','dane-weekly-pdf')
  self.cache(city); self.cache(other)
  self.attempts(city,24); self.attempts(other,16)
  result,calls=self.drain(limit=2,allow=True,utc_times=[datetime(2026,10,15,23,30)]*10)
  self.assertEqual(calls,[])
  self.assertEqual(result['processed'],2)
  self.assertEqual(self.counters(),(40,24,16))

 def test_late_arrival_after_first_read_stops_second_read(self):
  self.task('spent'); self.attempts('spent-image',24); self.db.execute("UPDATE source_ocr_task SET status='review' WHERE document_id='spent'")
  city=self.task('city-arrival-probe',minutes_ago=1)
  calls=[]
  def provider(content,**opts):
   calls.append(opts)
   if len(calls)==1:
    self.task('new-weekly-arrival','dane-weekly-pdf',minutes_ago=0)
   return {'text':'mock transcription','tables':[]}
  result,_=self.drain(limit=1,allow=True,provider=provider)
  self.assertEqual(len(calls),1)
  self.assertEqual(self.counters(),(25,25,0))
  self.assertEqual(self.db.execute("SELECT status FROM source_ocr_task WHERE document_id='city-arrival-probe'").fetchone()[0],'deferred')
  self.assertEqual(self.db.execute("SELECT status FROM source_ocr_task WHERE document_id='new-weekly-arrival'").fetchone()[0],'pending')
  self.assertEqual(result['processed'],0)

 def test_short_deadline_fails_before_any_provider(self):
  self.task('city-deadline',minutes_ago=1)
  result,calls=self.drain(limit=1,allow=True,deadline=time.monotonic()+1)
  self.assertEqual(calls,[])
  self.assertEqual(self.counters(),(0,0,0))

 def test_worker_shared_advisory_lock_overlap_skips_without_provider(self):
  self.db.execute('SELECT pg_advisory_lock(%s)',(w.LOCK,))
  try:
   def owned_connect(): return psycopg.connect(self.dsn,connect_timeout=3,autocommit=True,options='-c statement_timeout=4000 -c timezone=UTC')
   with patch.object(w,'connect',side_effect=owned_connect):
    res=w.run('daily',limit=0,time_budget=30)
   self.assertEqual(res['status'],'skipped_overlap')
   self.assertEqual(self.counters(),(0,0,0))
  finally:
   self.db.execute('SELECT pg_advisory_unlock(%s)',(w.LOCK,))

 def test_ocr_recovery_2305_is_before_borrow_window(self):
  spent=self.task('spent'); self.attempts(spent,24)
  self.db.execute("UPDATE source_ocr_task SET status='review' WHERE document_id='spent'")
  self.task('city-2305',minutes_ago=1)
  result,calls=self._scheduled_ocr_run(datetime(2026,10,16,23,5,0))
  self.assertEqual(calls,[])
  self.assertEqual(self.counters(),(24,24,0))
  self.assertEqual(self.db.execute("SELECT status FROM source_ocr_task WHERE document_id='city-2305'").fetchone()[0],'pending')
  self.assertEqual(result['ocr']['provider_quota']['city_borrowed_allowance'],0)

 def test_ocr_recovery_2335_borrows_only_within_existing_global_cap(self):
  spent=self.task('spent'); self.attempts(spent,24)
  self.db.execute("UPDATE source_ocr_task SET status='review' WHERE document_id='spent'")
  for i in range(2): self.task(f'city-2335-{i}',minutes_ago=2-i)
  result,calls=self._scheduled_ocr_run(datetime(2026,10,16,23,35,0))
  self.assertEqual(len(calls),4)
  self.assertEqual(result['ocr']['processed'],2)
  self.assertEqual(self.counters(),(28,28,0))
  self.assertEqual(result['ocr']['provider_quota']['global_limit'],40)
  self.assertEqual(result['ocr']['provider_quota']['city_borrowed_allowance'],16)
  self.assertEqual(result['errors'],[])

 def test_ocr_borrow_mode_gate_and_schedule_default_are_narrow(self):
  self.assertTrue(w._ocr_idle_city_borrow_enabled('ocr',None))
  self.assertTrue(w._ocr_idle_city_borrow_enabled('backfill',None))
  self.assertTrue(w._ocr_idle_city_borrow_enabled('daily',None))
  self.assertFalse(w._ocr_idle_city_borrow_enabled('ocr','https://example.invalid/target'))
  self.assertFalse(w._ocr_idle_city_borrow_enabled('discover',None))
  from infra import deploy_ingestion
  self.assertIn('"OCR_SCHEDULE": "0 35 * * * *"',Path(deploy_ingestion.__file__).read_text())


if __name__ == '__main__':
 unittest.main(verbosity=2)
