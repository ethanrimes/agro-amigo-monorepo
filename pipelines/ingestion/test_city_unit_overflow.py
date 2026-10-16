"""Independent native row controls for city unit glyphs crossing price cells."""
import copy
import csv
import hashlib
import re
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pdfplumber

from . import city_reports, city_unit_overflow, worker


DATA = Path(__file__).parent / 'testdata/city_unit_overflow_202201'
ORIGINALS = (
    ('armenia-jan3', '867232775a722b2a3d2c3c40307e2d892fe7edbb9a4e634780d85ff9e11d1943', 56, date(2022, 1, 3)),
    ('armenia-jan4', 'b194d4270d98bfc32414526e46cc75db54495957bf51805b01ca8867b9ae2156', 106, date(2022, 1, 4)),
    ('cali-santa-elena-jan4', '8440cada34d16f78dd1f8ca024a4201c39a87511756a4e97b6d1ac6c8841c88c', 134, date(2022, 1, 4)),
    ('ibague-jan4', '81df4ba0c7453d4610e82644e52b12f9bb5a43f56bc1cfe94d2c7715156535dd', 120, date(2022, 1, 4)),
)
MARKETS = {
    'armenia-jan3':'Armenia, Mercar',
    'armenia-jan4':'Armenia, Mercar',
    'cali-santa-elena-jan4':'Cali, Santa Elena',
    'ibague-jan4':'Ibagué, Plaza la 21',
}
CATEGORIES = {
    'armenia-jan3':{'Frutas','Verduras y hortalizas','Tuberculos, raices y platanos'},
    'armenia-jan4':{'Frutas','Verduras y hortalizas','Tuberculos, raices y platanos',
        'Granos y cereales','Procesados','Procesados > Carne de pollo',
        'Procesados > Pescado','Procesados > Huevos'},
    'cali-santa-elena-jan4':{'Frutas','Verduras y hortalizas','Tuberculos, raices y platanos',
        'Granos y cereales','Procesados','Pescados','Lacteos y huevos','Carnes'},
    'ibague-jan4':{'Frutas','Verduras y hortalizas','Tuberculos, raices y platanos',
        'Granos y cereales','Granos y cereales > Huevos y lacteos',
        'Procesados','Pescados','Carnes'},
}


def _literal_rows(stem):
    with (DATA / f'{stem}-native.tsv').open() as stream:
        return list(csv.DictReader(stream, delimiter='\t'))


def _independent_literal(row):
    unit, low, high = row['units'], row['round1_min'], row['round1_max']
    match = re.fullmatch(r'(r|R|C|c|G\s*R|C\s*C)\s*(\d+(?:[.,]\d+)*|-)', low)
    if match:
        suffix = ''.join(match[1].split())
        low = match[2]
        if unit.endswith(('G', 'g', 'C', 'c')) and len(suffix) == 1:
            unit += suffix
        elif unit[-1:].isdigit() and len(suffix) == 2:
            unit += ' ' + suffix
        else:
            raise AssertionError(row)
    return unit, low, high


