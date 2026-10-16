"""Copy with the three exact public PDFs to testdata after runtime integration."""

import datetime
import hashlib
from pathlib import Path
import unittest

from pipelines.ingestion import pdf_sources
from pipelines.ingestion.input_pdf_v17_replay import (
    VERSION, _normalized_old, _as_vector, assert_native_zero_input_context,
    assert_retained_v14_binding_locked, retained_v14_input_pdf,
    source_input_processor_version,
)
from pipelines.ingestion.inputs import input_pdf_version_for_document
from pipelines.ingestion.reviewed_wuxal_apr2015 import URL as WUXAL_URL, VERSION as WUXAL_VERSION
from pipelines.ingestion.reviewed_quindio_sep2014 import URL as SEP_URL, VERSION as SEP_VERSION
from pipelines.ingestion.test_pdf_layouts import source_pdf
from pipelines.ingestion.worker import SourceDateMismatch, asset_parser_version

SOURCES = Path(__file__).with_name('testdata') / 'input_pdf_v17_originals'
CASES = (
    ('feb2014.pdf', '3e1265bdbff25420d9be9b44c4db0aa7564585270cdc93878810c68ebae46dc3', datetime.date(2014, 2, 28), 4794, 4799),
    ('mar2014.pdf', '2befda0f1d3d4740b7a82e3a9d5ca3e6c9d2e213193ccf011ddadf9d8d729403', datetime.date(2014, 3, 31), 5706, 5709),
    ('may2014.pdf', 'db08213afe320e1a1101d2c8311565c924f4a2c82aef56d98a3971e26a1c9d62', datetime.date(2014, 5, 31), 5977, 5983),
)


def one_page(location='Armenia (Quindio)'):
    return source_pdf([
        (35, 740, 'Cuadro 1. Precios de fertilizantes', True),
        (35, 728, '2014 (febrero)', False),
        (35, 705, 'Productos y mercados', False),
        (200, 705, 'Precio medio', False),
        (35, 680, 'Wuxal tapa negra 16-16-12, 1 litro', True),
        (35, 660, location, False),
        (210, 660, '30.117', False),
    ])


