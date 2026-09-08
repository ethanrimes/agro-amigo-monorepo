"""Verify real DB coverage, boundaries, idempotency, and least-privilege access."""
import json
from pathlib import Path
from datetime import timedelta
import certifi,psycopg
from import_data import TODAY,START
ROOT=Path(__file__).resolve().parents[2]
c=json.loads((ROOT/'.azure-local/database.json').read_text())
options=dict(host=c['host'],dbname=c['database'],sslmode='verify-full',sslrootcert=certifi.where(),connect_timeout=15)
with psycopg.connect(**options,user=c['user'],password=c['password']) as db:
 for table in ['price_observation','coffee_reference','coffee_factor','exchange_rate','buyer_offer']:
  count,earliest,latest,outside=db.execute(f'SELECT count(*),min(observed_on),max(observed_on),count(*) FILTER(WHERE observed_on>%s) FROM {table}',(TODAY,)).fetchone()
  assert outside==0,(table,outside)
  print(table,{'rows':count,'first':str(earliest),'last':str(latest),'outside_window':outside})
 for day in [TODAY+timedelta(days=1)]:
  try:
   with db.transaction(): db.execute('INSERT INTO coffee_reference(observed_on,price,source_url) VALUES (%s,1,%s)',(day,'https://example.test/boundary-validation'))
  except psycopg.errors.RaiseException: pass
  else: raise AssertionError(f'Date guard did not reject {day}')
 assert db.execute('SELECT count(*) FROM buyer_offer').fetchone()[0]==0
 print('Future-date rejection: passed; history retained')
with psycopg.connect(**options,user='agro_reader',password=c['appPassword']) as db:
 assert db.execute('SELECT count(*) FROM product').fetchone()[0]>100
 try:
  with db.transaction(): db.execute("INSERT INTO product(id,name,category) VALUES ('permission-test','test','test')")
 except psycopg.errors.InsufficientPrivilege: print('Application read-only role: passed')
 else: raise AssertionError('Application role could write')
