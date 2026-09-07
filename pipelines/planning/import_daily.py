"""Keep the daily bulletin separate: its predominant varieties are not monthly product quotes."""
from import_references import *

def run(cur,iso):
 day=date.fromisoformat(iso)
 if not START<day<=TODAY:raise ValueError('Daily observation outside demo window')
 stem='daily-'+iso;path=CACHE/(stem+'.xlsx');base='https://www.dane.gov.co/files/operaciones/SIPSA/';code=f'{day.day:02d}'+['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'][day.month-1]+str(day.year)
 book=doc(cur,path,'DANE SIPSA - anexo diario '+iso,'DANE',base+'anex-SIPSADiario-'+code+'.xlsx',iso,stem+'-workbook')
 bulletin=doc(cur,CACHE/(stem+'.pdf'),'DANE SIPSA - boletín diario y abastecimiento '+iso,'DANE',base+'bol-SIPSADiario-'+code+'.pdf',iso,stem+'-bulletin')
 df=pd.read_excel(path,header=None);products=dict(cur.execute('SELECT id,name FROM product').fetchall());rows=[];values=[]
 for i,r in df.iterrows():
  name=str(r.iloc[0]).strip();pid=slug(name) if '*' not in name and slug(name) in products else None
  for col in range(1,len(df.columns),2):
   price=r.iloc[col]
   if not isinstance(price,(int,float)) or not math.isfinite(price) or price<=0:continue
   market=' '.join(str(df.iloc[2,col]).split());variation=r.iloc[col+1];variation=float(variation)*100 if isinstance(variation,(int,float)) and math.isfinite(variation) else None
   rows.append([iso,name+' · '+market,money(price),f'Boletín diario / fila {i+1}, col. {col+1}'])
   values.append((day,name,market,pid,float(price),variation,i+1,col+1))
 p=pdf_extract(stem,'Precios diarios SIPSA · '+iso,['Fecha','Producto y mercado','COP / kg','Archivo / ubicación'],rows,[book])
 # Distinguish the daily frequency prominently without modifying the official source bytes.
 # pdf_extract accepts an explicit subtitle for this daily representation.
 extract=doc(cur,p,'DANE - precios diarios, extracto '+iso,'DANE / extracto AgroAmigo',base+'anex-SIPSADiario-'+code+'.xlsx',iso,stem,kind='extract',metadata={'parents':[book,bulletin],'note':'* indica variedad predominante en cada mercado. No se mezcla con la serie mensual. La variación compara con el anterior día de mercado en la misma plaza.'})
 cur.execute('''CREATE TABLE IF NOT EXISTS daily_price(observed_on date,product_name text,market_name text,product_id text REFERENCES product(id),price numeric NOT NULL CHECK(price>0),change_percent numeric,document_id text REFERENCES source_document(id),source_page integer,source_locator text,PRIMARY KEY(observed_on,product_name,market_name)); DROP TRIGGER IF EXISTS demo_window ON daily_price; CREATE TRIGGER demo_window BEFORE INSERT OR UPDATE ON daily_price FOR EACH ROW EXECUTE FUNCTION enforce_demo_window(); GRANT SELECT ON daily_price TO agro_reader;''')
 cur.execute('DELETE FROM daily_price WHERE observed_on<=%s OR observed_on>%s',(START,TODAY))
 cur.executemany('INSERT INTO daily_price VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(observed_on,product_name,market_name) DO UPDATE SET price=excluded.price,document_id=excluded.document_id,source_page=excluded.source_page',[(d,n,m,pid,price,v,extract,k//24+1,f'Boletín diario, fila {row}, columna {col}') for k,(d,n,m,pid,price,v,row,col) in enumerate(values)])
 print('Daily prices',len(values),flush=True)
if __name__=='__main__':
 config=json.loads((ROOT/'.azure-local/database.json').read_text())
 with psycopg.connect(host=config['host'],dbname=config['database'],user=config['user'],password=config['password'],sslmode='verify-full',sslrootcert=certifi.where(),connect_timeout=15) as conn:run(conn.cursor(),sys.argv[1] if len(sys.argv)>1 else '2026-09-04')