class InputPDFV17Integration(unittest.TestCase):
    def test_three_exact_originals_keep_every_old_source_cell_and_add_only_14(self):
        added_total = 0
        for name, digest, day, old_count, new_count in CASES:
            with self.subTest(name=name):
                body = (SOURCES / name).read_bytes()
                self.assertEqual(hashlib.sha256(body).hexdigest(), digest)
                old = list(pdf_sources.parse_input_pdf(body, day, parser_version='inputs-pdf-v14'))
                new = list(pdf_sources.parse_input_pdf(body, day, parser_version=VERSION))
                self.assertEqual((len(old), len(new)), (old_count, new_count))
                old_cells = {_normalized_old(row)[0]: _normalized_old(row) for row in old}
                new_cells = {row[0]: _as_vector(row) for row in new}
                self.assertEqual(len(old_cells), old_count)
                self.assertEqual(len(new_cells), new_count)
                self.assertEqual({loc: new_cells[loc] for loc in old_cells}, old_cells)
                added_total += len(new_cells.keys() - old_cells.keys())
        self.assertEqual(added_total, 14)

    def test_ordinary_v17_and_exact_older_routes(self):
        self.assertEqual(asset_parser_version('inputs-pdf', 'fixture://new-input-pdf'), VERSION)
        self.assertEqual(input_pdf_version_for_document('f' * 64, 'fixture://new-input-pdf'), VERSION)
        self.assertEqual(source_input_processor_version(WUXAL_URL), WUXAL_VERSION)
        self.assertEqual(source_input_processor_version(SEP_URL), SEP_VERSION)
        self.assertEqual(asset_parser_version('inputs-pdf', WUXAL_URL), WUXAL_VERSION)
        self.assertEqual(asset_parser_version('inputs-pdf', SEP_URL), SEP_VERSION)

    def test_literal_location_survives_fold_without_guessing_unknown_or_date(self):
        day = datetime.date(2014, 2, 28)
        (row,) = pdf_sources.parse_input_pdf(one_page(), day, parser_version=VERSION)
        self.assertEqual(row[1:8], ('dane-inputs-pdf', day, 'Wuxal tapa negra 16-16-12', 'Armenia', '1 litro', 30117.0, None))
        self.assertEqual(row[-1]['department'], 'Quindío')
        self.assertEqual(row[-1]['printed_location_lines'], ['Armenia (Quindio)'])
        with self.assertRaisesRegex(ValueError, 'no verified rows'):
            list(pdf_sources.parse_input_pdf(one_page('Armenia (Quindio 2)'), day, parser_version=VERSION))
        with self.assertRaises(SourceDateMismatch):
            list(pdf_sources.parse_input_pdf(one_page(), datetime.date(2014, 3, 31), parser_version=VERSION))

    def test_actual_august_2026_context_remains_zero_without_publishing_ranges(self):
        digest = '681e997f3eca22a9540934979a782710518740bfbc80344750bc7582c5a284a3'
        body = (SOURCES / 'aug2026-context.pdf').read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(), digest)
        self.assertEqual(list(pdf_sources.parse_input_pdf(body, datetime.date(2026, 8, 31), parser_version=VERSION)), [])
        assert_native_zero_input_context(body, digest)
        monetary_header_without_verified_row = source_pdf([
            (35, 740, 'Cuadro 1. Precios de fertilizantes', True),
            (35, 705, 'Productos y mercados', False),
            (200, 705, 'Precio medio', False),
        ])
        with self.assertRaises(ValueError):
            assert_native_zero_input_context(monetary_header_without_verified_row,
                                             hashlib.sha256(monetary_header_without_verified_row).hexdigest())

    def test_missing_date_and_changed_pointer_fail_as_value_errors(self):
        url = 'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/insumos_factores_de_produccion_feb_2014.pdf'
        did = CASES[0][1]
        body = (SOURCES / 'feb2014.pdf').read_bytes()

        class FirstRow:
            def __init__(self, row):
                self.row = row

            def fetchone(self):
                return self.row

        class AssetOnly:
            def execute(self, query, params):
                return FirstRow(('inputs-pdf', datetime.date(2014, 2, 28), did,
                                 'complete', 'inputs-pdf-v14', 4794))

        with self.assertRaisesRegex(ValueError, 'source date missing'):
            retained_v14_input_pdf(AssetOnly(), url, 'inputs-pdf', None, VERSION)
        with self.assertRaisesRegex(ValueError, 'asset pointer/status/version changed'):
            assert_retained_v14_binding_locked(AssetOnly(), url, 'inputs-pdf',
                                                datetime.date(2014, 2, 28), did, 4794)

        class CheckpointValue:
            def __init__(self, value):
                self.value = value

            def execute(self, query, params):
                if 'FROM ingestion_asset' in query:
                    return FirstRow(('inputs-pdf', datetime.date(2014, 2, 28), did,
                                     'pending', 'inputs-pdf-v14', 4794))
                if 'FROM source_document' in query:
                    return FirstRow(('original', url, 'application/pdf', 56, body,
                                     {'ingestion_kind': 'context-pdf'}))
                if 'FROM historical_price' in query:
                    return FirstRow((4794, 4794, 0))
                return FirstRow((self.value,) if self.value is not None else None)

        for invalid in (None, 4793, 4795):
            with self.subTest(invalid_checkpoint=invalid):
                with self.assertRaisesRegex(ValueError, 'old publication checkpoint/typed cohort changed'):
                    assert_retained_v14_binding_locked(CheckpointValue(invalid), url, 'inputs-pdf',
                                                        datetime.date(2014, 2, 28), did, 4794)
        assert_retained_v14_binding_locked(CheckpointValue(4794), url, 'inputs-pdf',
                                            datetime.date(2014, 2, 28), did, 4794)

        class ChangedSource(CheckpointValue):
            def execute(self, query, params):
                if 'FROM source_document' in query:
                    return FirstRow(('original', url, 'application/pdf', 56, body + b'x',
                                     {'ingestion_kind': 'context-pdf'}))
                return super().execute(query, params)

        with self.assertRaisesRegex(ValueError, 'original metadata changed'):
            assert_retained_v14_binding_locked(ChangedSource(4794), url, 'inputs-pdf',
                                                datetime.date(2014, 2, 28), did, 4794)

        zero_url = 'https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSAinsumos-ago2026.pdf'
        zero_did = '681e997f3eca22a9540934979a782710518740bfbc80344750bc7582c5a284a3'
        zero_body = (SOURCES / 'aug2026-context.pdf').read_bytes()

        class ZeroContext:
            def execute(self, query, params):
                if 'FROM ingestion_asset' in query:
                    return FirstRow(('inputs-pdf', datetime.date(2026, 8, 31), zero_did,
                                     'pending', 'inputs-pdf-v14', 0))
                if 'FROM source_document' in query:
                    return FirstRow(('original', zero_url, 'application/pdf', 84, zero_body,
                                     {'ingestion_kind': 'inputs-pdf'}))
                if 'FROM historical_price' in query:
                    return FirstRow((0, 0, 0))
                return FirstRow(None)

        assert_retained_v14_binding_locked(ZeroContext(), zero_url, 'inputs-pdf',
                                            datetime.date(2026, 8, 31), zero_did, 0)


if __name__ == '__main__':
    unittest.main()
