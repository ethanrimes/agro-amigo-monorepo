"""Import real FNC, DANE and SFC observations. No synthetic prices or buyer offers.
Run: .venv/bin/python pipelines/demo/import_data.py [--cached]
A source failure aborts before any DB changes. Every run prunes outside 12 months.
"""
import argparse,calendar,json,math,re,subprocess,unicodedata,os
from datetime import date,datetime
from pathlib import Path
from urllib.parse import urljoin,urlencode,quote
from zoneinfo import ZoneInfo
import pandas as pd
import psycopg
import certifi
from psycopg import sql
from bs4 import BeautifulSoup
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[2]; HERE=Path(__file__).resolve().parent; CACHE=HERE/'cache'
FNC_PAGE='https://federaciondecafeteros.org/estadisticas-cafeteras/'
DANE_PAGE='https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/mayoristas-boletin-mensual-1'
TRM_PAGE='https://www.datos.gov.co/Econom-a-y-Finanzas/Tasa-de-Cambio-Representativa-del-Mercado-TRM/32sa-8pi3'
TODAY=datetime.now(ZoneInfo('America/Bogota')).date()
START=TODAY.replace(year=TODAY.year-1,day=min(TODAY.day,calendar.monthrange(TODAY.year-1,TODAY.month)[1]))
def in_window(day): return START<day<=TODAY
def slug(value): return re.sub(r'[^a-z0-9]+','-',unicodedata.normalize('NFKD',str(value)).encode('ascii','ignore').decode().lower()).strip('-')
def download(url,name,cached=False):
 CACHE.mkdir(exist_ok=True);path=CACHE/name
 if not cached or not path.exists():
  temp=path.with_suffix(path.suffix+'.tmp')
  subprocess.run(['curl','-fsSL','--retry','2','--connect-timeout','15','--max-time','90',url,'-o',str(temp)],check=True,capture_output=True)
  temp.replace(path)
 return path
def source_links(url,name,cached):
 page=download(url,name,cached)
 return [urljoin(url,a['href']) for a in BeautifulSoup(page.read_text(),'html.parser').select('a[href]')]
def finite(value):
 try: return math.isfinite(float(value)) and float(value)>0
 except (ValueError,TypeError): return False

def parse_dane(paths):
 products={};markets={};observations={};location={}
 for year,path,url in paths:
  book=pd.ExcelFile(path)
  if 'Fuentes' in book.sheet_names:
   for _,r in pd.read_excel(book,sheet_name='Fuentes').iterrows():
    location[str(r.iloc[0]).strip()]=(str(r['Municipio']).title(),str(r['Departamento']).title())
 for year,path,url in paths:
  df=pd.read_excel(path,sheet_name=str(year),header=5)
  required={'Fecha','Grupo','Producto','Mercado','Precio promedio por kilogramo*'}
  if not required.issubset(df.columns): raise ValueError(f'DANE schema changed: {year}')
  for _,r in df.iterrows():
   d=r.Fecha
   if not isinstance(d,(date,datetime)) or not finite(r['Precio promedio por kilogramo*']): continue
   # DANE dates monthly periods on the first; display their actual closing date.
   observed=date(d.year,d.month,calendar.monthrange(d.year,d.month)[1])
   if not in_window(observed): continue
   name=str(r.Producto).strip();pid=slug(name);market=str(r.Mercado).strip();mid='sipsa-'+slug(market)
   category={'VERDURAS Y HORTALIZAS':'Verduras','FRUTAS FRESCAS':'Frutas','TUBÉRCULOS, RAÍCES Y PLÁTANOS':'Tubérculos y plátanos','GRANOS Y CEREALES':'Granos y cereales','LÁCTEOS Y HUEVOS':'Lácteos y huevos','CARNES':'Carnes','PESCADOS':'Pescados','PRODUCTOS PROCESADOS':'Procesados'}.get(str(r.Grupo).strip(),str(r.Grupo).capitalize())
   category={'tuberculos-raices-y-platanos':'Tubérculos y plátanos','lacteos-y-huevos':'Lácteos y huevos','frutas-frescas':'Frutas','verduras-y-hortalizas':'Verduras','pescados':'Pescados','carnes':'Carnes','productos-procesados':'Procesados'}.get(slug(category),category)
   image='avocado' if pid.startswith('aguacate') else 'tomato' if pid.startswith('tomate') else 'potato' if pid.startswith('papa') else 'plantain' if pid.startswith('platano') else 'banana' if pid.startswith('banano') else 'produce'
   priority={'aguacate-hass':1,'tomate-chonto':2,'papa-criolla-limpia':3,'platano-harton-verde':4}.get(pid,100)
   products[pid]=(pid,name,category,image,priority)
   city,region=location.get(market,(market.split(',')[0],''))
   if 'Departamento' in r and pd.notna(r.Departamento): city,region=str(r.Municipio).title(),str(r.Departamento).title()
   region=region.replace(' De ',' de ').replace(' Del ',' del ')
   markets[mid]=(mid,market,city,region)
   row=(pid,mid,'dane-sipsa',observed,'monthly','kg',float(r['Precio promedio por kilogramo*']),url)
   key=(pid,mid,observed)
   if key in observations and observations[key][6]!=row[6]: raise ValueError(f'Conflicting source observation: {key}')
   observations[key]=row
 if not observations: raise ValueError('DANE import returned no in-window observations')
 return products,markets,list(observations.values())

