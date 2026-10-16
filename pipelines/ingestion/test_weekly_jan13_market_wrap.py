"""Exact whole-original Jan 7–13 2017 weekly market-wrap review."""

import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from . import dane_weekly as weekly, worker


URL = weekly.JANUARY_2017_JAN13_URL
DID = weekly.JANUARY_2017_JAN13_SHA
BODY = Path(__file__).parent / "testdata/weekly_market_wrap_originals" / f"{DID}.pdf"


class Jan13WholeOriginal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = BODY.read_bytes()
        assert hashlib.sha256(cls.body).hexdigest() == DID

    def test_whole_grid_and_printed_market_boundary(self):
        native_column = weekly._native_column

        def prior_column(*args, **kwargs):
            return native_column(*args, **{**kwargs, "january_2017_market_wrap": False})

        with (patch.object(weekly, "_native_column", side_effect=prior_column),
              patch.object(weekly, "JANUARY_2017_JAN13_URL", "_prior_grid_")):
            prior = weekly.parse_pdf(self.body, URL)
        current = weekly.parse_pdf(self.body, URL)
        self.assertEqual((len(prior), len(current)), (4674, 4674))
        self.assertEqual(sum(r["price"] is not None for r in current), 4523)
        self.assertEqual(len({r["source_locator"] for r in current}), 4674)
        self.assertEqual(hashlib.sha256(json.dumps(current, ensure_ascii=False,
            sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest(),
            weekly.JANUARY_2017_JAN13_ROWS_SHA)
        changed_market = changed_details = 0
        for old, new in zip(prior, current):
            self.assertEqual(old["source_locator"], new["source_locator"])
            for field in set(old) | set(new):
                if field not in ("market", "details"):
                    self.assertEqual(old.get(field), new.get(field), (new["source_locator"], field))
            changed_market += old["market"] != new["market"]
            changed_details += old["details"] != new["details"]
        self.assertEqual((changed_market, changed_details), (511, 322))
        coliflor = [r for r in current if r["product_name"] == "Coliflor"
                    and r["source_page"] == 9]
        self.assertTrue(any(r["market"] == "Manizales (Caldas)" and
            (r["min"], r["max"], r["price"]) == (2000, 2500, 2217)
            for r in coliflor))
        self.assertTrue(any(r["market"] == "Medellín, Central Mayorista de Antioquia" and
            (r["min"], r["max"], r["price"]) == (1500, 1500, 1500)
            for r in coliflor))
        self.assertFalse(any(r["market"] == "Manizales (Caldas) Medellín, Central"
                             for r in coliflor))

    def test_exact_source_body_and_version_only(self):
        kind = "dane-weekly-pdf"
        new = "official-v2:jan2017-market-wrap-v3:dane-weekly-v24"
        self.assertEqual(worker.parser_version(kind, URL), new)
        self.assertEqual(worker.asset_parser_version(kind, URL), new)
        self.assertEqual(worker.parser_version(kind, URL + "?alias"), worker.parser_version(kind))
        self.assertEqual(worker.asset_parser_version(kind, URL + "?alias"), worker.parser_version(kind))
        with self.assertRaisesRegex(ValueError, "bytes changed"):
            weekly.parse_pdf(self.body + b"x", URL)
        alias = weekly.parse_pdf(self.body, URL + "?alias")
        self.assertEqual(len(alias), 4674)
        self.assertFalse(any(r["details"].get("native_market_join") ==
            "january_2017_same_column_leading_market_line" for r in alias))


if __name__ == "__main__":
    unittest.main()
