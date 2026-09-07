"""Load reproducible planning references and immutable evidence into Azure PostgreSQL.
Current observations retain the 12-month guard. Five complete years support seasonality.
Run after demo/import_data.py and planning/fetch_references.py.
"""
import calendar,csv,hashlib,io,json,math,re,sys,unicodedata
from collections import defaultdict
from datetime import date,datetime
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo
import certifi,pandas as pd,psycopg
from psycopg.types.json import Jsonb
from pypdf import PdfReader
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph,Table,TableStyle
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent;CACHE=HERE/'cache';DEMO=ROOT/'pipelines/demo/cache';OUT=ROOT/'output/pdf';OUT.mkdir(parents=True,exist_ok=True)
URLS=json.loads((CACHE/'download-urls.json').read_text())
TODAY=datetime.now(ZoneInfo('America/Bogota')).date();START=TODAY.replace(year=TODAY.year-1,day=min(TODAY.day,calendar.monthrange(TODAY.year-1,TODAY.month)[1]))
def slug(s):return re.sub('[^a-z0-9]+','-',unicodedata.normalize('NFKD',str(s)).encode('ascii','ignore').decode().lower()).strip('-')
def money(v):return '$ '+f'{v:,.2f}'.replace(',','X').replace('.',',').replace('X','.')
def doc(cur,path,title,publisher,url,period,alias=None,kind='original',metadata=None,media=None):
 data=path.read_bytes();did=hashlib.sha256(data).hexdigest();suffix=path.suffix.lower()
 mime=media or {'.pdf':'application/pdf','.xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','.json':'application/json','.tsv':'text/tab-separated-values','.html':'text/html'}.get(suffix,'text/plain')
 pages=len(PdfReader(io.BytesIO(data)).pages) if mime=='application/pdf' else None
 cur.execute('INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,page_count,content,metadata) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO NOTHING',(did,title,publisher,url,mime,kind,str(period),pages,data,Jsonb(metadata or {})))
 if alias:cur.execute('INSERT INTO document_alias VALUES (%s,%s) ON CONFLICT(alias) DO UPDATE SET document_id=excluded.document_id',(alias,did))
 return did

def pdf_extract(name,title,headers,rows,parents):
 """24 rows per page: stable page locators, exact source-sheet row references."""
 p=OUT/(name+'.pdf');c=canvas.Canvas(str(p),pagesize=(612,792),invariant=1)
 c.setTitle(title);c.setAuthor('AgroAmigo - extracto verificable de datos oficiales')
 style=ParagraphStyle('cell',fontName='Helvetica',fontSize=8.5,leading=10,textColor=colors.HexColor('#233c30'))
 for start in range(0,len(rows),24):
  c.setFillColor(colors.HexColor('#164b35'));c.rect(0,770,612,22,fill=1,stroke=0)
  c.setFont('Helvetica-Bold',17);c.drawString(38,740,'agroamigo | Evidencia del dato')
  c.setFont('Helvetica-Bold',12);c.drawString(38,715,title[:85])
  c.setFont('Helvetica',9);c.drawString(38,695,'EXTRACTO GENERADO POR AGROAMIGO. El original de la entidad es un archivo de datos.')
  c.drawString(38,680,'COP nominales. Precios mayoristas mensuales; no son pagos en finca ni ofertas de compradores.' if name!='coffee-history' and not name.startswith('daily-') else 'Diario, COP/kg; * variedad predominante por mercado. No es una oferta de compra.' if name.startswith('daily-') else 'COP por carga de 125 kg de cafe pergamino seco. Referencia nacional FNC.')
  c.drawString(38,665,'La ultima columna identifica el libro/hoja y la fila exacta del archivo original archivado.')
  values=[headers]+[[Paragraph(str(v).replace('&','&amp;').replace('<','&lt;'),style) for v in r] for r in rows[start:start+24]]
  table=Table(values,colWidths=[72,236,85,143],rowHeights=[25]+[21]*len(rows[start:start+24]))
  table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e8f0e8')),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,0),9),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f6f8f4')]),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5)]))
  w,h=table.wrap(536,600);table.drawOn(c,38,646-h)
  c.setFont('Helvetica',8);c.setFillColor(colors.HexColor('#526259'))
  c.drawString(38,70,'Originales inmutables en Azure: ver los enlaces del visor para descargar los archivos completos.')
  for i,parent in enumerate(parents[-2:]):c.drawString(38,56-i*11,'SHA-256: '+parent)
  c.drawRightString(574,24,f'Pagina {start//24+1} de {math.ceil(len(rows)/24)}');c.showPage()
 c.save();return p

