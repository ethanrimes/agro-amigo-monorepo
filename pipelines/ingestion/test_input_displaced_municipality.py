"""Unchanged DANE pages with a next-row municipality after the prior price."""
from copy import deepcopy
from datetime import date
from hashlib import sha256
from pathlib import Path
import unittest

from . import pdf_sources as inputs
from .test_input_pdf_native_layouts import word

DATA = Path(__file__).parent / "testdata"


class DisplacedNativeMunicipality(unittest.TestCase):
    def test_actual_original_pages_preserve_both_rows_and_following_neighbor(self):
        # Full originals: b74fea1a1701d7a2096af50d461db3c4e3951b3a713be46251d5faa54ba3f483
        # and 6513fd4896e38de7c4d09971051928b9ad68bf53fb8ef4be6e1e3e772f992dbe.
        for file,digest,day,page,name,presentation,expected in (
            ("inputs_march2015_displaced_page67.pdf",
             "1e74d702a4e63b4a0273999a32264056be292a9b99a8abed9ef787d26557f1f0",
             date(2015,3,31),67,"Grapas 1 1/4 pulgadas x 9 BWG","caja por 1 kilogramo",
             (("Fresno",5100,6.3),("Fusagasugá",5100,-1.9),("Guadalajara de Buga",5217,-1.3))),
            ("inputs_july2015_displaced_page56.pdf",
             "1d1a22237adce90f599cfe077949011bf3e0e0371da09a5a139b4a52511cd2ae",
             date(2015,7,31),56,"Monitor","1 litro",
             (("Chipaque",24600,.8),("Chiquinquirá",22267,-1),("Choachí",25000,-2.9))),
        ):
            with self.subTest(file=file):
                body=(DATA/file).read_bytes()
                self.assertEqual(sha256(body).hexdigest(),digest)
                rows=list(inputs.parse_input_pdf(body,day))
                for town,price,change in expected:
                    row=next(r for r in rows if r[3:6]==(name,town,presentation))
                    self.assertEqual(row[1],"dane-inputs-pdf")
                    self.assertEqual(row[2],day)
                    self.assertEqual(row[6:8],(price,change))
                    self.assertEqual(row[-1]["page"],page)
                    self.assertIsNone(row[-1]["quality_issue"])
                displaced=next(r for r in rows if r[3:6]==(name,expected[1][0],presentation))
                self.assertEqual(displaced[-1]["printed_location_lines"][0],expected[1][0])
                self.assertEqual(displaced[-1]["location_recovery"]["method"],"native-displaced-municipality")

    def test_recovery_rejects_unknown_department_distant_lines_and_extra_cells(self):
        original=[(100,[word("Fresno (Tolima)",321,100,377),word("5.100",484,100,504),
                        word("6,3",504,100,515),word("Fusagasugá",517,100,562)]),
                  (108,[word("(Cundinamarca)",321,108,379),word("5.100",484,108,504),
                        word("-1,9",541,108,556)])]
        self.assertEqual(inputs._input_displaced_location(original,0,470,True)["line"],"Fresno (Tolima) 5.100 6,3")
        self.assertEqual(inputs._input_displaced_location(original,1,470,True)["line"],"Fusagasugá (Cundinamarca) 5.100 -1,9")
        for defect in ("department","distance","heading","extra-cell","price-alignment","already-complete"):
            lines=deepcopy(original)
            if defect=="department": lines[1][1][0]["text"]="(Lugar inventado)"
            if defect=="distance": lines[1][1][0]["top"]+=20
            if defect=="heading": lines[0][1][3]["fontname"]="FuturaStd-Heavy"
            if defect=="extra-cell": lines[1][1].append(word("100",565,108,580))
            if defect=="price-alignment": lines[1][1][1]["x1"]+=10
            if defect=="already-complete": lines[1][1][0]["text"]="Fusagasugá (Cundinamarca)"
            with self.subTest(defect=defect):
                self.assertIsNone(inputs._input_displaced_location(lines,0,470,True))
                self.assertIsNone(inputs._input_displaced_location(lines,1,470,True))
        self.assertIsNone(inputs._input_displaced_location(original,0,470,False))


if __name__=="__main__": unittest.main()