class CityNativeUnitOverflow(unittest.TestCase):
    def test_every_price_from_four_originals_matches_independent_literal_rows(self):
        self.assertEqual(city_reports.VERSION, 'city-v8')
        self.assertEqual(worker.parser_version('city-zip'), city_reports.VERSION)
        self.assertIn('pipelines/ingestion/city_unit_overflow.py', worker.RELEASE_FILES)
        for stem, digest, count, day in ORIGINALS:
            with self.subTest(stem=stem):
                body = (DATA / f'{stem}.pdf').read_bytes()
                self.assertEqual(hashlib.sha256(body).hexdigest(), digest)
                parsed = list(city_reports.parse_city_pdf(body, day))
                self.assertEqual(len(parsed), count)
                by_locator = {row[0]: row for row in parsed}
                self.assertEqual(len(by_locator), count)
                literal = _literal_rows(stem)
                expected = {}
                for row in literal:
                    unit, low, high = _independent_literal(row)
                    if low == high == '-':
                        continue
                    locator = f"PDF page {row['page']},table {row['table']},row {row['row']},round 1"
                    expected[locator] = (row, unit, low, high)
                self.assertEqual(set(by_locator), set(expected))
                for locator, (row, unit, low, high) in expected.items():
                    got = by_locator[locator]
                    quantity, source_unit = unit.split(' ', 1)
                    self.assertEqual((got[1], got[3], got[6], got[7], got[8], got[9]),
                        (day, row['product'], row['presentation'],
                         Decimal(quantity.replace(',', '.')), source_unit, 1))
                    self.assertEqual((got[11], got[12]),
                        (Decimal(low.replace('.', '')), Decimal(high.replace('.', ''))))
                    # Other typed fields are checked as source-backed heading
                    # constants or arithmetic/identity invariants. The TSV
                    # independently controls every literal product/unit/price.
                    self.assertEqual(len(got),17)
                    self.assertEqual(got[2],worker.slug(row['product']))
                    self.assertEqual(got[4],MARKETS[stem])
                    self.assertIn(got[5],CATEGORIES[stem])
                    self.assertEqual(got[10],'Ronda 1')
                    self.assertEqual(got[16],int(row['page']))
                    base={
                        'kilogramo':('kg',Decimal(1)),
                        'gramo':('kg',Decimal('.001')),
                        'litro':('litre',Decimal(1)),
                        'mililitro':('litre',Decimal('.001')),
                        'unidad':('unit',Decimal(1)),
                        'unidades':('unit',Decimal(1)),
                    }.get(worker.slug(source_unit))
                    if base:
                        unit,factor=base
                        self.assertEqual((got[13],got[14],got[15]),
                            (unit,got[11]/(got[7]*factor),got[12]/(got[7]*factor)))
                    else:
                        self.assertEqual((got[13],got[14],got[15]),(source_unit,None,None))
                self.assertTrue(all(not x['round2_min'] and not x['round2_max'] for x in literal))

    def test_unavailable_dash_dash_rows_remain_unpublished(self):
        rows = _literal_rows('ibague-jan4')
        unavailable = [r for r in rows if _independent_literal(r)[1:] == ('-', '-')]
        self.assertEqual({r['product'] for r in unavailable}, {'Manteca', 'Margarina'})
        parsed = list(city_reports.parse_city_pdf((DATA/'ibague-jan4.pdf').read_bytes(), date(2022,1,4)))
        self.assertFalse({r[3] for r in parsed} & {'Manteca', 'Margarina'})

    def test_geometry_and_literal_negative_controls(self):
        with pdfplumber.open(DATA/'armenia-jan3.pdf') as pdf:
            page=pdf.pages[0]; table=page.extract_tables()[0]; shape=page.find_tables()[0]
            row=table[28]; cells=shape.rows[28].cells
            self.assertEqual(city_unit_overflow._one_cell(page,row,cells), ('25 Unidad 454 Gr','40.000'))
            for col,text in ((3,'r 41.000'),(3,'COP 40.000'),(3,'r 40.000 + 5'),
                             (2,'25 Kilogramo'),(2,'25 Unidad 999 G'),(3,'r: 40.000')):
                changed=list(row);changed[col]=text
                self.assertIsNone(city_unit_overflow._one_cell(page,changed,cells))
            self.assertIsNone(city_unit_overflow._one_cell(page,row,shape.rows[27].cells))
            shifted=list(cells);box=list(shifted[3]);box[0]+=2;shifted[3]=tuple(box)
            self.assertIsNone(city_unit_overflow._one_cell(page,row,shifted))
            fake=SimpleNamespace(chars=[dict(c) for c in page.chars])
            spill=next(c for c in fake.chars if c['text']=='r' and 342<c['x0']<343 and 571<c['top']<573)
            spill['fontname']='DifferentFont'
            self.assertIsNone(city_unit_overflow._one_cell(fake,row,cells))

    def test_no_price_repair_keeps_every_cell_literal(self):
        with pdfplumber.open(DATA/'armenia-jan3.pdf') as pdf:
            page=pdf.pages[0]; tables=page.extract_tables(); before=copy.deepcopy(tables)
            self.assertIs(city_unit_overflow.verified_city_unit_overflow(page,tables,repair_prices=False),tables)
            self.assertEqual(tables,before)

    def test_crossed_quantity_digit_february_source_still_requires_true_archive_day(self):
        path=DATA/'villavicencio-feb2-2022-in-2021-url.pdf'
        body=path.read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(),
            '4b229f716725b65ea44256e285354923fc1fee6114641286277fbac2aebb3131')
        rows=list(city_reports.parse_city_pdf(body,date(2022,2,2)))
        self.assertEqual(len(rows),131)
        sugar=next(r for r in rows if r[3]=='Azúcar Refinada')
        self.assertEqual((sugar[0],sugar[7],sugar[8],sugar[11],sugar[12],sugar[14]),
            ('PDF page 4,table 1,row 4,round 1',Decimal(25),'Kilogramo 500 GR',
             Decimal(41500),Decimal(45700),None))
        with self.assertRaises(worker.SourceDateMismatch):
            list(city_reports.parse_city_pdf(body,date(2021,2,2)))


if __name__=='__main__':
    unittest.main()
