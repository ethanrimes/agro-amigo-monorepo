"""Offline mutation and independent text-engine controls for the private candidate."""
import hashlib
import re
import subprocess
import unittest
from datetime import date
from pathlib import Path

from . import daily_prose_generic as candidate

HERE = Path(__file__).resolve().parent / "testdata/daily_prose_generic"
_DAYS = (
    ("2026-10-01", "89f1bd8d6c27f92daeacdea07914ad8f5f93cf85886ea97082fcdee2d699b8c7", 23),
    ("2026-10-02", "e176e5f6134d19a2797f364e4d2bd472981ec5ba91b7f3e828839313cad79f37", 23),
    ("2026-10-05", "c220e350191e8fc30199cd3994b5c093bc0716d7df498edf17953e7224d1e543", 25),
    ("2026-10-06", "60087dcd12480c65a3901075e3ae8fd36bbbfd922b419f497d9ff8d22858b51f", 26),
    ("2026-10-07", "fb0c840f6ea8c38d8fe810ae88ff2bbaf97c713a1ad4d3b2fc69500aca32feb9", 23),
)
SOURCES = [
    {"day": day, "did": did, "review_count": count,
     "url": "https://www.dane.gov.co/files/operaciones/SIPSA/"
            f"bol-SIPSADiario-{day[-2:]}oct2026.pdf"}
    for day, did, count in _DAYS
]


