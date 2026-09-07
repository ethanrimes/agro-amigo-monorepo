"""Import the last 12 months of DANE SIPSA-A; archive originals and exact source rows.
Run from root: .venv/bin/python pipelines/market/import_supply.py [--cached]
Monthly aggregates retain actual date coverage. Only exact product names are linked;
source foods with different variety/physical-state definitions stay separate.
"""
import argparse, calendar, hashlib, json, math, re, subprocess, sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import certifi, openpyxl, psycopg
from psycopg.types.json import Jsonb
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'pipelines/planning'))
from import_references import doc, slug
HERE = Path(__file__).resolve().parent
CACHE = HERE / 'cache'
TODAY = datetime.now(ZoneInfo('America/Bogota')).date()
START = TODAY.replace(year=TODAY.year-1, day=min(TODAY.day, calendar.monthrange(TODAY.year-1,TODAY.month)[1]))

def ranges(numbers):
    result = []
    for n in numbers:
        if result and n == result[-1][1]+1: result[-1][1] = n
        else: result.append([n,n])
    return result

def parse(path):
    groups = {}
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    for sheet in book:
        if not re.fullmatch(r'2\.[123]', sheet.title): continue
        # The first two four-month sheets of the previous year cannot overlap September.
        if int(path.stem[-4:]) == START.year and int(sheet.title[-1])*4 < START.month: continue
        header = next(sheet.iter_rows(min_row=9,max_row=9,values_only=True))
        if header[0] != 'Ciudad, Mercado Mayorista' or header[8] != 'Alimento' or header[9] != 'Cant Kg': raise ValueError('DANE supply schema changed')
        for index, row in enumerate(sheet.iter_rows(min_row=10,values_only=True),10):
            if not isinstance(row[1],datetime): continue
            day = row[1].date()
            if not START < day <= TODAY: continue
            if not row[0] or not row[8] or not isinstance(row[9],(int,float)) or not math.isfinite(row[9]) or row[9] < 0: raise ValueError(f'Invalid supply row {sheet.title}:{index}')
            key=(str(row[0]).strip(),str(row[8]).strip(),day.replace(day=1))
            if key not in groups: groups[key]={'kg':0,'days':set(),'category':str(row[6]).strip(),'rows':defaultdict(list)}
            g=groups[key];g['kg']+=row[9];g['days'].add(day);g['rows'][sheet.title].append(index)
        print(path.name,sheet.title,'groups',len(groups),flush=True)
    book.close()
    if not groups: raise ValueError('No in-window supply data')
    return groups

def main(cached):
    CACHE.mkdir(parents=True,exist_ok=True)
    batches=[]
    for year in range(START.year,TODAY.year+1):
        path=CACHE/f'supply-{year}.xlsx'
        url=f'https://www.dane.gov.co/files/operaciones/SIPSA/anex-Microdato-abastecimiento-{year}.xlsx'
        if not cached or not path.exists():
            temp=path.with_suffix('.part')
            subprocess.run(['curl','-fsSL','--connect-timeout','20','--max-time','600',url,'-o',str(temp)],check=True)
            temp.replace(path)
        batches.append((year,path,url,parse(path)))
    c=json.loads((ROOT/'.azure-local/database.json').read_text())
    with psycopg.connect(host=c['host'],dbname=c['database'],user=c['user'],password=c['password'],sslmode='verify-full',sslrootcert=certifi.where(),connect_timeout=15) as db:
        cur=db.cursor();cur.execute((HERE/'schema.sql').read_text())
        products={slug(n):pid for pid,n in cur.execute('SELECT id,name FROM product')}
        markets={mid:(n,city,region) for mid,n,city,region in cur.execute('SELECT id,name,city,region FROM market')}
        places={(slug(n),slug(d)):(mid,n,d) for mid,n,d in cur.execute('SELECT id,name,department FROM municipality')}
        city_alias={'bogota':'bogota-d-c','santafe-de-bogota-d-c':'bogota-d-c','cucuta':'san-jose-de-cucuta','buga':'guadalajara-de-buga','cartagena':'cartagena-de-indias','cali':'santiago-de-cali'}
        missing=[]
        for mid,(name,city,region) in markets.items():
            key=(city_alias.get(slug(city),slug(city)),slug(region))
            place=places.get(key)
            if place: cur.execute('UPDATE market SET municipality_id=%s WHERE id=%s',(place[0],mid))
            else: missing.append(mid)
        allrows=[];summaries=[]
        for year,path,url,groups in batches:
            did=doc(cur,path,f'DANE SIPSA-A — microdatos de abastecimiento {year}','DANE',url,year,f'supply-{year}',metadata={'dataset':'supply','unit':'kg','aggregation':'Sum of exact source rows by food, destination market and calendar month. Only the rolling 12-month window is imported; partial periods retain actual date coverage.'})
            unmatched=set()
            for (market,food,period),g in groups.items():
                mid='sipsa-'+slug(market)
                if mid not in markets:
                    city=market.split(',')[0].strip();citykey=city_alias.get(slug(city),slug(city))
                    found=[v for (n,d),v in places.items() if n==citykey]
                    if len(found)!=1: raise ValueError(f'Ambiguous supply market municipality: {market}')
                    place=found[0]
                    cur.execute('INSERT INTO market(id,name,city,region,municipality_id) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(id) DO NOTHING',(mid,market,place[1],place[2].title(),place[0]))
                    markets[mid]=(market,place[1],place[2])
                pid=products.get(slug(food))
                if not pid: unmatched.add(food)
                allrows.append((mid,slug(food),food,pid,g['category'],period,max(g['days']),min(g['days']),g['kg'],len(g['days']),did,Jsonb({s:ranges(v) for s,v in g['rows'].items()})))
            summaries.append({'year':year,'sha256':did,'url':url,'groups':len(groups),'unmatched_foods':sorted(unmatched)})
        # Preserve older periods. Database triggers retain every revised snapshot.
        cur.execute('CREATE TEMP TABLE supply_stage (LIKE supply_observation) ON COMMIT DROP')
        with cur.copy('COPY supply_stage(market_id,food_id,food_name,product_id,category,period_start,observed_on,first_reported_on,quantity_kg,reporting_days,document_id,source_rows) FROM STDIN') as copy:
            for row in allrows: copy.write_row(row)
        cur.execute('''INSERT INTO supply_observation SELECT * FROM supply_stage
            ON CONFLICT(market_id,food_id,period_start) DO UPDATE SET
            observed_on=excluded.observed_on,first_reported_on=excluded.first_reported_on,
            quantity_kg=excluded.quantity_kg,reporting_days=excluded.reporting_days,
            document_id=excluded.document_id,source_rows=excluded.source_rows''')
        cur.execute('''INSERT INTO supply_observation SELECT * FROM supply_stage ON CONFLICT(market_id,food_id,period_start) DO UPDATE SET observed_on=excluded.observed_on,first_reported_on=excluded.first_reported_on,quantity_kg=excluded.quantity_kg,reporting_days=excluded.reporting_days,document_id=excluded.document_id,source_rows=excluded.source_rows WHERE (supply_observation.quantity_kg,supply_observation.document_id) IS DISTINCT FROM (excluded.quantity_kg,excluded.document_id)''')
        cur.execute('ANALYZE supply_observation')
        result={'window_start_exclusive':str(START),'window_end':str(TODAY),'aggregates':len(allrows),'unlocated_price_markets':missing,'sources':summaries}
    (HERE/'import-summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('Imported',len(allrows),'supply aggregates; unmapped price-market locations:',missing,flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--cached',action='store_true');main(p.parse_args().cached)
