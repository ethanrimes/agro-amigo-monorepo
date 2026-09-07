"""Check persisted evidence, references, numerical extraction and data boundaries."""
from import_references import *
import hashlib
config=json.loads((ROOT/'.azure-local/database.json').read_text())
with psycopg.connect(host=config['host'],dbname=config['database'],user=config['user'],password=config['password'],sslmode='verify-full',sslrootcert=certifi.where(),connect_timeout=15) as db:
 for table in ['price_observation','coffee_reference','coffee_factor','exchange_rate','input_price','daily_price']:
  n,missing,outside=db.execute(f'SELECT count(*),count(*) FILTER(WHERE document_id IS NULL),count(*) FILTER(WHERE observed_on<=%s OR observed_on>%s) FROM {table}',(START,TODAY)).fetchone();assert missing==outside==0,(table,missing,outside);print(table,n,'dated and traceable')
 total=0;size=0
 with db.cursor(name='evidence_integrity') as cursor:
  cursor.execute('SELECT id,content FROM source_document')
  for did,content in cursor:assert hashlib.sha256(content).hexdigest()==did;total+=1;size+=len(content)
 print('Immutable documents verified',total,'bytes',size)
 for table in ['municipality','crop_reference','crop_calendar','crop_suitability','soil_reference','seasonal_year','cost_template','advisory']:print(table,db.execute(f'SELECT count(*) FROM {table}').fetchone()[0])
 assert db.execute('SELECT count(*) FROM seasonal_year WHERE reference_year<2021 OR reference_year>2025 OR jsonb_array_length(monthly_prices)<>12').fetchone()[0]==0
 for ident,total,yieldkg in [('papa-2023-2',27739208,34100),('frijol-2023-13',8231655,1500),('tomate-2023-10',54710884,139200)]:
  row=db.execute('SELECT costs,yield_kg_ha,source_page FROM cost_template WHERE id=%s',(ident,)).fetchone()
  assert row is not None,ident
  assert abs(sum(c['amount'] for c in row[0])-total)<1,(ident,row)
  assert abs(float(row[1])-yieldkg)<1,(ident,row)
 print('Three independent source-table totals and yields verified')
 assert db.execute('SELECT price FROM daily_price WHERE product_name=%s AND market_name=%s',('Habichuela','Montería, Mercado del Sur')).fetchone()[0]==6250
 print('Daily quote checked against DANE bulletin page 1')
 for alias in ['planning-method','coffee-development','potato-alhaja','fnc-price','input-index','first-market','ideam-bulletin']:
  assert db.execute('SELECT 1 FROM document_alias WHERE alias=%s',(alias,)).fetchone(),alias
 print('All in-app reference aliases resolve')
