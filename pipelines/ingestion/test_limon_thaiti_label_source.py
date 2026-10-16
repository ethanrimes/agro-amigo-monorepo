"""Exact DANE source typo changes labels only, never IDs or source prices."""
import hashlib
import os
from datetime import date
from pathlib import Path
import unittest

import psycopg

from . import city_reports, label_normalization as labels

HERE=Path(__file__).resolve().parent
PDF=HERE/'testdata/city_cali_santa_helena_2021_11_16_label_original.pdf'
DID='35037d8b903aee4af4f0cb38538a9117a3f64e0585ae50e88e34dc33eff548e3'
LOC='PDF page 1,table 1,row 12,round 1'

class LimonThaitiSourceLabel(unittest.TestCase):
    def test_exact_original_and_native_tuple(self):
        body=PDF.read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(),DID)
        rows=list(city_reports.parse_city_pdf(body,date(2021,11,16)))
        self.assertEqual(len(rows),58)
        selected=[r for r in rows if r[0]==LOC]
        self.assertEqual(len(selected),1)
        row=selected[0]
        self.assertEqual((row[2],row[3],row[4],row[6],str(row[7]),row[8],
                          row[9],str(row[11]),str(row[12])),
                         ('limon-thaiti','Limón thaití','Cali, Santa Helena',
                          'Kilogramo','1','kg',1,'1800','1900'))

    def test_exact_alias_only_crosses_slug_guard(self):
        self.assertEqual(labels.product_label('Limón thaití'),'Limón Tahití')
        self.assertEqual(labels.product_label('LIMÓN THAITÍ'),'Limón Tahití')
        self.assertEqual(labels.normalize('Limón thaití'),'Limón Tahití')
        for unrelated in ('limon thaiti', 'Limón thaítí', 'Limón taihtí', 'Pepinocohombro',
                          'Limón Tahití (contiunuación)'):
            self.assertEqual(labels.product_label(unrelated),unrelated)
        self.assertEqual(labels.change('Limón thaití','product')['method'],
                         'exact-reviewed-label')

    @unittest.skipUnless(os.environ.get('AGRO_REFERENCE_TEST_DSN'),
                         'Disposable local PostgreSQL opt-in required')
    def test_metadata_drain_retains_both_ids_and_source_row_xmins(self):
        with psycopg.connect(os.environ['AGRO_REFERENCE_TEST_DSN'],autocommit=True) as db:
            self.assertTrue(db.info.host.startswith('/tmp/agro-'))
            self.assertIsNone(db.execute('SELECT inet_server_addr()').fetchone()[0])
            db.execute('SET search_path=pg_temp,public')
            db.execute('CREATE TEMP TABLE product(id text PRIMARY KEY,name text NOT NULL,category text NOT NULL)')
            db.execute('CREATE TEMP TABLE published_label_correction (LIKE public.published_label_correction INCLUDING ALL)')
            db.execute('CREATE TEMP TABLE published_label_scan (LIKE public.published_label_scan INCLUDING ALL)')
            db.execute('CREATE TEMP TABLE regional_price(document_id text,source_locator text,product_id text,product_name text,price numeric,PRIMARY KEY(document_id,source_locator))')
            db.execute('CREATE TEMP TABLE price_observation(product_id text,source_locator text,price numeric,PRIMARY KEY(product_id,source_locator))')
            db.execute("INSERT INTO product VALUES('limon-thaiti','Limón thaití','Frutas'),('limon-tahiti','Limón Tahití','Frutas')")
            db.execute('INSERT INTO regional_price VALUES(%s,%s,%s,%s,%s)',
                       (DID,LOC,'limon-thaiti','Limón thaití',1800))
            db.execute("INSERT INTO price_observation VALUES('limon-thaiti','old-city',1800),('limon-tahiti','canonical-monthly',2471)")
            old_source=db.execute('SELECT document_id,source_locator,product_id,product_name,price,xmin::text FROM regional_price').fetchall()
            old_prices=db.execute('SELECT product_id,source_locator,price,xmin::text FROM price_observation ORDER BY product_id').fetchall()
            self.assertEqual(labels.drain(db)['changed'],1)
            self.assertEqual(db.execute('SELECT id,name FROM product ORDER BY id').fetchall(),
                             [('limon-tahiti','Limón Tahití'),('limon-thaiti','Limón Tahití')])
            audit=db.execute('''SELECT entity_id,field,original_value,normalized_value,evidence->>'method'
                FROM published_label_correction''').fetchall()
            self.assertEqual(audit,[('limon-thaiti','name','Limón thaití','Limón Tahití','exact-reviewed-label')])
            self.assertEqual(db.execute('SELECT document_id,source_locator,product_id,product_name,price,xmin::text FROM regional_price').fetchall(),old_source)
            self.assertEqual(db.execute('SELECT product_id,source_locator,price,xmin::text FROM price_observation ORDER BY product_id').fetchall(),old_prices)
            self.assertEqual(labels.drain(db)['changed'],0)
            self.assertEqual(db.execute('SELECT count(*) FROM published_label_correction').fetchone()[0],1)
