"""Whole-original market-line regressions from two public SIPSA PDFs."""

import json
import unittest
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from pipelines.ingestion import dane_weekly as weekly
from pipelines.ingestion.worker import asset_parser_version, parser_version


SOURCE = Path(__file__).parent / "testdata/weekly_market_wrap_originals"
JAN_URL = (
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/"
    "Sem_14ene_2017_20ene_2017.pdf"
)


class WeeklyOriginalMarketWrap(unittest.TestCase):
    def compare_full_original(self, stem, url, oracle_name, row_count, repaired_count):
        body = (SOURCE / f"{stem}.pdf").read_bytes()
        oracle = json.loads((SOURCE / oracle_name).read_text())
        self.assertEqual(sha256(body).hexdigest(), stem)
        self.assertEqual(oracle["source_pdf_sha256"], stem)
        source_rows = oracle["rows"]
        self.assertEqual(len(source_rows), repaired_count)

        native_column = weekly._native_column

        def uncorrected_column(*args, **kwargs):
            return native_column(*args, **{
                **kwargs,
                "january_2017_market_wrap": False,
                "december_2022_popayan_wrap": False,
            })

        with patch.object(weekly, "_native_column", side_effect=uncorrected_column):
            before = weekly.parse_pdf(body, url)
        after = weekly.parse_pdf(body, url)
        self.assertEqual((len(before), len(after)), (row_count, row_count))
        self.assertEqual(
            [r["source_locator"] for r in before],
            [r["source_locator"] for r in after],
        )
        changes = {}
        for old, new in zip(before, after):
            for key in set(old) | set(new):
                if key not in {"market", "details"}:
                    self.assertEqual(old.get(key), new.get(key),
                                     (new["source_locator"], key))
            if old["market"] != new["market"]:
                changes[new["source_locator"]] = (old, new)
        self.assertEqual(len(changes), repaired_count)
        self.assertEqual(set(changes), {r["source_locator"] for r in source_rows})

        for source in source_rows:
            with self.subTest(locator=source["source_locator"]):
                row = changes[source["source_locator"]][1]
                self.assertEqual(row["product_name"], source["product"])
                self.assertEqual(row["market"], source["market"])
                mean = (row["price"] if row["price"] is not None
                        else row["details"].get("literal_mean"))
                self.assertEqual([row["min"], row["max"], mean], source["money"])
        return changes

    def test_jan20_all_507_native_market_repairs_preserve_4706_quotes(self):
        changes = self.compare_full_original(
            weekly.JANUARY_2017_MARKET_WRAP_ORIGINALS[JAN_URL], JAN_URL,
            "jan20_2017_507_native_oracle.json", 4706, 507,
        )
        self.assertEqual(
            sum(row[1]["price"] is None for row in changes.values()), 27,
        )
        cilantro = [new for _, new in changes.values()
                    if new["product_name"] == "Cilantro"
                    and new["market"] == "Marinilla (Antioquia)"]
        self.assertEqual([(r["min"], r["max"], r["price"]) for r in cilantro],
                         [(600, 800, 725)])

    def test_dec09_all_9_popayan_breaks_preserve_4372_quotes(self):
        changes = self.compare_full_original(
            weekly.DECEMBER_2022_POPAYAN_WRAP_SHA,
            weekly.DECEMBER_2022_POPAYAN_WRAP_URL,
            "dec09_2022_9_native_oracle.json", 4372, 9,
        )
        for old, new in changes.values():
            self.assertEqual(old["market"],
                             "Popayán, Plaza de mercado del barrio Bo- lívar")
            self.assertEqual(new["details"]["literal_market_lines"], [
                "Popayán, Plaza de mercado del barrio Bo-", "lívar",
            ])
            self.assertEqual(new["details"]["native_market_join"],
                             "december_2022_popayan_line_wrap")
        cilantro = [new for _, new in changes.values()
                    if new["product_name"] == "Cilantro"]
        self.assertEqual([(r["min"], r["max"], r["price"]) for r in cilantro],
                         [(3000, 3500, 3250)])

    def test_other_url_does_not_adopt_either_source_local_rule(self):
        for stem, url in (
            (weekly.JANUARY_2017_MARKET_WRAP_ORIGINALS[JAN_URL], JAN_URL),
            (weekly.DECEMBER_2022_POPAYAN_WRAP_SHA,
             weekly.DECEMBER_2022_POPAYAN_WRAP_URL),
        ):
            with self.subTest(stem=stem):
                body = (SOURCE / f"{stem}.pdf").read_bytes()
                ordinary = weekly.parse_pdf(body, url + "?changed-source=1")
                self.assertFalse(any(
                    r["details"].get("native_market_join") in {
                        "january_2017_same_column_leading_market_line",
                        "december_2022_popayan_line_wrap",
                    } for r in ordinary
                ))

    def test_only_two_exact_assets_advance_their_replay_versions(self):
        kind = "dane-weekly-pdf"
        base = parser_version(kind)
        self.assertEqual(asset_parser_version(kind, JAN_URL),
                         base + ":jan2017-market-wrap-v2")
        self.assertEqual(asset_parser_version(
            kind, weekly.DECEMBER_2022_POPAYAN_WRAP_URL),
            base + ":dec2022-popayan-line-wrap-v1")
        self.assertEqual(asset_parser_version(kind, JAN_URL + "?changed-source=1"),
                         base)


if __name__ == "__main__":
    unittest.main()
