"""Parse checked UPRA aggregate cost tables and DANE input-price observations.
Pesticide quantities in historical publications are never turned into application advice.
"""
from import_references import *
from cost_regions import ARVEJA_SOURCE, arveja_municipalities, cost_region
from cost_junca import SOURCE as JUNCA_SOURCE, parse_junca_tables
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import subprocess

def number_co(s):return float(s.replace('.','').replace(',','.'))
def amount(text,label):
 m=re.search(r'^\s*'+label+r'\s*\$?\s*([\d][\d.,]+)',text,re.I|re.M)
 return number_co(m[1]) if m else None

def costs(cur):
 municipalities=cur.execute('SELECT id,name,department FROM municipality').fetchall();report=[]
 files={'cost-20231018_Ficha_papa_2023.pdf':('Papa',2023),'cost-20231009_BolCostos_Frijol.pdf':('Frijol',2023),'cost-20231019_BolCostos_Tomate.pdf':('Tomate',2023),'cost-20231222_Boletin_YUCA_Dic-2023_DG.pdf':('Yuca',2023),'cost-20231009_BolCostos_Cebolla.pdf':('Cebolla de bulbo',2023),'cost-01_BolCostArv_20240925.pdf':('Arveja',2024),'cost-01_FicCostPlat_20250310.pdf':('Plátano',2024)}
 for name,(crop,year) in files.items():
  p=CACHE/name;did=doc(cur,p,f'UPRA - estructura de costos de {crop.lower()} {year}','UPRA',URLS[name],year,'cost-'+slug(crop))
  reader=PdfReader(p)
  for i,page in enumerate(reader.pages):
   if crop=='Plátano' and i!=24:continue # Table 8, one-year Ariari system; other tables span multiple years.
   text=page.extract_text();total=amount(text,r'total\s+costos');labor=amount(text,r'mano\s+de\s+obra\s*/\s*maquinaria');inputs=amount(text,'insumos');harvest=amount(text,'cosecha')
   yield_match=re.search(r'producci[oó]n\s+total\s*(?:\(?t/ha\)?)?\s+([\d.,]+)',text,re.I)
   if None in (total,labor,inputs,harvest) or not yield_match:continue
   # Source titles may follow the table. Select the region adjacent to its cost heading.
   region=cost_region(text,name,i+1,crop,year)
   if not region:continue
   out_yield=number_co(yield_match[1])*1000
   if total<=0 or out_yield<=0 or labor<harvest or total-labor-inputs< -2:raise ValueError(f'Invalid cost table {name}/{i+1}')
   foot=re.search(r'\*\s*Incluye(.*?)(?:\*\*|Fuente:|$)',text,re.S|re.I);foot=slug(foot[1]) if foot else ''
   codes=[mid for mid,mun,dep in municipalities if slug(dep) in foot and ('-'+slug(mun)+'-') in ('-'+foot+'-')]
   if name==ARVEJA_SOURCE:codes=arveja_municipalities(text,i+1,municipalities)
   lines=[{'label':'Labores antes de cosecha','amount':round(labor-harvest,2),'timing':'before'},{'label':'Semilla e insumos','amount':inputs,'timing':'before'},{'label':'Mano de obra de cosecha','amount':harvest,'timing':'harvest'},{'label':'Otros rubros del total publicado','amount':round(max(0,total-labor-inputs),2),'timing':'before'}]
   ident=slug(crop)+'-'+str(year)+'-'+str(i+1)
   notes='Pesos nominales del período del estudio, sin actualización automática. Otros rubros pueden incluir transporte y empaques: evita contarlos dos veces. La asignación del momento de pago es editable; no proviene de un calendario financiero de UPRA.'
   system='Monocultivo, región Ariari; ciclo de un año' if crop=='Plátano' else 'Sistema regional reportado por UPRA; consultar variedades y tecnología en la tabla'
   cur.execute('INSERT INTO cost_template VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET costs=excluded.costs,document_id=excluded.document_id,municipalities=excluded.municipalities',(ident,crop,crop+' · '+region,region,Jsonb(codes),year,system,out_yield,Jsonb(lines),did,i+1,notes))
   report.append({'id':ident,'source':name,'page':i+1,'region':region,'total':total,'yield_kg_ha':out_yield,'municipalities':codes})
 # This publication has an explicitly continued table and a different total
 # label. Validate all three regional tables before saving any new template.
 junca=CACHE/JUNCA_SOURCE
 junca_rows=parse_junca_tables([p.extract_text() for p in PdfReader(junca).pages],municipalities)
 junca_did=doc(cur,junca,'UPRA - estructura de costos de cebolla junca 2023','UPRA',URLS[JUNCA_SOURCE],2023,'cost-cebolla-de-rama')
 for review in junca_rows.reviews:
  cur.execute('INSERT INTO official_source_review(document_id,source_locator,parser_version,record,reason) VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',(junca_did,review['source_locator'],review['parser_version'],Jsonb(review['record']),review['reason']))
 for row in junca_rows.rows:
  cur.execute('INSERT INTO cost_template VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO NOTHING',(row['id'],row['crop'],row['title'],row['region'],Jsonb(row['municipalities']),row['reference_year'],row['production_system'],row['yield_kg_ha'],Jsonb(row['costs']),junca_did,row['source_page'],row['notes']))
  report.append({'id':row['id'],'source':JUNCA_SOURCE,'page':row['source_page'],'region':row['region'],'total':sum(c['amount'] for c in row['costs']),'yield_kg_ha':row['yield_kg_ha'],'municipalities':row['municipalities']})
 # Archive additional studies, even where multi-year tables are not flattened into one-year budgets.
 for p in CACHE.glob('cost-*.pdf'):
  if p.name not in files:doc(cur,p,'UPRA - '+p.name.removeprefix('cost-').replace('_',' '),'UPRA',URLS.get(p.name,'https://upra.gov.co/es-co/eva'),'Consultar período en el documento','reference-'+slug(p.stem))
 (HERE/'cost-extractions.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print('Cost templates',len(report),flush=True)

def input_prices(cur):
 from pipelines.ingestion.worker import archive,save_rows
 from pipelines.ingestion.inputs import parse_inputs,project_inputs
 path=CACHE/'inputs-history.xlsx';data=path.read_bytes()
 did=archive(cur.connection,URLS[path.name],data,'inputs')
 save_rows(cur.connection,did,parse_inputs(data))
 print('Input conflicts',project_inputs(cur.connection,did),flush=True)


def download(url,name):
 p=CACHE/name
 if not p.exists():subprocess.run(['curl','-fsSL','--retry','2','--max-time','120',url,'-o',str(p)],capture_output=True,check=True)
 URLS[name]=url;return p

def publications(cur):
 fep='https://federaciondecafeteros.org/wp-content/uploads/2026/04/Reporte_mensual_FEPCafe.pdf'
 p=download(fep,'fep-coffee-costs.pdf')
 if '1,550,805' not in PdfReader(p).pages[5].extract_text():raise ValueError('FEPCafe publication changed: re-verify period and cost')
 doc(cur,p,'FEPCafé - costo medio de producción, febrero 2026','Secretaría Técnica FEPCafé / FNC',fep,'Febrero 2026; reporte publicado en marzo','coffee-cost-benchmark',metadata={'cost_per_125kg':1550805,'page':6,'note':'Costo medio nacional por carga de 125 kg de café pergamino seco. Referencia agregada, no costo observado en una finca. La metodología se explica en la página 10.'})
 pdfs=[('ppm-dec2025.pdf','UPRA - precios en primer mercado, primera quincena de diciembre','UPRA','Diciembre 2025, primera quincena','first-market'),('inputs-jun2026.pdf','UPRA - índice de precios de insumos agrícolas','UPRA','Junio 2026','input-index'),('ideam-may2026.pdf','IDEAM - boletín agroclimático nacional','IDEAM','Mayo 2026: boletín histórico, no pronóstico actual','ideam-bulletin')]
 ids={}
 for name,title,publisher,period,alias in pdfs:
  p=CACHE/name
  if not p.exists():continue
  ids[alias]=doc(cur,p,title,publisher,URLS[name],period,alias)
 potato='https://editorial.agrosavia.co/index.php/publicaciones/catalog/download/163/140/1111-1?inline=1'
 doc(cur,download(potato,'potato-alhaja.pdf'),'AGROSAVIA - papa criolla Alhaja, manual técnico','AGROSAVIA',potato,'Ficha varietal; adaptación al Nudo de los Pastos (Nariño)','potato-alhaja')
 coffeePage='https://publicaciones.cenicafe.org/index.php/avances_tecnicos/article/view/1964'
 html=download(coffeePage,'coffee-development.html');soup=BeautifulSoup(html.read_text(errors='replace'),'html.parser')
 pdfview=next(urljoin(coffeePage,a['href']) for a in soup.select('a[href]') if '/1964/' in a['href'] and 'PDF' in a.get_text().upper())
 pdfurl=pdfview.replace('/article/view/','/article/download/')
 doc(cur,download(pdfurl,'coffee-development.pdf'),'Cenicafé - crecimiento del fruto y relación con la broca, Avance 194','Cenicafé',pdfurl,'1993; referencia fisiológica por altitud','coffee-development',metadata={'license':'CC BY-NC-ND 4.0 indicada por la publicación; documento original íntegro, demo sin comercialización.'})
 ica='https://www.ica.gov.co/noticias/el-ica-fortalece-la-vigilancia-fitosanitaria-del-c'
 p=download(ica,'ica-coffee-santander.html');body=BeautifulSoup(p.read_text(errors='replace'),'html.parser');main=body.find('main') or body
 textpath=CACHE/'ica-coffee-santander.txt';textpath.write_text(main.get_text('\n',strip=True))
 did=doc(cur,textpath,'ICA - vigilancia fitosanitaria del café en Santander','ICA',ica,'3 de septiembre de 2026; actividades con corte a julio de 2026','ica-coffee-santander',kind='extract',metadata={'note':'Texto de la publicación oficial conservado. No implica que haya un brote en tu finca.'})
 advisories=[('ica-coffee-santander','Revisa señales de broca en el café','El ICA reportó acciones de vigilancia y seis brotes de broca en lugares visitados de Santander, con corte a julio de 2026.','Observa los frutos y consulta con el servicio de extensión o el ICA si encuentras señales. El reporte no ubica un brote en tu predio.',['Café'],['Santander'],'2026-09-03','2026-12-03','monitoring',did,None,ica)]
 if 'input-index' in ids:advisories.append(('inputs-jun2026','Vuelve a cotizar tus insumos antes de comprar','El índice nacional de insumos agrícolas subió 2,36 % en junio de 2026, según UPRA. Es un índice agregado, no una cotización de tu proveedor.','Compara la misma presentación y actualiza el presupuesto con una cotización local.',[],[],'2026-08-12',None,'reference',ids['input-index'],2,URLS['inputs-jun2026.pdf']))
 cur.executemany('INSERT INTO advisory VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET document_id=excluded.document_id,summary=excluded.summary,action=excluded.action',[(a,b,c,d,Jsonb(e),Jsonb(f),g,h,i,j,k,l) for a,b,c,d,e,f,g,h,i,j,k,l in advisories])
 (CACHE/'download-urls.json').write_text(json.dumps(URLS,indent=2))

def main():
 config=json.loads((ROOT/'.azure-local/database.json').read_text())
 with psycopg.connect(host=config['host'],dbname=config['database'],user=config['user'],password=config['password'],sslmode='verify-full',sslrootcert=certifi.where(),connect_timeout=15) as conn:
  cur=conn.cursor()
  if '--publications-only' not in sys.argv:costs(cur);conn.commit();input_prices(cur);conn.commit()
  publications(cur);conn.commit();conn.execute('ANALYZE')
if __name__=='__main__':main()