def parse_fnc(excel,pdf,excel_url,pdf_url):
 df=pd.read_excel(excel,sheet_name='1. Precio Interno Diario ',header=5)
 history={}
 for _,r in df.iterrows():
  d=r.iloc[1]
  if isinstance(d,(date,datetime)) and finite(r.iloc[2]):
   day=d.date() if isinstance(d,datetime) else d
   if in_window(day): history[day]=(day,float(r.iloc[2]),excel_url)
 reader=PdfReader(pdf);text='\n'.join(p.extract_text() for p in reader.pages)
 months={m:i+1 for i,m in enumerate(['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre'])}
 match=re.search(r'([A-Za-z]+)\s+(\d{1,2})\s*/\s*(20\d{2})',text)
 if not match: raise ValueError('FNC publication date missing')
 day=date(int(match[3]),months[match[1].lower()],int(match[2]))
 if not in_window(day): raise ValueError('FNC bulletin outside demo window')
 price=re.search(r'125\s*Kg.*?FR\s*94\s+([\d,]+)\s+COP',text)
 if not price: raise ValueError('FNC 125kg FR94 reference missing')
 history[day]=(day,float(price[1].replace(',','')),pdf_url)
 factors=[(day,int(m[1]),float(m[2].replace(',','')),pdf_url) for m in re.finditer(r'^\s*(8[8-9]|9\d|100)\s+[\d.]+\s+[\d.]+\s+[\d,]+\s+[\d,]+\s+([\d,]+)\s*$',text,re.M)]
 if len(factors)!=13: raise ValueError(f'Expected FNC factors 88–100, got {len(factors)}')
 regions={'ARMENIA':'Quindío','BOGOTÁ':'Bogotá, D.C.','BUCARAMANGA':'Santander','BUGA':'Valle del Cauca','CHINCHINÁ':'Caldas','CÚCUTA':'Norte de Santander','IBAGUÉ':'Tolima','MANIZALES':'Caldas','MEDELLÍN':'Antioquia','NEIVA':'Huila','PAMPLONA':'Norte de Santander','PASTO':'Nariño','PEREIRA':'Risaralda','POPAYÁN':'Cauca','SANTA MARTA':'Magdalena','VALLEDUPAR':'Cesar'}
 markets={};observations=[]
 for match in re.finditer(r'^\s*([A-ZÁÉÍÓÚÑ ]+?)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s*$',reader.pages[1].extract_text(),re.M):
  city=match[1].strip()
  if city not in regions: continue
  mid='almacafe-'+slug(city);markets[mid]=(mid,'Almacafé · '+city.title(),city.title(),regions[city])
  observations.append(('cafe-pergamino-seco',mid,'fnc',day,'daily','125kg',float(match[2].replace(',','')),pdf_url))
 if len(markets)!=16: raise ValueError(f'Expected 16 Almacafé branches, got {len(markets)}')
 return list(history.values()),factors,markets,observations