def dane_rows(year,path):
 book=pd.ExcelFile(path)
 sheets=[str(year)] if str(year) in book.sheet_names else book.sheet_names[1:]
 for sheet in sheets:
  header=5 if sheet==str(year) else 6
  df=pd.read_excel(book,sheet_name=sheet,header=header)
  if not {'Fecha','Producto','Mercado','Precio promedio por kilogramo*'}.issubset(df.columns):raise ValueError(f'Unexpected DANE schema {year}/{sheet}')
  for idx,r in df.iterrows():
   d=r['Fecha'];price=r['Precio promedio por kilogramo*']
   if not isinstance(d,(date,datetime)) or pd.isna(price) or not isinstance(price,(float,int)) or price<=0:continue
   yield {'product':slug(r['Producto']),'name':str(r['Producto']).strip(),'market':'sipsa-'+slug(r['Mercado']),'market_name':str(r['Mercado']).strip(),'year':d.year,'month':d.month,'price':float(price),'sheet':sheet,'row':int(idx)+header+2,'date':date(d.year,d.month,calendar.monthrange(d.year,d.month)[1])}

def prices(cur):
 products={r[0]:r[1] for r in cur.execute('SELECT id,name FROM product').fetchall()};books={};current=defaultdict(list);years=defaultdict(dict);locators=defaultdict(dict);conflicts=set()
 for y in range(TODAY.year-5,TODAY.year+1):
  p=(DEMO if y>=2025 else CACHE)/f'dane{y}.xlsx'
  url=URLS.get(f'dane{y}.xlsx') or f'https://www.dane.gov.co/files/operaciones/SIPSA/anex-SIPSA-SerieHistoricaMayorista-{y}.xlsx'
  did=doc(cur,p,f'DANE SIPSA - precios mayoristas {y}','DANE',url,y,f'dane-{y}');books[y]=did
  for r in dane_rows(y,p):
   if r['product'] not in products:continue
   if y<TODAY.year:
    key=(r['product'],r['market'],y)
    if r['month'] in years[key] and years[key][r['month']]!=r['price']:conflicts.add(key)
    years[key][r['month']]=r['price'];locators[key][r['month']]=f"{r['sheet']}!fila {r['row']}"
   if START<r['date']<=TODAY:current[r['product']].append(r)
  print('Parsed DANE',y,flush=True)
 seasonal=[]
 for (pid,mid,y),months in years.items():
  if len(months)==12 and (pid,mid,y) not in conflicts:seasonal.append((pid,mid,y,Jsonb([months[m] for m in range(1,13)]),books[y],Jsonb([locators[(pid,mid,y)][m] for m in range(1,13)])))
 cur.execute('DELETE FROM seasonal_year WHERE reference_year<%s OR reference_year>=%s',(TODAY.year-5,TODAY.year))
 cur.executemany('INSERT INTO seasonal_year VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(product_id,market_id,reference_year) DO UPDATE SET monthly_prices=excluded.monthly_prices,document_id=excluded.document_id,source_rows=excluded.source_rows',seasonal)
 for pid,obs in current.items():
  obs.sort(key=lambda r:(-r['date'].toordinal(),r['market_name']));parents=sorted({books[r['year']] for r in obs})
  rows=[[str(r['date']),r['market_name'],money(r['price']),f"{r['year']} / {r['sheet']} / {r['row']}"] for r in obs]
  p=pdf_extract('price-'+pid,products[pid],['Periodo','Mercado','COP / kg','Libro / hoja / fila'],rows,parents)
  did=doc(cur,p,'Precios de '+products[pid]+' - extracto DANE','DANE / extracto AgroAmigo','https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/mayoristas-boletin-mensual-1',f'{START} a {TODAY}','price-'+pid,kind='extract',metadata={'parents':parents,'product_id':pid,'method':'Filas originales de los libros DANE SIPSA, sin alterar precios. Fecha mensual presentada como cierre de mes.'})
  cur.executemany('UPDATE price_observation SET document_id=%s,source_locator=%s WHERE product_id=%s AND market_id=%s AND observed_on=%s AND source_id=\'dane-sipsa\'',[(did,f"PDF p. {i//24+1}; libro {r['year']}, hoja {r['sheet']}, fila {r['row']}",pid,r['market'],r['date']) for i,r in enumerate(obs)])
 (HERE/'seasonality-exclusions.json').write_text(json.dumps({'reason':'Conflicting duplicate source prices; entire market-year excluded','excluded':sorted(conflicts)},indent=2))
 print('Archived price extracts',len(current),'complete market-years',len(seasonal),'conflicting market-years excluded',len(conflicts),flush=True)
 fnc_url=cur.execute('SELECT source_url FROM coffee_reference WHERE source_url LIKE %s LIMIT 1',('%.xlsx',)).fetchone()[0]
 fnc=doc(cur,DEMO/'fnc.xlsx','FNC - series cafeteras','Federación Nacional de Cafeteros',fnc_url,'Serie histórica, archivo consultado '+str(TODAY),'fnc-workbook')
 pdfurl=cur.execute('SELECT source_url FROM coffee_factor LIMIT 1').fetchone()[0]
 fncpdf=doc(cur,DEMO/'fnc.pdf','FNC - precio de compra y factores','Federación Nacional de Cafeteros',pdfurl,str(cur.execute('SELECT max(observed_on) FROM coffee_factor').fetchone()[0]),'fnc-price')
 df=pd.read_excel(DEMO/'fnc.xlsx',sheet_name='1. Precio Interno Diario ',header=5);dayrows={};annual=defaultdict(list)
 for i,r in df.iterrows():
  d=r.iloc[1];v=r.iloc[2]
  if isinstance(d,(date,datetime)) and isinstance(v,(float,int)) and math.isfinite(v) and v>0:
   d=d.date() if isinstance(d,datetime) else d
   dayrows[d]=(float(v),i+7)
   if TODAY.year-5<=d.year<TODAY.year:annual[(d.year,d.month)].append((v,i+7))
 for y in range(TODAY.year-5,TODAY.year):
  if all(annual[(y,m)] for m in range(1,13)):
   cur.execute('INSERT INTO seasonal_year VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(product_id,market_id,reference_year) DO UPDATE SET monthly_prices=excluded.monthly_prices,document_id=excluded.document_id,source_rows=excluded.source_rows',('cafe-pergamino-seco','fnc-national',y,Jsonb([sum(v for v,i in annual[(y,m)])/len(annual[(y,m)])/125 for m in range(1,13)]),fnc,Jsonb([f"1. Precio Interno Diario, filas {min(i for v,i in annual[(y,m)])}-{max(i for v,i in annual[(y,m)])}" for m in range(1,13)])))
 days=cur.execute('SELECT observed_on,price FROM coffee_reference ORDER BY observed_on DESC').fetchall()
 rows=[[str(d),'Referencia nacional FNC',money(float(v)),f'Hoja 1 / fila {dayrows[d][1]}' if d in dayrows else 'Boletín FNC p. 1'] for d,v in days]
 extract=pdf_extract('coffee-history','Café pergamino seco - historia diaria',['Fecha','Referencia','COP / 125 kg','Libro / hoja / fila'],rows,[fnc])
 did=doc(cur,extract,'FNC - referencia diaria, extracto verificable','FNC / extracto AgroAmigo',fnc_url,f'{START} a {TODAY}','coffee-history',kind='extract',metadata={'parents':[fnc],'method':'Precios diarios originales. No se interpolan días faltantes.'})
 cur.execute('UPDATE coffee_reference SET document_id=CASE WHEN source_url LIKE %s THEN %s ELSE %s END',('%.pdf',fncpdf,did));cur.execute('UPDATE coffee_factor SET document_id=%s',(fncpdf,));cur.execute("UPDATE price_observation SET document_id=%s,source_locator='PDF p. 2; tabla Almacafé' WHERE source_id='fnc'",(fncpdf,))
 trm=doc(cur,DEMO/'trm.json','SFC - tasa representativa del mercado','Superintendencia Financiera','https://www.datos.gov.co/resource/32sa-8pi3.json',f'{START} a {TODAY}','trm')
 cur.execute('UPDATE exchange_rate SET document_id=%s',(trm,))

