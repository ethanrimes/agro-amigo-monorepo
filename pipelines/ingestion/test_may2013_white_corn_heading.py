"""Original-backed regression for the exact May 2013 native heading."""
import hashlib
import json
import unittest
from pathlib import Path

from pipelines.ingestion import dane_weekly as weekly

FIX = Path(__file__).parent / "testdata" / "may2013_white_corn_heading"
URL = weekly.MAY2013_WHITE_CORN_URL
DID = weekly.MAY2013_WHITE_CORN_SHA
REVISION = "official-v2:may2013-white-corn-heading-v1:dane-weekly-v24"


def canonical_sha(value):
    return hashlib.sha256((json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()).hexdigest()


class May2013WhiteCornHeading(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = (FIX / "may2013_original.pdf").read_bytes()
        cls.native_expected = json.loads((FIX / "may2013_native_4404_expected.json").read_text())
        cls.prior = json.loads((FIX / "may2013_v24_quotes_4201_prior.json").read_text())
        cls.expected = json.loads((FIX / "may2013_heading_quotes_4201_expected.json").read_text())

    def test_exact_original_emits_complete_native_4404_row_vector(self):
        self.assertEqual(hashlib.sha256(self.body).hexdigest(), DID)
        actual = weekly.parse_pdf(self.body, URL)
        self.assertEqual(len(actual), 4404)
        self.assertEqual(canonical_sha(actual), "8815e38040163575f92ac220e93ac38d49cfa1bac36507800bf0f1c1bc26bb96")
        self.assertEqual(actual, self.native_expected)
        self.assertEqual(sum(row.get("price") is not None and not row.get("details", {}).get("quality_issue") for row in actual), 4201)
        self.assertEqual(sum(bool(row.get("price") is None or row.get("details", {}).get("quality_issue")) for row in actual), 203)

    def test_complete_old_and_new_sql_vectors_change_only_two_reviewed_identities(self):
        self.assertEqual(hashlib.sha256((FIX / "may2013_v24_quotes_4201_prior.json").read_bytes()).hexdigest(), "937703c6a009617751c4b2a54e460f42b3edba7d3e7d1c3653e46ce0ce6bb83a")
        self.assertEqual((len(self.prior), len(self.expected)), (4201, 4201))
        self.assertEqual(canonical_sha(self.expected), "9dc37bb515a6c7460a31952a1d77af4eecc00462c537b9a4c4cb64e6d50b3188")
        prior = {row["source_locator"]: row for row in self.prior}
        current = {row["source_locator"]: row for row in self.expected}
        old_targets = {
            "PDF page 29,table 1,column 2,line 27": ("Medellín, Central Mayorista de Antioquia", "905.0", "="),
            "PDF page 29,table 1,column 2,line 28": ("San Vicente (Antioquia)", "1000.0", "++"),
        }
        self.assertEqual(set(prior) - set(old_targets), set(current) - {
            old + ":may2013-white-corn-heading-v1" for old in old_targets
        })
        for locator in set(prior) - set(old_targets):
            old = dict(prior[locator]); new = dict(current[locator])
            old.pop("xmin", None)
            old["parser_version"] = REVISION
            self.assertEqual(old, new, locator)
        for old_locator, (market, amount, trend) in old_targets.items():
            old = prior[old_locator]
            new_locator = old_locator + ":may2013-white-corn-heading-v1"
            new = current[new_locator]
            self.assertEqual((old["product_id"], old["product_name"], old["market"], old["price"]),
                             ("maiz-amarillo-trillado", "Maíz amarillo trillado",
                              "Maíz blanco cáscara " + market if "Medellín" in market else market, amount))
            self.assertEqual((new["product_id"], new["product_name"], new["category"], new["market"], new["unit"], new["observed_on"], new["price"], new["min_price"], new["max_price"], new["source_page"]),
                             ("maiz-blanco-cascara", "Maíz blanco cáscara", "granos y cereales", market, "kg", "2013-05-24", amount, amount, amount, 29))
            self.assertEqual(new["parser_version"], REVISION)
            self.assertEqual(new["details"].get("trend"), trend)
            self.assertEqual(new["details"].get("native_heading_recovery"), "exact_may2013_page29_column2_heading_before_wrapped_market_v1")
        actual_native = weekly.parse_pdf(self.body, URL)
        target_rows = {row["source_locator"]: row for row in actual_native if row.get("details", {}).get("native_heading_recovery")}
        self.assertEqual(set(target_rows), {old + ":may2013-white-corn-heading-v1" for old in old_targets})

    def test_exact_source_binding_rejects_changed_original_bytes(self):
        with self.assertRaisesRegex(ValueError, "Exact May 2013 weekly PDF bytes changed"):
            weekly.parse_pdf(self.body + b"x", URL)

    def test_heading_recovery_does_not_apply_to_another_url(self):
        other = weekly.parse_pdf(self.body, URL + "?unbound=1")
        self.assertEqual(len(other), 4404)
        self.assertFalse(any(row.get("details", {}).get("native_heading_recovery") for row in other))
        targets = [row for row in other if row.get("source_locator") in {
            "PDF page 29,table 1,column 2,line 27", "PDF page 29,table 1,column 2,line 28"
        }]
        self.assertEqual(len(targets), 2)
        self.assertTrue(all(row["product_id"] == "maiz-amarillo-trillado" for row in targets))


if __name__ == "__main__":
    unittest.main()