class GenericDailyProseCandidate(unittest.TestCase):
    def test_five_real_retained_originals_and_poppler_first_prices(self):
        counts=[]
        for source in SOURCES:
            pdf=HERE/(source["did"]+".pdf")
            body=pdf.read_bytes()
            rows,reviews=candidate.parse_generic(body,source["url"],source["did"],
                                                   date.fromisoformat(source["day"]))
            self.assertEqual(len(rows)+len(reviews),source["review_count"])
            self.assertTrue(all(row[1]=="dane-daily" and row[5]=="kg" and row[6]>0 for row in rows))
            self.assertTrue(all("requires_explicit_product_binding" in r[1]["reason_code"]
                                for r in reviews if ",price 2," in r[0]))
            for row in rows:
                page=int(re.search(r"PDF page (\d+)",row[0]).group(1))
                poppler=subprocess.run(["pdftotext","-f",str(page),"-l",str(page),
                    "-layout",str(pdf),"-"],check=True,capture_output=True,text=True).stdout
                blocks=[re.sub(r"\s+"," ",part) for part in re.split(r"\n\s*\n",poppler)
                        if part.strip()]
                independent=[block for block in blocks
                    if row[8]["price_literal"] in block
                    and candidate.fold(row[3]) in candidate.fold(block)
                    and row[8]["change_percent_literal"] in block]
                self.assertEqual(len(independent),1)
                before_price=independent[0].split(row[8]["price_literal"])[0]
                city,site=row[4].split(", ",1)
                if city=="Bogotá" and site.startswith("D.C., "):
                    site=site[len("D.C., "):]
                self.assertIsNotNone(candidate.exact_token(before_price,city))
                self.assertIsNotNone(candidate.exact_token(before_price,site))
            counts.append((len(rows),len(reviews)))
        self.assertEqual(counts,[(14,9),(14,9),(15,10),(14,12),(15,8)])

    def test_literal_unknown_product_is_preserved_not_merged_with_a_variety(self):
        source=SOURCES[0]
        rows,_=candidate.parse_generic((HERE/(source["did"]+".pdf")).read_bytes(),
            source["url"],source["did"],date.fromisoformat(source["day"]))
        literal=[r for r in rows if r[3]=="guayaba"]
        self.assertEqual(len(literal),1)
        self.assertEqual(literal[0][8]["source_product_caption"],"guayaba")
        self.assertEqual(literal[0][8]["product_basis"],"literal_native_caption")
        self.assertNotEqual(literal[0][3],"Guayaba pera")
        known=next(r for r in rows if r[3]=="Limón Tahití")
        self.assertEqual(known[8]["source_product_caption"],"limón Tahití")
        self.assertEqual(known[8]["product_basis"],"known_exact_label")

    def test_whole_printed_caption_precedes_known_label_lookup(self):
        base=("La habichuela presentó un aumento en su precio del 38% en Popayán, "
              "Plaza de mercado del barrio Bolívar, cotizándose el kilogramo a $6.500")
        ordinary,reason=candidate.first_quote(base)
        self.assertIsNone(reason)
        self.assertEqual((ordinary["product"],ordinary["source_product_caption"]),
                         ("Habichuela","habichuela"))
        for replacement in ("habichuela roja", "habichuela extra"):
            row,reason=candidate.first_quote(base.replace("habichuela",replacement))
            self.assertIsNone(reason)
            self.assertEqual(row["product"],replacement)
            self.assertEqual(row["source_product_caption"],replacement)
            self.assertEqual(row["product_basis"],"literal_native_caption")
        # A different *full* name may itself be in the registry. It still
        # must never collapse to the shorter Habichuela identity.
        long_row,reason=candidate.first_quote(base.replace("habichuela","habichuela larga"))
        self.assertIsNone(reason)
        self.assertEqual(long_row["source_product_caption"],"habichuela larga")
        self.assertEqual(long_row["product"],"Habichuela larga")
        self.assertNotEqual(long_row["product"],ordinary["product"])
        for replacement in ("habichuela y pimentón", "habichuela o pimentón"):
            row,_=candidate.first_quote(base.replace("habichuela",replacement))
            self.assertIsNone(row)

    def test_prior_or_negated_movement_before_price_stays_review(self):
        base=("La habichuela presentó un aumento en su precio del 38% en Popayán, "
              "Plaza de mercado del barrio Bolívar, cotizándose el kilogramo a $6.500")
        for changed in (
            base.replace("presentó un aumento", "no presentó aumento"),
            base.replace("presentó un aumento", "sin aumento"),
            base.replace("presentó un aumento", "si presenta un aumento"),
            base.replace("presentó un aumento", "en septiembre presentó un aumento"),
            base.replace("presentó un aumento", "en 2025 presentó un aumento"),
            base.replace("$6.500", "$6.500; en septiembre $5.000"),
        ):
            with self.subTest(changed=changed):
                if "$6.500;" in changed:
                    # A historical mention *after* this current first quote must
                    # not be reassigned to it; it is a separate review span.
                    row,_=candidate.first_quote(changed)
                    self.assertIsNotNone(row)
                else:
                    row,_=candidate.first_quote(changed)
                    self.assertIsNone(row)

    def test_supply_causation_after_price_percentage_does_not_reverse_price(self):
        source=SOURCES[0]
        rows,_=candidate.parse_generic((HERE/(source["did"]+".pdf")).read_bytes(),
            source["url"],source["did"],date.fromisoformat(source["day"]))
        maracuya=[row for row in rows if row[8]["source_product_caption"]=="maracuyá"
                  and row[6]==4800]
        self.assertEqual(len(maracuya),1)
        self.assertEqual(maracuya[0][7],-15)
        self.assertIn("aumento en la oferta",maracuya[0][8]["source_quote"])
        contradictory=("El maracuyá presentó una reducción y un aumento en su precio del "
                       "15% en Ibagué, Plaza La 21, comercializándose el kilo a $4.800")
        self.assertIsNone(candidate.first_quote(contradictory)[0])

    def test_whole_positive_money_literal_no_decimal_or_scale_truncation(self):
        base=("La habichuela presentó un aumento en su precio del 38% en Popayán, "
              "Plaza de mercado del barrio Bolívar, cotizándose el kilogramo a $6.500")
        self.assertEqual(candidate.first_quote(base)[0]["price"],6500)
        for bad in ("$6.500,50", "$6,500", "$6.5", "$0", "$6.500 mil",
                    "$6.500 millones"):
            with self.subTest(bad=bad):
                row,reason=candidate.first_quote(base.replace("$6.500",bad))
                self.assertIsNone(row)
                self.assertEqual(reason,"money_token_not_exact_positive_pesos")

    def test_exact_visible_source_examples(self):
        expected={
            "2026-10-01":("Cebolla junca","Bogotá, D.C., Corabastos",1542,-20),
            "2026-10-02":("Habichuela","Popayán, Plaza de mercado del barrio Bolívar",6500,38),
            "2026-10-05":("Habichuela","Manizales, Centro Galerías",6600,65),
            "2026-10-06":("Habichuela","Bucaramanga, Centroabastos",7333,43),
            "2026-10-07":("Remolacha","Pereira, Mercasa",2533,17),
        }
        for source in SOURCES:
            rows,_=candidate.parse_generic((HERE/(source["did"]+".pdf")).read_bytes(),
                source["url"],source["did"],date.fromisoformat(source["day"]))
            self.assertEqual(tuple(rows[0][3:5])+tuple(rows[0][6:8]),expected[source["day"]])

    def test_changed_body_or_registered_day_fails_closed(self):
        source=SOURCES[-1]
        body=(HERE/(source["did"]+".pdf")).read_bytes()
        with self.assertRaisesRegex(ValueError,"SHA mismatch"):
            candidate.parse_generic(body+b"changed",source["url"],source["did"],date(2026,10,7))
        for url,day in ((source["url"],date(2026,10,6)),
                        (source["url"].replace("07oct","08oct"),date(2026,10,7)),
                        (source["url"].replace("www.dane.gov.co","example.com"),date(2026,10,7))):
            rows,reviews=candidate.parse_generic(body,url,source["did"],day)
            self.assertEqual((len(rows),len(reviews)),(0,23))

    def test_unbound_product_market_unit_and_basis_review(self):
        base=("La habichuela presentó un aumento en su precio del 38% en Popayán, "
              "Plaza de mercado del barrio Bolívar, cotizándose el kilogramo a $6.500")
        self.assertIsNotNone(candidate.first_quote(base)[0])
        changes=(
            base.replace("habichuela","hortaliza"),
            base.replace("Plaza de mercado del barrio Bolívar","un mercado"),
            base.replace("Popayán, Plaza de mercado del barrio Bolívar","Barranquilla"),
            base.replace("kilogramo","bulto"),
            base.replace("del 38%","del 38% y del 22%"),
            base.replace("aumento","aumento y disminución"),
            base.replace("su precio","su precio promedio"),
            base.replace("cotizándose el kilogramo a $6.500",
                         "cotizándose el bulto a $6.500, distinto kilogramo"),
            base.replace("presentó un aumento", "presentó ayer un aumento"),
            base.replace("presentó un aumento", "presentó la semana pasada un aumento"),
            base.replace("presentó un aumento", "presentó un aumento estimado"),
            base.replace("presentó un aumento", "si hubiera presentado un aumento"),
            base.replace("cotizándose", "no se vendió y cotizándose"),
            base.replace("en Popayán, Plaza de mercado del barrio Bolívar,",
                         "procedente de Popayán, Plaza de mercado del barrio Bolívar,"),
            base.replace("La habichuela presentó", "La habichuela fue enviada ayer. Presentó"),
        )
        for mutated in changes:
            with self.subTest(mutated=mutated):
                self.assertIsNone(candidate.first_quote(mutated)[0])

    def test_second_anaphoric_money_is_review_even_if_same_market_known(self):
        source=SOURCES[-1]
        rows,reviews=candidate.parse_generic((HERE/(source["did"]+".pdf")).read_bytes(),
            source["url"],source["did"],date(2026,10,7))
        self.assertTrue(any("PDF page 1,paragraph 3,price 1," in r[0] for r in rows))
        self.assertTrue(any("PDF page 1,paragraph 3,price 2," in r[0] and
            r[1]["reason_code"]=="later_money_requires_explicit_product_binding" for r in reviews))

    def test_bare_city_stays_review(self):
        reasons={}
        for source in SOURCES:
            _,reviews=candidate.parse_generic((HERE/(source["did"]+".pdf")).read_bytes(),
                source["url"],source["did"],date.fromisoformat(source["day"]))
            reasons[source["day"]]=[r[1]["reason_code"] for r in reviews if ",price 1," in r[0]]
        self.assertEqual(reasons["2026-10-01"],[])
        self.assertEqual(reasons["2026-10-02"],["market_not_unique_or_named"])
        self.assertEqual(reasons["2026-10-05"],["market_not_unique_or_named"])
        self.assertEqual(reasons["2026-10-06"],[])
        self.assertEqual(reasons["2026-10-07"],[])


if __name__=="__main__":
    unittest.main()
