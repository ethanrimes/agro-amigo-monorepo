"""Department histories remain separate from municipal observations."""

import unittest
from datetime import date
from unittest.mock import MagicMock, Mock, patch

from . import worker
from .inputs import identity, parse_inputs, prepare_input_stage


class DepartmentHistory(unittest.TestCase):
    def test_staging_retains_exact_line_prices_and_legacy_aliases(self):
        db = MagicMock()
        cur = MagicMock()
        source = MagicMock()
        db.cursor.side_effect = [MagicMock(__enter__=Mock(return_value=cur)),
                                MagicMock(__enter__=Mock(return_value=source))]
        rows = []
        expected = []
        for metres, numbers, prices in [
            (200, (70, 71), (152970.5, 147122.2222222)),
            (350, (91, 92), (262487.5555556, 251116.6666667)),
            (500, (113, 115), (369795.4545455, 351075.0)),
        ]:
            for line, number, price in zip(["Finquero", "Iowa"], numbers, prices):
                meta = {"sheet": "3.2", "category": "Elementos agropecuarios",
                    "presentation": f"rollo por {metres} metros", "brand": "PROALCO BEKAERT",
                    "ica": "", "line": line, "department": "Antioquia", "municipality": ""}
                name = "Alambre de púas nro. 14"
                rows.append((f"3.2!row {number}; full product identity", "dane-inputs",
                    date(2023, 1, 31), name, "Antioquia", meta["presentation"], price, meta))
                expected.append((identity(name, {**meta, "line": ""}), identity(name, meta)))
        source.fetchmany.side_effect = [rows, []]
        prepare_input_stage(db, "reviewed-original", date(2023, 1, 31))
        copied = [call.args[0] for call in cur.copy.return_value.__enter__.return_value.write_row.call_args_list]
        self.assertEqual(len({row[0] for row in copied}), 6)
        self.assertEqual([row[6] for row in copied], [r[6] for r in rows])
        self.assertEqual([row[8] for row in copied], [r[0] for r in rows])
        self.assertEqual([row[11] for row in copied], ["Finquero", "Iowa"] * 3)
        self.assertEqual(cur.executemany.call_args.args[1], sorted(expected))

    def test_verified_wire_lines_split_without_rewriting_source_names(self):
        for metres, prices in [
            (200, (152970.5, 147122.2222222)),
            (350, (262487.5555556, 251116.6666667)),
            (500, (369795.4545455, 351075.0)),
        ]:
            meta = {"sheet": "3.2", "presentation": f"rollo por {metres} metros",
                "brand": "PROALCO BEKAERT", "ica": ""}
            base = identity("Alambre de púas nro. 14", meta)
            keys = [identity("Alambre de púas nro. 14", {**meta, "line": line})
                    for line in ["Finquero", "Iowa"]]
            self.assertEqual(keys, [base + "-linea-finquero", base + "-linea-iowa"])
            self.assertEqual(len(dict(zip(keys, prices))), 2)

    def test_unaffected_and_line_already_named_keep_existing_ids(self):
        meta = {"sheet": "3.2", "presentation": "rollo por 1 metro",
            "brand": "PLASTILENE", "ica": ""}
        name = "Agrolene calibre 6 - ancho 8"
        self.assertEqual(identity(name, meta), identity(name, {**meta, "line": "Calibre 6 - Ancho 8"}))
        for line in ["", "NA", "N/A", "No aplica"]:
            self.assertEqual(identity(name, meta), identity(name, {**meta, "line": line}))
        fertilizer = {**meta, "sheet": "1.3", "line": "Finquero"}
        self.assertEqual(identity(name, meta), identity(name, fertilizer))

    def test_discovery_types_department_history_without_filename_date(self):
        archive = worker.INPUTS + "/componente-insumos-historicos"
        base = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/"
        department = base + "anex-SIPSAInsumos-SeriesHistoricasDep-2018-2026.xlsx"
        municipal = base + "anex-SIPSAInsumos-SeriesHistoricasMun-2013-2026.xlsx"
        db = Mock()
        db.execute.return_value.fetchall.return_value = []
        with patch.object(worker, "links", side_effect=[
            [("Archivo", archive), ("Serie histórica departamental", department)],
            [("Serie histórica municipal", municipal)],
            [("Serie histórica departamental", department)],
        ]), patch.object(worker, "queue") as queue:
            worker.discover_inputs(db)
        self.assertEqual(queue.call_args_list, [
            unittest.mock.call(db, municipal, "inputs-municipal"),
            unittest.mock.call(db, department, "inputs"),
        ])

    def test_top_level_discovery_accepts_literal_lowercase_xls_link(self):
        url = "https://www.dane.gov.co/files/anex-sipsainsumos-serieshistoricasdep-2018-2026.xls?download=1"
        with patch.object(worker, "discover_input_sources"), patch.object(
            worker, "links", return_value=[("Serie histórica", url)]
        ), patch.object(worker, "queue") as queue:
            worker.discover_inputs(Mock())
        self.assertEqual(queue.call_args.args[1:], (url, "inputs"))

    def test_literal_department_header_uses_row_month_and_source_locator(self):
        # Literal values from reviewed 2018-2026 workbook, sheet 1.3 row 10.
        rows = [
            ["SIPSA-I Serie histórica de precio promedio de mercado por departamento (enero 2018 - agosto 2026)*"],
            [], [], [],
            ["1.3. Fertilizantes, enmiendas y acondicionadores de suelo"],
            [], [], [],
            ["Año ", "Mes", "Código departamento", "Nombre departamento ",
             "Código CPC 2.1 A.C.", "Nombre del producto", "Artículo", "Casa Comercial",
             "Registro ICA", "Presentación del producto", "Precio promedio departamento"],
            [2018, "Enero", "05", "Antioquia", "34641", "10-20-20", "Nutrimon 10-20-20",
             "MONOMEROS COLOMBO VENEZOLANOS S.A.", 1824, "50 kilogramos", 82682.6666667],
        ]
        with patch.object(worker, "workbooks", return_value=[("1.3", iter(rows))]):
            result = list(parse_inputs(b"reviewed header sample"))
        self.assertEqual(len(result), 1)
        row = result[0]
        self.assertEqual(row[1:7], ("dane-inputs", date(2018, 1, 31),
            "Nutrimon 10-20-20", "Antioquia", "50 kilogramos", 82682.6666667))
        self.assertEqual(row[0], "1.3!row 10")
        self.assertEqual(row[-1]["municipality"], "")
        self.assertEqual(row[-1]["department"], "Antioquia")
        self.assertEqual(row[-1]["ica"], "1824")


if __name__ == "__main__":
    unittest.main()