def farms(cur):
 path=ROOT/'data/divipola_municipios.tsv'
 did=doc(cur,path,'Municipios de Colombia - DIVIPOLA','DANE','https://www.dane.gov.co/index.php/servicios-al-ciudadano/servicios-informacion/divipola','Directorio de referencia del repositorio; coordenadas municipales','municipalities',metadata={'note':'Puntos municipales de referencia; no delimitan ni ubican una finca.'})
 municipalities={};lookup={}
 for r in csv.DictReader(path.open(),delimiter='\t'):
  mid=r['Código (Municipio)'].zfill(5);name=r['Nombre (Municipio)'];dep=r['Nombre (Departamento)']
  municipalities[mid]=(mid,name,dep,r['Código (Departamento)'].zfill(2),float(r['Latitud']),float(r['Longitud']),did);lookup[(slug(dep),slug(name))]=mid
 cur.executemany('INSERT INTO municipality VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO NOTHING',municipalities.values())
 eva=doc(cur,CACHE/'eva-2025.json','UPRA - producción municipal EVA 2025','UPRA',URLS['eva-2025.json'],'2025','eva-2025',metadata={'units':'Área: ha. Producción: toneladas. Rendimiento calculado: producción / área cosechada × 1000. Desagregado por variedad y sistema.'})
 grouped={}
 for i,r in enumerate(json.loads((CACHE/'eva-2025.json').read_text())):
  mid=r['c_digo_dane_municipio'].zfill(5)
  if mid not in municipalities:continue
  key=(mid,r['c_digo_del_cultivo']);entry=grouped.setdefault(key,[r,0,0,0,[]])
  entry[1]+=float(r.get('rea_sembrada',0));entry[2]+=float(r.get('rea_cosechada',0));entry[3]+=float(r.get('producci_n',0));entry[4].append(i+1)
 rows=[]
 for (mid,code),(r,planted,harvested,produced,indices) in grouped.items():
  rows.append((mid,code,r['cultivo'],r['desagregaci_n_cultivo'],2025,r['ciclo_del_cultivo'],r['estado_f_sico_del_cultivo'],planted,harvested,produced,produced/harvested*1000 if harvested>0 else None,eva,Jsonb(indices)))
 cur.executemany('INSERT INTO crop_reference VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(municipality_id,crop_code,reference_year) DO UPDATE SET planted_ha=excluded.planted_ha,harvested_ha=excluded.harvested_ha,production_t=excluded.production_t,yield_kg_ha=excluded.yield_kg_ha,document_id=excluded.document_id,source_rows=excluded.source_rows',rows)
 cal=doc(cur,CACHE/'calendars.json','UPRA - calendarios departamentales de siembra y cosecha','UPRA',URLS['calendars.json'],'2024','calendars',metadata={'note':'Porcentajes mensuales históricos de área; no son una recomendación de fecha de siembra.'})
 calrows=[]
 for i,r in enumerate(json.loads((CACHE/'calendars.json').read_text())):
  vals=[float(r.get(m,0)) for m in ['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic']]
  if not all(0<=v<=100 for v in vals):raise ValueError('Calendar value out of range')
  calrows.append((r['c_digo_departamento'].zfill(2),r['cultivo'],r['calendario'],int(r['anio_eva']),Jsonb(vals),cal,i+1))
 cur.executemany('INSERT INTO crop_calendar VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(department_id,crop,activity,reference_year) DO UPDATE SET percentages=excluded.percentages,document_id=excluded.document_id,source_row=excluded.source_row',calrows)
 print('Farm references',len(municipalities),len(rows),len(calrows),flush=True)
 for p in sorted(CACHE.glob('aptitude-*.json')):
  key=p.stem.removeprefix('aptitude-')
  if '-meta' in key or '-dept-' in key or re.search(r'-\d+$',key) or key in ['services','soy']:continue
  data=json.loads(p.read_text())
  if 'pages' not in data:continue
  meta=json.loads((CACHE/f'aptitude-{key}-meta.json').read_text());base=f'https://sig.upra.gov.co/server/rest/services/aptitud_uso_suelo/aptitud_{key}/MapServer/0'
  did=doc(cur,p,meta['name'],'UPRA · SIPRA',base,'Zonificación de referencia; ver año y escala en metadatos','suitability-'+key,kind='extract',metadata={'description':BeautifulText(meta.get('description','')),'scale':'1:100.000 (referencia regional)','note':'Suma de áreas por municipio y categoría. No evalúa un predio. El archivo conserva cada consulta y su respuesta.'})
  values=[];seen=set()
  for page in data['pages']:
   for feat in page['response']['features']:
    r=feat['attributes'];mid=r['cod_dane_mpio'];classification=r['aptitud'];ident=(mid,classification)
    if ident in seen:raise ValueError('Duplicate suitability group')
    seen.add(ident)
    if mid in municipalities and r['area_ha'] is not None:values.append((mid,key,classification,r['area_ha'],did))
  cur.executemany('INSERT INTO crop_suitability VALUES (%s,%s,%s,%s,%s) ON CONFLICT(municipality_id,crop_key,classification) DO UPDATE SET area_ha=excluded.area_ha,document_id=excluded.document_id',values)
  print('Imported suitability',key,len(values),flush=True)
 soilpath=CACHE/'soils.json'
 if soilpath.exists():
  did=doc(cur,soilpath,'AGROSAVIA - resultados públicos de análisis de suelos','AGROSAVIA',URLS['soils.json'],'Muestras históricas de laboratorio; fechas de análisis en cada registro','soils',metadata={'note':'Muestreo por demanda del servicio, sin coordenadas de parcela. No representa el suelo de todas las fincas de un municipio. Valores censurados (<) excluidos de los percentiles.'})
  samples=defaultdict(list)
  for r in json.loads(soilpath.read_text()):
   mid=lookup.get((slug(r.get('departamento','')),slug(r.get('municipio',''))))
   if mid:samples[mid].append(r)
  vals=[]
  for mid,rs in samples.items():
   ph=[];om=[];dates=[]
   for r in rs:
    for key,out in [('ph_agua_suelo',ph),('materia_organica',om)]:
     value=str(r.get(key,'')).replace(',','.')
     if re.fullmatch(r'\d+(\.\d+)?',value):
      v=float(value)
      if (key=='ph_agua_suelo' and 0<v<=14) or (key=='materia_organica' and 0<=v<=100):out.append(v)
    try:dates.append(datetime.strptime(r['fecha_de_an_lisis'],'%d/%m/%Y').date())
    except (ValueError,KeyError):pass
   dates=[d for d in dates if d<=TODAY]
   vals.append((mid,len(rs),len(ph),median(ph) if ph else None,float(pd.Series(ph).quantile(.25)) if ph else None,float(pd.Series(ph).quantile(.75)) if ph else None,median(om) if om else None,min(dates) if dates else None,max(dates) if dates else None,did))
  cur.executemany('INSERT INTO soil_reference VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(municipality_id) DO UPDATE SET samples=excluded.samples,ph_samples=excluded.ph_samples,ph_median=excluded.ph_median,ph_low=excluded.ph_low,ph_high=excluded.ph_high,organic_matter_median=excluded.organic_matter_median,oldest=excluded.oldest,newest=excluded.newest,document_id=excluded.document_id',vals)
  print('Soil municipalities',len(vals),flush=True)

def BeautifulText(html):
 from bs4 import BeautifulSoup
 return BeautifulSoup(html,'html.parser').get_text(' ',strip=True)

def main():
 config=json.loads((ROOT/'.azure-local/database.json').read_text())
 with psycopg.connect(host=config['host'],dbname=config['database'],user=config['user'],password=config['password'],sslmode='verify-full',sslrootcert=certifi.where(),connect_timeout=15) as conn:
  cur=conn.cursor();cur.execute((HERE/'schema.sql').read_text());conn.commit()
  if '--prices-only' in sys.argv:prices(cur)
  elif '--farms-only' in sys.argv:farms(cur)
  else:prices(cur);farms(cur)
  conn.commit();conn.execute('ANALYZE')
  print('Committed reference data and evidence.',flush=True)
if __name__=='__main__':main()