def main(cached=False):
 fnc_links=source_links(FNC_PAGE,'fnc-page.html',cached)
 excel_url=next(u for u in fnc_links if u.endswith('.xlsx') and 'Precios' in u)
 pdf_url=next(u for u in fnc_links if u.endswith('precio_cafe.pdf'))
 dane_links=source_links(DANE_PAGE,'dane-page.html',cached)
 paths=[]
 for year in sorted({START.year,TODAY.year}):
  url=next(u for u in dane_links if 'SerieHistoricaMayorista' in u and str(year) in u)
  paths.append((year,download(url,f'dane{year}.xlsx',cached),url))
 print('Parsing official DANE and FNC files…',flush=True)
 products,markets,observations=parse_dane(paths)
 history,factors,coffee_markets,coffee_obs=parse_fnc(download(excel_url,'fnc.xlsx',cached),download(pdf_url,'fnc.pdf',cached),excel_url,pdf_url)
 products['cafe-pergamino-seco']=('cafe-pergamino-seco','Café pergamino seco','Café','coffee',0)
 markets.update(coffee_markets);observations.extend(coffee_obs)
 trm_url='https://www.datos.gov.co/resource/32sa-8pi3.json?'+urlencode({'$where':f"vigenciadesde > '{START}T00:00:00' AND vigenciadesde <= '{TODAY}T23:59:59'",'$order':'vigenciadesde ASC','$limit':1000})
 trm=json.loads(download(trm_url,'trm.json',cached).read_text());rates=[]
 for r in trm:
  day=date.fromisoformat(r['vigenciadesde'][:10]);until=date.fromisoformat(r['vigenciahasta'][:10])
  if in_window(day) and finite(r['valor']): rates.append((day,until,float(r['valor']),TRM_PAGE))
 if not rates: raise ValueError('SFC TRM returned no records')
 summary={'products':len(products),'markets':len(markets),'wholesale_observations':len(observations)-len(coffee_obs),'coffee_days':len(history),'coffee_branches':len(coffee_markets),'coffee_factors':len(factors),'exchange_rates':len(rates),'oldest':str(min(o[3] for o in observations)),'newest_wholesale':str(max(o[3] for o in observations if o[2]=='dane-sipsa')),'newest_coffee':str(max(h[0] for h in history))}
 config=json.loads((ROOT/'.azure-local/database.json').read_text())
 with psycopg.connect(host=config['host'],dbname=config['database'],user=config['user'],password=config['password'],sslmode='verify-full',sslrootcert=certifi.where(),connect_timeout=15) as conn:
  with conn.cursor() as cur:
   cur.execute((HERE/'schema.sql').read_text())
   for table in ['price_observation','coffee_reference','coffee_factor','exchange_rate','buyer_offer']:
    cur.execute(sql.SQL('DELETE FROM {} WHERE observed_on<=%s OR observed_on>%s').format(sql.Identifier(table)),(START,TODAY))
   cur.executemany('INSERT INTO source VALUES (%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET url=excluded.url',[
    ('dane-sipsa','DANE · SIPSA',DANE_PAGE,'monthly'),('fnc','Federación Nacional de Cafeteros',FNC_PAGE,'daily'),('sfc','Superintendencia Financiera',TRM_PAGE,'daily')])
   cur.executemany('INSERT INTO product VALUES (%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET name=excluded.name,category=excluded.category,image_key=excluded.image_key,priority=excluded.priority',products.values())
   cur.executemany('INSERT INTO market VALUES (%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET name=excluded.name,city=excluded.city,region=excluded.region',markets.values())
   cur.executemany('INSERT INTO price_observation(product_id,market_id,source_id,observed_on,period,unit,price,source_url) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(product_id,market_id,source_id,observed_on,period,unit) DO UPDATE SET price=excluded.price,source_url=excluded.source_url,fetched_at=now()',observations)
   cur.executemany('INSERT INTO coffee_reference(observed_on,price,source_url) VALUES (%s,%s,%s) ON CONFLICT(observed_on) DO UPDATE SET price=excluded.price,source_url=excluded.source_url',history)
   cur.executemany('INSERT INTO coffee_factor VALUES (%s,%s,%s,%s) ON CONFLICT(observed_on,factor) DO UPDATE SET price=excluded.price,source_url=excluded.source_url',factors)
   cur.executemany('INSERT INTO exchange_rate VALUES (%s,%s,%s,%s) ON CONFLICT(observed_on) DO UPDATE SET price=excluded.price,valid_until=excluded.valid_until',rates)
   cur.execute('INSERT INTO import_run(window_start,window_end,summary) VALUES (%s,%s,%s)',(START,TODAY,json.dumps(summary)))
   cur.execute("SELECT 1 FROM pg_roles WHERE rolname='agro_reader'")
   if not cur.fetchone(): cur.execute(sql.SQL('CREATE ROLE agro_reader LOGIN PASSWORD {}').format(sql.Literal(config['appPassword'])))
   cur.execute('GRANT CONNECT ON DATABASE agroamigo TO agro_reader; GRANT USAGE ON SCHEMA public TO agro_reader; GRANT SELECT ON source,product,market,price_observation,coffee_reference,coffee_factor,exchange_rate TO agro_reader')
  conn.commit()
  conn.execute('ANALYZE')
 env=ROOT/'apps/web/.env.local'
 connection=f"postgresql://agro_reader:{quote(config['appPassword'],safe='')}@{config['host']}:5432/{config['database']}"
 fd=os.open(env,os.O_CREAT|os.O_WRONLY|os.O_TRUNC,0o600)
 with os.fdopen(fd,'w') as f: f.write('DATABASE_URL='+connection+'\n')
 (HERE/'import-summary.json').write_text(json.dumps({'window_start_exclusive':str(START),'window_end_inclusive':str(TODAY),**summary},indent=2)+'\n')
 print(json.dumps(summary,indent=2),flush=True)
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--cached',action='store_true');args=parser.parse_args();main(args.cached)
