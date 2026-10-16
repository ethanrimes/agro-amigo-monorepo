"""Original-backed regression for the 19-Aug-2025 Corabastos table."""
import hashlib
import unittest
from collections import Counter
from pathlib import Path

from pipelines.ingestion.colombia_sources import _pdf_date_text, parse_corabastos


ROOT = Path(__file__).with_name('testdata')
SOURCE = ROOT / 'BOLETIN-DE-PRECIOS-19082025-original.pdf'
URL = 'https://corabastos.com.co/wp-content/uploads/2025/08/BOLETIN-DE-PRECIOS-19082025.pdf'
SHA = '125c5e82ad45ab44a8912d1319ba7b8e57510de99946d05f343c62e2c584932a'


class CorabastosAugust2025NativeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = SOURCE.read_bytes()
        assert hashlib.sha256(cls.body).hexdigest() == SHA
        cls.rows = parse_corabastos(cls.body, URL)

    def test_source_bound_explicit_date_and_filename_guard(self):
        # Generic date parsing stays restrictive: another similarly styled
        # PDF must not fall through to the legacy partial-table reader.
        with self.assertRaisesRegex(ValueError, 'explicit observation date'):
            _pdf_date_text('19 Agosto del 2025')
        with self.assertRaisesRegex(ValueError, 'explicit observation date'):
            _pdf_date_text('BOLETIN-DE-PRECIOS-19082025.pdf')
        with self.assertRaisesRegex(ValueError, 'printed date differs'):
            parse_corabastos(self.body, URL.replace('19082025', '20082025'))

    def test_complete_native_table_without_false_product_a(self):
        rows = self.rows
        self.assertEqual(len(rows), 350)
        self.assertEqual(Counter(r['details']['source_page'] for r in rows),
                         {1: 68, 2: 88, 3: 82, 4: 82, 5: 30})
        self.assertEqual(sum(r['price'] is not None for r in rows), 349)
        identities = [(r['product_id'], r['series'], r['unit'], r['date']) for r in rows]
        self.assertEqual(len(set(identities)), len(identities))
        self.assertFalse(any(r['product_name'] in {'A', 'Aa', 'B', 'Extra', 'Producto sin identificar'}
                             for r in rows))
        self.assertIn('Huevo Blanco AA', {r['product_name'] for r in rows})
        self.assertEqual([r['date'] for r in rows], ['2025-08-19'] * 350)

    def test_original_prices_names_units_and_page_locators(self):
        def row(name, quality):
            return next(r for r in self.rows if r['product_name'] == name and
                        r['details']['quality'] == quality)
        printed = [
            ('Acelga', 'extra', 25000, 'ATADO · cantidad 10,00 · KILO', 1, 2500),
            ('Acelga', 'primera', 15000, 'ATADO · cantidad 10,00 · KILO', 1, 2500),
            ('Banano Criollo', 'extra', 80000, 'CAJA DE MADERA · cantidad 30,00 · KILO', 1, 2667),
            ('Banano Criollo', 'primera', 76000, 'CAJA DE MADERA · cantidad 30,00 · KILO', 1, 2667),
            ('Arracacha', 'extra', 75000, 'BULTO · cantidad 50,00 · KILO', 3, 5700),
            ('Huevo Blanco A', 'extra', 12000, 'CUBETA · cantidad 30,00 · Unidad', 5, 400),
            ('Huevo Rojo Extra', 'primera', 15000, 'CUBETA · cantidad 30,00 · Unidad', 5, 500),
        ]
        for name, quality, price, unit, page, per_unit in printed:
            with self.subTest(name=name, quality=quality):
                actual = row(name, quality)
                self.assertEqual(actual['price'], price)
                self.assertEqual(actual['unit'], unit)
                self.assertEqual(actual['details']['unit_price_as_published'], per_unit)
                self.assertEqual(actual['details']['source_page'], page)
                self.assertIn(f'PDF page {page}', actual['source_locator'])
                self.assertIn(f'price column {1 if quality == "extra" else 2}', actual['source_locator'])

    def test_corrupt_printed_cell_is_review_not_inferred_price(self):
        extra = next(r for r in self.rows if r['product_name'] == 'Arroz Corriente'
                     and r['details']['quality'] == 'extra')
        first = next(r for r in self.rows if r['product_name'] == 'Arroz Corriente'
                     and r['details']['quality'] == 'primera')
        self.assertEqual(extra['price'], 158000)
        self.assertIsNone(first['price'])
        self.assertEqual(first['details']['original_price'], '158/000')
        self.assertIn('requires review', first['details']['quality_issue'])
        self.assertEqual(first['details']['unit_price_as_published'], 3160)

    def test_neighbouring_original_layouts_stay_on_existing_paths(self):
        march = (ROOT / '961bf016177e-Boletin_diario_20260309-sn.pdf').read_bytes()
        march_rows = parse_corabastos(
            march, 'https://corabastos.com.co/wp-content/uploads/2026/03/Boletin_diario_20260309.pdf')
        self.assertEqual(len(march_rows), 346)
        self.assertEqual(sum(r['price'] is not None for r in march_rows), 232)
        blank = (ROOT / '14fcf6c96f01-Boletin-18febrero2025-1.pdf').read_bytes()
        blank_rows = parse_corabastos(
            blank, 'https://corabastos.com.co/wp-content/uploads/2025/02/Boletin-18febrero2025-1.pdf')
        self.assertEqual(len(blank_rows), 1)
        self.assertIsNone(blank_rows[0]['price'])
        self.assertIn('no observation date or price table', blank_rows[0]['details']['quality_issue'])

    def test_sha_bound_reader_rejects_changed_bytes(self):
        changed = self.body + b'\n'
        with self.assertRaisesRegex(ValueError, 'Revised Corabastos'):
            parse_corabastos(changed, URL)
        # A changed-byte copy under a different URL cannot fall through to the
        # generic legacy reader and publish only eight mislabeled egg rows.
        with self.assertRaisesRegex(ValueError, 'split-price layout'):
            parse_corabastos(changed, URL.replace('BOLETIN-DE-PRECIOS-19082025',
                                                 'Boletin_diario_20250819'))


if __name__ == '__main__':
    unittest.main()
