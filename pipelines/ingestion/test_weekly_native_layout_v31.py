"""Source-bound offline and isolated PostgreSQL checks for weekly native layout prototype."""
import hashlib, os, unittest
from pathlib import Path
from unittest.mock import patch
import psycopg
from psycopg.types.json import Jsonb
from . import dane_weekly as NATIVE, official_sources, worker

HERE = Path(__file__).resolve().parent / "testdata"
BY_PREFIX = {
    "ec95": {"document_id": "ec95dc1b92689e54b52000a621dc87bad18d54392522bce748a56ce6003688e0", "source_url": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/bol_01abr_al_05abr_2023.pdf", "file": "dane_weekly_2023_04_01_native_layout.pdf"},
    "2ab3": {"document_id": "2ab314d876e586aafd8017a50d26762a1a96cbb489a57cc45a51007d63158304", "source_url": "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/bol_09jul_al_15jul_2022.pdf", "file": "dane_weekly_2022_07_09_native_layout.pdf"},
}

def parse(prefix):
    d = BY_PREFIX[prefix]
    body = (HERE / d["file"]).read_bytes()
    assert hashlib.sha256(body).hexdigest() == d["document_id"]
    return NATIVE.parse_pdf(body, d["source_url"])

def one(rows,product,market):
    matches=[r for r in rows if r['product_name']==product and r['market']==market]
    if len(matches)!=1: raise AssertionError((product,market,len(matches)))
    return matches[0]

class NativeOriginals(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fish=parse('ec95'); cls.produce=parse('2ab3')

    def test_full_original_counts_and_printed_controls(self):
        self.assertEqual((len(self.fish),sum(r['price'] is not None for r in self.fish)),(4204,3629))
        self.assertEqual((len(self.produce),sum(r['price'] is not None for r in self.produce)),(4828,4225))
        self.assertEqual(sum(r['details'].get('literal_missing_columns')==['Mínimo','Máximo','Medio'] for r in self.produce),182)
        controls=[
            (self.fish,'Calamar anillos','Bogotá, D.C., Corabastos',34000,35000,34750,'PDF page 55,table 1,column 1,line 2','2023-04-05'),
            (self.fish,'Calamar blanco entero','Bogotá, D.C., Corabastos',15000,16200,15575,'PDF page 55,table 1,column 1,line 8','2023-04-05'),
            (self.fish,'Merluza, filete nacional','Cali, Galería Alameda',50000,55000,52333,'PDF page 55,table 1,column 2,line 3','2023-04-05'),
            (self.fish,'Mojarra lora entera congelada','Barranquilla, Barranquillita',12000,12200,12067,'PDF page 55,table 1,column 2,line 6','2023-04-05'),
            (self.fish,'Langostino U12','Cali, Galería Alameda',75000,80000,76667,'PDF page 55,table 1,column 1,line 37','2023-04-05'),
            (self.fish,'Tilapia roja entera fresca','Bogotá, D.C., Paloquemao',11500,12000,11833,'PDF page 56,table 1,column 2,line 8','2023-04-05'),
            (self.produce,'Acelga','Armenia, Mercar',2000,2133,2067,'PDF page 9,table 1,column 1,line 2','2022-07-15'),
            (self.produce,'Acelga','Bogotá, D.C., Corabastos',667,1667,1184,'PDF page 9,table 1,column 1,line 4','2022-07-15'),
            (self.produce,'Ahuyama','Bogotá, D.C., Corabastos',2000,2300,2124,'PDF page 9,table 1,column 1,line 24','2022-07-15'),
            (self.produce,'Ajo','Bogotá, D.C., Corabastos',12000,14000,13481,'PDF page 9,table 1,column 2,line 28','2022-07-15'),
        ]
        for rows,product,market,low,high,mean,locator,date in controls:
            with self.subTest(product=product,market=market):
                r=one(rows,product,market)
                self.assertEqual((r['min'],r['max'],r['price'],r['source_locator'],r['date'],r['unit']),(low,high,mean,locator,date,'kg'))
        for product,market,locator in [('Ahuyamín (Sakata)','Chiquinquirá (Boyacá)','PDF page 9,table 1,column 2,line 10'),('Ahuyama','Barranquilla, Barranquillita','PDF page 9,table 1,column 1,line 22')]:
            r=one(self.produce,product,market)
            self.assertEqual((r['min'],r['max'],r['price'],r['details']['literal_mean'],r['source_locator']),(None,None,None,0,locator))
            self.assertEqual(r['details']['literal_missing_columns'],['Mínimo','Máximo'])
        for product,market,trend,locator in [
            ('Banano Urabá','Barranquilla, Granabastos','n.d.','PDF page 22,table 1,column 1,line 9'),
            ('Fresa','Sincelejo, Nuevo Mercado','-','PDF page 23,table 1,column 1,line 38'),
            ('Papaya Maradol','Cali, Santa Elena','+','PDF page 30,table 1,column 1,line 41'),
        ]:
            r=one(self.produce,product,market)
            self.assertEqual((r['min'],r['max'],r['price'],r['details']['trend'],r['source_locator'],r['date'],r['unit']),(None,None,None,trend,locator,'2022-07-15','kg'))
            self.assertEqual(r['details']['literal_missing_columns'],['Mínimo','Máximo','Medio'])

    def test_negative_native_shapes_fail_closed(self):
        headers=[{'x0':100,'x1':120},{'x0':130,'x1':150},{'x0':160,'x1':180}]
        def w(text,x): return {'text':text,'x0':x,'x1':x+8,'top':10,'bottom':15,'fontname':'Book'}
        def row(tokens): return [w('Mercado',0)]+[w(t,x) for t,x in tokens]
        for tokens in [ [('0',160)], [('.',100),('.',130),('0',160)], [('.',100),('.',130),('0',160),('n.d.',170)], [('.',100),('.',130),('1',160),('n.d.',200)] ]:
            with self.subTest(tokens=tokens),self.assertRaisesRegex(ValueError,'unbound/incomplete'):
                NATIVE._native_column([[w('Producto',0)],[*row(tokens)]],headers,'verduras',(NATIVE.date(2022,7,9),NATIVE.date(2022,7,15)),9,1,1,{},legacy_wrapping=False)
        joined=w('52.333n.d.',160)
        self.assertEqual(NATIVE._split_joined_price_words([joined],[headers]),[joined])  # no source glyphs => no guessed split
        def native_line(tokens):
            heading={**w('Producto',0),'fontname':'Bold','top':0,'bottom':5}
            market=[{**w('Mercado',0),'top':10,'bottom':15}]+[{**w(t,x),'top':10,'bottom':15} for t,x in tokens]
            return NATIVE._native_column([[heading],market],headers,'verduras',(NATIVE.date(2022,7,9),NATIVE.date(2022,7,15)),9,1,1,{})
        valid=native_line([('-',100),('-',130),('-',160),('n.d.',200)])
        self.assertEqual((len(valid),valid[0]['price'],valid[0]['details']['literal_missing_columns']),(1,None,['Mínimo','Máximo','Medio']))
        for tokens in [
            [('-',100),('-',130),('-',130),('n.d.',200)],  # third dash in wrong cell
            [('-',100),('-',130),('-',160),('unknown',200)],  # unsupported trend
            [('-',100),('-',130),('-',160),('n.d.',170)],  # trend overlaps mean
            [('-',100),('-',130),('-',160),('n.d.',200),('9',210)], # extra monetary token
        ]:
            with self.subTest(tokens=tokens),self.assertRaises(ValueError):native_line(tokens)

class PublicationTemporaryPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dsn=os.environ.get('AGRO_REFERENCE_TEST_DSN')
        if not dsn: raise RuntimeError('Explicit private PG DSN required')
        cls.db=psycopg.connect(dsn,autocommit=True)
        if not str(cls.db.info.host).startswith('/tmp/agro-'):
            cls.db.close();raise RuntimeError('Private socket only')
        cls.db.execute("SET search_path=pg_temp; SET statement_timeout='30s'")
        for name in ('source_document','ingestion_asset','official_price_quote','official_source_review','ingestion_checkpoint'):
            cls.db.execute(f'CREATE TEMP TABLE {name} (LIKE public.{name} INCLUDING ALL)')
        cls.fish=parse('ec95');cls.produce=parse('2ab3')
    @classmethod
    def tearDownClass(cls): cls.db.close()
    def test_append_only_quote_and_zero_review_idempotent(self):
        db=self.db;db.execute('BEGIN')
        try:
            for prefix in ('ec95','2ab3'):
                d=BY_PREFIX[prefix];body=(HERE / d["file"]).read_bytes()
                db.execute("INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content,metadata) VALUES(%s,'DANE weekly','DANE',%s,'application/pdf','original',%s,%s,%s)",(d['document_id'],d['source_url'],'2023-04-05' if prefix=='ec95' else '2022-07-15',body,Jsonb({'ingestion_kind':'dane-weekly-pdf'})))
                db.execute("INSERT INTO ingestion_asset(url,kind,status,processor_version,document_id,observed_on,checked_at) VALUES(%s,'dane-weekly-pdf','complete','official-v2:dane-weekly-v23',%s,%s,now())",(d['source_url'],d['document_id'],'2023-04-05' if prefix=='ec95' else '2022-07-15'))
            quoted=one(self.fish,'Merluza, filete nacional','Cali, Galería Alameda')
            reviewed=one(self.produce,'Ahuyamín (Sakata)','Chiquinquirá (Boyacá)')
            dashed=one(self.produce,'Papaya Maradol','Cali, Santa Elena')
            with patch('pipelines.ingestion.official_catalog.mark_document_dirty'),patch('pipelines.ingestion.official_catalog.refresh_document'),patch('pipelines.ingestion.write_pacing.pause_between_batches'):
                official_sources.publish_rows(db,[quoted],BY_PREFIX['ec95']['document_id'],'dane-weekly-pdf')
                official_sources.publish_rows(db,[quoted],BY_PREFIX['ec95']['document_id'],'dane-weekly-pdf')
                official_sources.publish_rows(db,[reviewed,dashed],BY_PREFIX['2ab3']['document_id'],'dane-weekly-pdf')
                official_sources.publish_rows(db,[reviewed,dashed],BY_PREFIX['2ab3']['document_id'],'dane-weekly-pdf')
            self.assertEqual(db.execute("SELECT count(*) FROM official_price_quote WHERE document_id=%s",(BY_PREFIX['ec95']['document_id'],)).fetchone()[0],1)
            self.assertEqual(db.execute("SELECT count(*) FROM official_price_quote WHERE document_id=%s",(BY_PREFIX['2ab3']['document_id'],)).fetchone()[0],0)
            self.assertEqual(db.execute("SELECT count(*) FROM official_source_review WHERE document_id=%s",(BY_PREFIX['2ab3']['document_id'],)).fetchone()[0],2)
        finally: db.execute('ROLLBACK')

    def test_corrected_market_revision_retains_old_source_quote(self):
        db=self.db;d=BY_PREFIX['2ab3'];body=(HERE / d["file"]).read_bytes()
        corrected=next(r for r in self.produce if r['source_locator']=='PDF page 21,table 1,column 1,line 3')
        self.assertEqual((corrected['product_name'],corrected['market'],corrected['min'],corrected['max'],corrected['price']),('Aguacate común','Bucaramanga, Centroabastos',5500,6000,5750))
        previous={**corrected,'market':'Barranquilla, Barranquillita Bucaramanga, Centroabastos'}
        db.execute('BEGIN')
        try:
            db.execute("INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content,metadata) VALUES(%s,'DANE weekly','DANE',%s,'application/pdf','original','2022-07-15',%s,%s)",(d['document_id'],d['source_url'],body,Jsonb({'ingestion_kind':'dane-weekly-pdf'})))
            db.execute("INSERT INTO ingestion_asset(url,kind,status,processor_version,document_id,observed_on,checked_at) VALUES(%s,'dane-weekly-pdf','complete','official-v2:dane-weekly-v23',%s,'2022-07-15',now())",(d['source_url'],d['document_id']))
            with patch.object(worker,'parser_version',return_value='official-v2:dane-weekly-v23'),patch('pipelines.ingestion.official_catalog.mark_document_dirty'),patch('pipelines.ingestion.official_catalog.refresh_document'),patch('pipelines.ingestion.write_pacing.pause_between_batches'):
                official_sources.publish_rows(db,[previous],d['document_id'],'dane-weekly-pdf')
            db.execute("UPDATE official_price_quote SET parsed_at=now()-interval '1 minute' WHERE document_id=%s",(d['document_id'],))
            with patch.object(worker,'parser_version',return_value='official-v2:dane-weekly-v24'),patch('pipelines.ingestion.official_catalog.mark_document_dirty'),patch('pipelines.ingestion.official_catalog.refresh_document'),patch('pipelines.ingestion.write_pacing.pause_between_batches'):
                official_sources.publish_rows(db,[corrected],d['document_id'],'dane-weekly-pdf')
                official_sources.publish_rows(db,[corrected],d['document_id'],'dane-weekly-pdf')
            found=db.execute("SELECT market,price,min_price,max_price,source_locator,parser_version FROM official_price_quote WHERE document_id=%s ORDER BY parsed_at",(d['document_id'],)).fetchall()
            self.assertEqual(len(found),2)
            self.assertEqual(found[0][:5],('Barranquilla, Barranquillita Bucaramanga, Centroabastos',5750,5500,6000,corrected['source_locator']))
            self.assertEqual(found[1][:5],('Bucaramanga, Centroabastos',5750,5500,6000,corrected['source_locator']))
            self.assertEqual((found[0][5],found[1][5]),('official-v2:dane-weekly-v23','official-v2:dane-weekly-v24'))
        finally:db.execute('ROLLBACK')

if __name__=='__main__':unittest.main()
