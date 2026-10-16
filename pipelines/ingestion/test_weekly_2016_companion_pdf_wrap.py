"""Whole paired-source proof for the exact 4 Nov 2016 weekly bulletin."""

import collections
import json
import re
import unicodedata
import unittest
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from pipelines.ingestion import dane_weekly as weekly
from pipelines.ingestion.worker import asset_parser_version, parser_version


SOURCE = Path(__file__).parent / "testdata/weekly_2016_schematic"
PDF_SHA = weekly.NOVEMBER_2016_MEDELLIN_WRAP_SHA
XLS_SHA = "abce8f1ee2cd3211e6bb20b8dd6a2849aea9266a19b76a5c293ef89b77a1e23e"
XLS_URL = (
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/"
    "Sem_29oct_04nov_2016.xls"
)


def compact(value):
    letters = unicodedata.normalize("NFKD", value.casefold())
    return re.sub(r"[^a-z0-9]+", "", letters.encode("ascii", "ignore").decode())


def source_key(row):
    mean = row["details"].get("literal_mean", row["price"])
    return (compact(row["product_name"]), compact(row["market"]),
            row["min"], row["max"], mean)


class Weekly2016CompanionPDFWrap(unittest.TestCase):
    def test_full_pdf_113_market_repairs_and_all_4709_annex_matches(self):
        body = (SOURCE / f"{PDF_SHA}.pdf").read_bytes()
        annex = (SOURCE / f"{XLS_SHA}.xls").read_bytes()
        oracle = json.loads((SOURCE / "nov04_2016_113_native_wrap_oracle.json").read_text())
        self.assertEqual(sha256(body).hexdigest(), PDF_SHA)
        self.assertEqual(sha256(annex).hexdigest(), XLS_SHA)
        self.assertEqual(oracle["source_pdf_sha256"], PDF_SHA)
        self.assertEqual(len(oracle["rows"]), 113)

        original_column = weekly._native_column

        def without_exact_repair(*args, **kwargs):
            return original_column(*args, **{
                **kwargs, "november_2016_medellin_wrap": False,
            })

        source_url = weekly.NOVEMBER_2016_MEDELLIN_WRAP_URL
        with (patch.object(weekly, "_native_column", side_effect=without_exact_repair),
              patch.object(weekly, "NOVEMBER_2016_MEDELLIN_WRAP_URL", "_prior_grid_")):
            before = weekly.parse_pdf(body, source_url)
        after = weekly.parse_pdf(body, weekly.NOVEMBER_2016_MEDELLIN_WRAP_URL)
        self.assertEqual((len(before), len(after)), (4709, 4709))
        self.assertEqual(sum(r["price"] is not None for r in after), 4560)
        self.assertEqual([r["source_locator"] for r in before],
                         [r["source_locator"] for r in after])
        changed = {}
        for old, new in zip(before, after):
            for field in set(old) | set(new):
                if field not in {"market", "details"}:
                    self.assertEqual(old.get(field), new.get(field),
                                     (new["source_locator"], field))
            if old["market"] != new["market"]:
                changed[new["source_locator"]] = new
        self.assertEqual(len(changed), 113)
        self.assertEqual(set(changed),
                         {r["source_locator"] for r in oracle["rows"]})
        for control in oracle["rows"]:
            with self.subTest(locator=control["source_locator"]):
                row = changed[control["source_locator"]]
                self.assertEqual(compact(row["product_name"]),
                                 compact(control["product_key"]))
                self.assertEqual(compact(row["market"]),
                                 compact(control["market"]))
                self.assertEqual([row["min"], row["max"],
                                  row["details"].get("literal_mean", row["price"])],
                                 control["money"])
                self.assertIn(
                    row["details"].get("native_market_join"),
                    {None, "november_2016_same_column_leading_market_line"},
                )
                if row["market"].startswith(("Medellín, Central", "Medellín, Plaza")):
                    self.assertEqual(
                        row["details"]["native_market_join"],
                        "november_2016_same_column_leading_market_line",
                    )

        workbook_rows = weekly.parse_workbook(annex, XLS_URL)
        self.assertEqual(len(workbook_rows), 4750)
        pdf_keys = collections.Counter(source_key(r) for r in after)
        annex_keys = collections.Counter(source_key(r) for r in workbook_rows)
        self.assertEqual(sum((pdf_keys & annex_keys).values()), 4709)
        self.assertEqual(sum((annex_keys - pdf_keys).values()), 41)
        self.assertFalse(pdf_keys - annex_keys)
        self.assertTrue(all(r["price"] is None and r["unit"] == "unverified"
                            for r in workbook_rows))

    def test_only_exact_pdf_asset_advances_its_replay_version(self):
        kind = "dane-weekly-pdf"
        self.assertEqual(asset_parser_version(
            kind, weekly.NOVEMBER_2016_MEDELLIN_WRAP_URL),
            parser_version(kind, weekly.NOVEMBER_2016_MEDELLIN_WRAP_URL))
        self.assertEqual(parser_version(kind, weekly.NOVEMBER_2016_MEDELLIN_WRAP_URL),
                         "official-v2:nov2016-medellin-market-wrap-v2:dane-weekly-v24")
        self.assertEqual(asset_parser_version(
            kind, weekly.NOVEMBER_2016_MEDELLIN_WRAP_URL + "?changed=1"),
            parser_version(kind))
        body = (SOURCE / f"{PDF_SHA}.pdf").read_bytes()
        with self.assertRaisesRegex(ValueError, "bytes changed"):
            weekly.parse_pdf(body + b"x", weekly.NOVEMBER_2016_MEDELLIN_WRAP_URL)


if __name__ == "__main__":
    unittest.main()
