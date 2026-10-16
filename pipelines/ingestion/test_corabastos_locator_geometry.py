"""Source-bound locator guard controls using six retained original PDFs."""
from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path

from . import colombia_sources
from .corabastos_locator_geometry import FIELDS, full20, plan
from .corabastos_source_relocation import (HELD_NOVEL_ORIGINALS, KIND,
                                            REVIEWED_ORIGINALS)

FIXTURES = Path(__file__).parent / "testdata/corabastos_locator"
EXPECTED_MOVES = {"8748df4db724": 12, "5b16541ebf21": 18,
                  "855beb303e4b": 14, "bb77b9ac465f": 14,
                  "1cf46b5a7fc9": 12, "a6bd81f04321": 18}


def sources():
    cases = []
    for path in sorted(FIXTURES.glob("prior-*.json")):
        saved = json.loads(path.read_text())
        did, url = saved["document_id"], saved["url"]
        body = (FIXTURES / url.rsplit("/", 1)[-1]).read_bytes()
        if hashlib.sha256(body).hexdigest() != did or REVIEWED_ORIGINALS.get(did) != url:
            raise ValueError("Corabastos fixture does not match reviewed original")
        prior = [full20(row) for row in saved["prior_quotes"]]
        proposed = [full20(row) for row in colombia_sources.parse(body, url, KIND)]
        if not len(prior) == len(proposed) == 350:
            raise ValueError("Complete 350-row source proof unavailable")
        cases.append((did, url, body, prior, proposed))
    if len(cases) != 6:
        raise ValueError("Exactly six reviewed sources required")
    return cases


class CorabastosLocatorGeometry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = sources()

    def test_all_six_whole_originals_only_move_bounded_locators(self):
        for did, url, body, prior, proposed in self.cases:
            with self.subTest(url=url):
                proof = plan(did, url, body, prior, proposed)
                self.assertEqual(len(proof["retirements"]), EXPECTED_MOVES[did[:12]])
                self.assertEqual(proof["complete_source_quotes"], 350)
                self.assertEqual(proof["new_source_rows"], ())

    def test_every_business_field_mutation_is_refused(self):
        did, url, body, prior, proposed = self.cases[0]
        for field in FIELDS:
            for change_old in (False, True):
                changed = copy.deepcopy(prior if change_old else proposed)
                value = changed[0][field]
                changed[0][field] = (value + 1 if isinstance(value, (int, float))
                                     else "WRONG" if value is not None else 1.0)
                with self.subTest(field=field, old=change_old), self.assertRaises((ValueError, TypeError)):
                    plan(did, url, body,
                         changed if change_old else prior,
                         proposed if change_old else changed)

    def test_wrong_body_url_or_locator_geometry_is_refused(self):
        did, url, body, prior, proposed = self.cases[0]
        for other_body, other_url in ((body + b"changed", url),
                                      (body, url.replace("corabastos.com.co", "example.com"))):
            with self.assertRaises(ValueError):
                plan(did, other_url, other_body, prior, proposed)
        for locator in ("PDF page 9, y 201.0; price column 1",
                        "PDF page 1, y 201.0; price column 2",
                        "PDF page 1, y 900.0; price column 1"):
            changed = copy.deepcopy(prior)
            changed[0]["source_locator"] = locator
            with self.subTest(locator=locator), self.assertRaises(ValueError):
                plan(did, url, body, changed, proposed)

    def test_partial_duplicate_and_novel_august_one_are_not_whitelisted(self):
        did, url, body, prior, proposed = self.cases[0]
        for changed in (proposed[:-1], proposed + [proposed[0]]):
            with self.assertRaises(ValueError):
                plan(did, url, body, prior, changed)
        self.assertFalse(set(HELD_NOVEL_ORIGINALS) & set(REVIEWED_ORIGINALS))
        self.assertFalse(set(HELD_NOVEL_ORIGINALS.values()) & set(REVIEWED_ORIGINALS.values()))


if __name__ == "__main__":
    unittest.main()
