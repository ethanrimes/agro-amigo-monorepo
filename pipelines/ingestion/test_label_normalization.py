"""Source-backed orthography, identity boundaries and automatic publication."""

import getpass
import hashlib
import json
import random
import shutil
import subprocess
import tempfile
import time
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import psycopg

from . import label_normalization as labels, worker


class ReviewedLabelTests(unittest.TestCase):
    def test_nov2021_printed_category_typo_is_display_only_and_source_bound(self):
        import io
        import zipfile
        import pdfplumber

        evidence = next(e for e in labels.LEXICON["evidence"]
                        if e.get("raw_alias") == "Verduras y hortailizas")
        archive = (Path(__file__).resolve().parents[2] / evidence["fixture"]).read_bytes()
        self.assertEqual(hashlib.sha256(archive).hexdigest(), evidence["source_sha256"])
        with zipfile.ZipFile(io.BytesIO(archive)) as source:
            children = [source.read(entry) for entry in source.infolist()]
        body = next(b for b in children
                    if hashlib.sha256(b).hexdigest() == evidence["child_sha256"])
        with pdfplumber.open(io.BytesIO(body)) as source:
            self.assertIn(evidence["source_literal"].lower(),
                          source.pages[1].extract_text().lower())
        for raw in ("Verduras y hortailizas", "VERDURAS Y HORTAILIZAS"):
            self.assertEqual(labels.category(raw), "Verduras y hortalizas")
            self.assertEqual(labels.change(raw, "category")["original"], raw)
            for domain in ("product", "input"):
                self.assertEqual(labels.normalize(raw, domain), raw)
        self.assertEqual(labels.category("Verduras y hortailizas > Leguminosas"),
                         "Verduras y hortalizas > Leguminosas")
        self.assertEqual(labels.category("Verduras y hortailizas especiales"),
                         "Verduras y hortailizas especiales")

    def test_tuquerres_category_uses_printed_spacing_and_retains_raw_witness(self):
        import io
        import pdfplumber
        evidence = next(e for e in labels.LEXICON["evidence"] if e.get("raw_alias") == "Otrostuberculos")
        body = (Path(__file__).resolve().parents[2] / evidence["fixture"]).read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(), evidence["source_sha256"])
        with pdfplumber.open(io.BytesIO(body)) as pdf:
            self.assertEqual(len(pdf.pages), 1)
            self.assertIn(evidence["raw_alias"], pdf.pages[0].extract_text())
        # Independent native text preserves the visible word gap that the
        # former default extraction swallowed; neither engine uses OCR.
        text = subprocess.check_output(["pdftotext", "-layout", "-", "-"], input=body).decode()
        self.assertIn("17 de Julio de 2024", text)
        self.assertIn(evidence["source_literal"], text)
        self.assertIn("Ulluco Bulto 30 Kilogramo 30.000 35.000 0 0", " ".join(text.split()))
        for raw in ("Otros tuberculos", "OTROSTUBERCULOS", "Otros tube\u0301rculos"):
            self.assertEqual(labels.category(raw), evidence["canonical"])
            proof = labels.change(raw, "category")
            self.assertEqual(proof["original"], raw)
            self.assertEqual(proof["normalized"], evidence["canonical"])
        self.assertEqual(labels.category("Tuberculos, raices y platanos > Otrostuberculos"),
                         "Tubérculos, raíces y plátanos > Otros tubérculos")
        self.assertEqual(labels.category("Otrostuberculos especiales"), "Otrostuberculos especiales")
        for domain in ("product", "input"):
            self.assertEqual(labels.normalize("Otrostuberculos", domain), "Otrostuberculos")

    def test_joined_category_alias_is_bound_to_retained_native_heading(self):
        import io
        import pdfplumber
        from . import city_reports
        evidence = next(e for e in labels.LEXICON["evidence"] if e.get("raw_alias") == "Otrasfrutas")
        body = (Path(__file__).resolve().parents[2] / evidence["fixture"]).read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(), evidence["source_sha256"])
        with pdfplumber.open(io.BytesIO(body)) as pdf:
            self.assertIn(evidence["raw_alias"], pdf.pages[0].extract_text())
        native = list(city_reports.parse_city_pdf(body, date(2025, 1, 7)))
        self.assertEqual(len(native), 48)
        self.assertEqual(sum(row[5] == "Frutas > Otras frutas" for row in native), 16)
        self.assertEqual(labels.category("FRUTAS > OTRASFRUTAS"), "Frutas > Otras frutas")
        self.assertEqual(labels.normalize("Otrasfrutas especiales", "category"), "Otrasfrutas especiales")
        for domain in ("product", "input"):
            self.assertEqual(labels.normalize("Otrasfrutas", domain), "Otrasfrutas")
        evidence = labels.change("Frutas > Otrasfrutas", "category")
        self.assertEqual(evidence["original"], "Frutas > Otrasfrutas")
        self.assertEqual(evidence["normalized"], "Frutas > Otras frutas")
        self.assertEqual(evidence["method"], "exact-reviewed-label")

    def test_all_native_product_options_are_original_bound_and_unambiguous(self):
        evidence = next(e for e in labels.LEXICON["evidence"] if e.get("domain") == "product")
        path = Path(__file__).resolve().parents[2] / evidence["fixture"]
        body = path.read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(), evidence["source_sha256"])
        native = json.loads(body)
        self.assertEqual(int(native["queryInfo"]["totalRows"]), 382)
        self.assertEqual(labels.LEXICON["domains"]["product"], [r[0] for r in native["resultset"]])
        for (name,) in native["resultset"]:
            with self.subTest(name=name):
                variant = name.upper().translate(str.maketrans("ÁÉÍÓÚÜ", "AEIOUU"))
                self.assertEqual(labels.normalize(variant), name)
                self.assertEqual(worker.slug(variant), worker.slug(name))

    def test_cienaga_display_accent_keeps_de_and_exact_source_identity(self):
        import io
        import pdfplumber
        from . import city_reports

        evidence = next(e for e in labels.LEXICON["evidence"]
                        if e.get("raw_product_id") == "limon-comun-de-cienaga")
        body = (Path(__file__).resolve().parents[2] / evidence["fixture"]).read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(), evidence["source_sha256"])
        self.assertEqual(evidence["parent_sha256"],
                         "8abfbdfa276dad94403bf053b2a1773548bf6855b81dd818eb5119c5f5a944fd")
        with pdfplumber.open(io.BytesIO(body)) as pdf:
            self.assertEqual(len(pdf.pages), 4)
            text = pdf.pages[0].extract_text()
            self.assertIn("Barranquilla, Barranquillita", text)
            self.assertIn("Limon comun de Cienaga Bulto 50 Kilogramo 355.000 360.000", text)
        rows = list(city_reports.parse_city_pdf(body, date(2022, 1, 5)))
        self.assertEqual(len(rows), 113)
        selected = [row for row in rows if row[2] == evidence["raw_product_id"]]
        self.assertEqual(len(selected), 1, "Printed second round is blank, not a zero-price row")
        row = selected[0]
        self.assertEqual(row[0], "PDF page 1,table 1,row 13,round 1")
        self.assertEqual((row[3], row[4], row[5], row[6], str(row[7]), row[8], row[9],
                          str(row[11]), str(row[12])),
                         ("Limon comun de Cienaga", "Barranquilla, Barranquillita",
                          "Frutas", "Bulto", "50", "Kilogramo", 1, "355000", "360000"))
        self.assertEqual(labels.LEXICON["product_display_only"], [
            {"raw": row[3], "canonical": "Limón común de Ciénaga",
             "product_id": row[2]}])
        self.assertEqual(worker.slug(row[3]), worker.slug(labels.product_label(row[3])))
        self.assertEqual(worker.slug(row[3]), row[2])
        self.assertEqual(labels.normalize("LIMON COMUN DE CIENAGA"), "Limón común de Ciénaga")
        self.assertEqual(labels.product_label(row[3]), "Limón común de Ciénaga")
        self.assertEqual(labels.change(row[3], "product")["method"], "exact-reviewed-label")
        self.assertEqual(worker.slug("Limón común Ciénaga"), "limon-comun-cienaga")
        self.assertNotEqual(worker.slug("Limón común Ciénaga"), row[2])
        for near in ("Limón común", "Limón común Ciénaga", "Limon comun de Cienaga extra",
                     "Limón común de la Ciénaga"):
            self.assertNotEqual(labels.normalize(near), "Limón común de Ciénaga")
        self.assertEqual(labels.normalize(row[3], "input"), row[3])

    def test_cienaga_rule_rejects_entity_merge_or_changed_id(self):
        for bad in (
            {"raw": "Limon comun de Cienaga", "canonical": "Limón común Ciénaga",
             "product_id": "limon-comun-de-cienaga"},
            {"raw": "Limon comun de Cienaga", "canonical": "Limón común de Ciénaga",
             "product_id": "limon-comun-cienaga"},
        ):
            with self.subTest(bad=bad), patch.dict(labels.LEXICON,
                                                   {"product_display_only": [bad]}):
                with self.assertRaisesRegex(ValueError, "identity-changing"):
                    labels._lexicon()

    def test_caparrapi_detached_token_is_exact_source_scoped_display_only(self):
        fixture_path = Path(__file__).resolve().parent / "testdata/panela_caparrapi_1234_reference_fixture.json"
        fixture = json.loads(fixture_path.read_text())
        row, evidence = fixture["reference"], fixture["source_evidence"]
        rule = labels.LEXICON["source_scoped_product_display_only"][0]
        self.assertEqual(evidence["source_url"], row["source_url"])
        self.assertEqual(evidence["document_id_sha256"], row["document_id"])
        self.assertEqual(row["document_id"], rule["document_id"])
        self.assertEqual(row["source_locator"], rule["source_locator"])
        self.assertEqual(row["product_id"], rule["product_id"])
        self.assertEqual(row["product_name"], rule["raw"])
        self.assertEqual(row["details"]["identity_dimensions"]["source_product"], rule["source_product"])
        self.assertEqual(evidence["printed_heading"], rule["canonical"])
        self.assertEqual(evidence["detached_token"], "1234")
        self.assertIn("unresolved", evidence["interpretation_limit"])

        shown = labels.official_product_label(row)
        self.assertEqual(shown, rule["canonical"])
        self.assertEqual(row["product_name"], rule["raw"])
        self.assertEqual((row["price"], row["min_price"], row["max_price"], row["observed_on"],
                          row["unit"], row["source_locator"]),
                         (1550, 1550, 1550, "2013-02-15", "kg", rule["source_locator"]))

        negatives = []
        for field, value in (("document_id", "f" * 64),
                             ("source_locator", "PDF page 42,table 1,column 1,line 4"),
                             ("product_id", "panela-cuadrada-morena"),
                             ("product_name", "Panela cuadrada morena 1235")):
            changed = dict(row)
            changed[field] = value
            negatives.append(changed)
        changed = json.loads(json.dumps(row))
        changed["details"]["identity_dimensions"]["source_product"] = "Panela cuadrada morena"
        negatives.append(changed)
        for changed in negatives:
            with self.subTest(changed=(changed.get("document_id"), changed.get("source_locator"),
                                       changed.get("product_id"), changed.get("product_name"))):
                self.assertEqual(labels.official_product_label(changed), changed["product_name"])
        for literal in ("Wuxal 16-16-12", "Wuxal tapa negra 16-16-12 1 litro",
                        "Papa R-12 negra", "Panela cuadrada morena 1234 extra"):
            self.assertEqual(labels.product_label(literal), literal)

    def test_source_scoped_product_display_rules_reject_duplicate_or_ambiguous_selectors(self):
        rule = labels.LEXICON["source_scoped_product_display_only"][0]
        for rules in ([rule, dict(rule)],
                      [rule, {**rule, "canonical": "Panela cuadrada"}],
                      [{**rule, "product_id": "panela-cuadrada-morena"}]):
            with self.subTest(rules=rules), patch.dict(labels.LEXICON,
                                                       {"source_scoped_product_display_only": rules}):
                with self.assertRaisesRegex(ValueError, "source-scoped product display rule"):
                    labels._lexicon()

    def test_unicode_hygiene_does_not_invent_or_casefold_unknown_names(self):
        self.assertEqual(labels.normalize("  Cafe\u0301\u200b especial\t de\n finca  "), "Café especial de finca")
        self.assertEqual(labels.normalize("Wuxal\u00ad Tapa Negra 16-16-12", "input"), "Wuxal Tapa Negra 16-16-12")
        for name in ("WUXAL tapa NEGRA 16-16-12", "Papa R-12 negra extra", "Melón Cantaloupe", "Pina gold", "Cafe arabica premium"):
            self.assertEqual(labels.normalize(name), name)
        self.assertNotEqual(labels.key("Piña gold"), labels.key("Pina gold"))

    def test_variety_brand_grade_formulation_and_packages_remain_distinct(self):
        for domain, names in (
            ("product", ["Papa R-12 negra", "Papa R-12 roja", "Papa Puracé"]),
            ("input", ["Wuxal Tapa Negra", "Wuxal tapa negra 16-16-12", "Wuxal Tapa Negra 1 L", "Wuxal Tapa Negra 20 L"]),
            ("product", ["Arroz de primera", "Arroz cristal", "Arroz cristal · en molino"]),
            ("presentation", ["Caja de cartón 2.5 kg", "Caja de cartón 12.5 kg"]),
        ):
            self.assertEqual(len({labels.normalize(n, domain) for n in names}), len(names))
        self.assertEqual(labels.normalize("MARACUYA", "input"), "MARACUYA")
        self.assertEqual(labels.normalize("MARACUYA", "product"), "Maracuyá")

    def test_exact_categories_accents_and_product_casing(self):
        self.assertEqual(labels.normalize("limon tahiti"), "Limón Tahití")
        self.assertEqual(labels.category("FRUTAS > Citricos"), "Frutas > Cítricos")
        self.assertEqual(labels.category("Lacteos y huevos"), "Lácteos y huevos")
        self.assertEqual(labels.category("frutas frescas"), "Frutas frescas")
        self.assertEqual(labels.category("FRUTAS FRESCAS"), "Frutas frescas")
        for raw in ("FRUTAS\u00a0>\u00a0CITRICOS", "FRUTAS\t>\tCITRICOS", "FRUTAS\n>\nCITRICOS"):
            with self.subTest(raw=raw):
                self.assertEqual(labels.category(raw), "Frutas > Cítricos")
                self.assertEqual(labels.category(labels.category(raw)), "Frutas > Cítricos")
                evidence = labels.change(raw, "category")
                self.assertEqual(evidence["original"], raw)
                self.assertEqual(evidence["normalized"], "Frutas > Cítricos")
                self.assertEqual(evidence["method"], "exact-reviewed-label")
        self.assertEqual(labels.category("FRUTAS\u00a0>\tSubgrupo R-12"), "Frutas > Subgrupo R-12")
        self.assertEqual(labels.change("Otro\u00a0>\tSubgrupo R-12", "category")["method"], "unicode-whitespace")
        self.assertEqual(labels.normalize("Caja de cartÓn", "presentation"), "Caja de cartón")
        self.assertEqual(labels.normalize("Quindio", "place"), "Quindío")
        for value in ("Limón Tahití (contiunuación)", "Pepinocohombro", "Papacriollasucia", "San Juan Nepomu- ceno"):
            # These require native geometry/context, not the spelling lexicon.
            self.assertEqual(labels.normalize(value), value)

    def test_cleaning_is_idempotent_and_original_is_retained_in_evidence(self):
        evidence = labels.change("limon tahiti", "product")
        self.assertEqual(evidence["original"], "limon tahiti")
        self.assertEqual(evidence["normalized"], "Limón Tahití")
        self.assertEqual(evidence["version"], labels.VERSION)
        self.assertEqual(evidence["dictionary_sha256"], labels.LEXICON_SHA256)
        for domain, names in labels.LEXICON["domains"].items():
            for value in names:
                self.assertEqual(labels.normalize(labels.normalize(value, domain), domain), value)
        with self.assertRaises(ValueError):
            labels.normalize("x", "brand")

    def test_identity_changing_hygiene_is_not_published_as_a_rename(self):
        literal = "Papa negra"
        # A future bad dictionary rule must not turn spacing cleanup into a
        # product-ID rename. Real current dictionary rules preserve the slug.
        with patch.object(labels, "normalize", return_value="Papanegra"):
            self.assertNotEqual(worker.slug(literal), worker.slug(labels.normalize(literal)))
            self.assertEqual(labels.product_label(literal), literal)

    def test_lexicon_and_service_are_in_exact_deployable_runtime(self):
        self.assertIn("shared/label-normalization.json", worker.RELEASE_FILES)
        self.assertIn("pipelines/ingestion/label_normalization.py", worker.RELEASE_FILES)
        self.assertEqual(worker.release_path("shared/label-normalization.json").read_bytes(), labels.LEXICON_BYTES)
        run_source = Path(worker.__file__).read_text()
        self.assertIn('summary["label_normalization"] = normalize_labels(', run_source)
        self.assertIn('summary["label_normalization_after_publication"] = normalize_labels(', run_source)


class LabelPublicationPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = Path(tempfile.mkdtemp(prefix="agro-label-cleanup-pg-", dir="/tmp"))
        cls.cluster = cls.directory / "data"
        cls.port = random.randrange(41000, 49000)
        try:
            subprocess.run(["initdb", "-D", str(cls.cluster), "--auth=trust", "--no-locale", "--encoding=UTF8"], check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["pg_ctl", "-D", str(cls.cluster), "-l", str(cls.directory / "postgres.log"),
                            "-o", f'-k {cls.directory} -p {cls.port} -h ""', "-w", "start"], check=True, stdout=subprocess.DEVNULL)
            cls.db = psycopg.connect(f"host={cls.directory} port={cls.port} dbname=postgres user={getpass.getuser()}", autocommit=True)
            cls.db.execute("CREATE ROLE agro_ingestor; CREATE ROLE agro_reader")
            cls.db.execute("CREATE TABLE product(id text PRIMARY KEY,name text NOT NULL,category text NOT NULL)")
            cls.db.execute("CREATE TABLE source_document(id text PRIMARY KEY,retrieved_at timestamptz DEFAULT now())")
            cls.db.execute("CREATE TABLE market(id text PRIMARY KEY,name text,city text,region text)")
            cls.db.execute("""CREATE TABLE price_observation(product_id text,market_id text,source_id text,
                observed_on date,period text,unit text,price numeric,source_url text,document_id text,
                source_locator text,PRIMARY KEY(product_id,market_id,source_id,observed_on,period,unit))""")
            cls.db.execute("CREATE TABLE historical_price(document_id text,source_locator text,product_name text,price numeric)")
            migration = Path(__file__).parent / "migrations/20261004_053_label_normalization.sql"
            cls.db.execute(migration.read_text())
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "db", None) is not None:
            cls.db.close()
        if getattr(cls, "cluster", None) is not None and cls.cluster.exists():
            subprocess.run(["pg_ctl", "-D", str(cls.cluster), "-m", "fast", "-w", "stop"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if getattr(cls, "directory", None) is not None:
            shutil.rmtree(cls.directory, ignore_errors=True)

    def setUp(self):
        self.db.execute("BEGIN")

    def tearDown(self):
        self.db.execute("ROLLBACK")

    def test_existing_labels_cleaned_without_touching_prices_ids_or_raw_history(self):
        self.db.execute("INSERT INTO product VALUES('limon-tahiti','limon tahiti','FRUTAS > Citricos'),('papa-r-12-roja','Papa R-12 roja','Tubérculos y plátanos')")
        self.db.execute("INSERT INTO historical_price VALUES('original','A5','limon tahiti',1234.567)")
        result = labels.drain(self.db)
        self.assertEqual((result["scanned"], result["changed"], result["cycle_complete"]), (2, 1, True))
        self.assertEqual(self.db.execute("SELECT name,category FROM product WHERE id='limon-tahiti'").fetchone(), ("Limón Tahití", "Frutas > Cítricos"))
        self.assertEqual(self.db.execute("SELECT * FROM historical_price").fetchone(),
                         ("original", "A5", "limon tahiti", Decimal('1234.567')))
        evidence = self.db.execute("SELECT field,original_value,normalized_value,evidence FROM published_label_correction ORDER BY field").fetchall()
        self.assertEqual(len(evidence), 2)
        self.assertTrue(all(r[3]["dictionary_sha256"] == labels.LEXICON_SHA256 for r in evidence))
        again = labels.drain(self.db)
        self.assertEqual(again["changed"], 0)
        self.assertEqual(self.db.execute("SELECT count(*) FROM published_label_correction").fetchone()[0], 2)

    def test_category_separator_hygiene_keeps_original_bytes_and_quote_price(self):
        originals = {
            "nbsp": "FRUTAS\u00a0>\u00a0CITRICOS",
            "tab": "FRUTAS\t>\tCITRICOS",
            "newline": "FRUTAS\n>\nCITRICOS",
            "unknown": "FRUTAS\u00a0>\tSubgrupo R-12",
        }
        for ident, raw in originals.items():
            self.db.execute("INSERT INTO product VALUES(%s,%s,%s)", (ident, "Limón Tahití", raw))
        self.db.execute("INSERT INTO historical_price VALUES('native-sha','sheet!A5','limon tahiti',1234.567)")
        self.db.execute("INSERT INTO price_observation VALUES('nbsp','market-raw','dane','2020-01-31','monthly','kg',1234.567,'https://dane.gov.co/source.xlsx','native-sha','sheet!A5')")
        quote_before = self.db.execute("SELECT * FROM price_observation").fetchone()
        result = labels.drain(self.db)
        self.assertEqual((result["scanned"], result["changed"], result["cycle_complete"]), (4, 4, True))
        for ident, raw in originals.items():
            expected = "Frutas > Subgrupo R-12" if ident == "unknown" else "Frutas > Cítricos"
            self.assertEqual(self.db.execute("SELECT category FROM product WHERE id=%s", (ident,)).fetchone()[0], expected)
            evidence = self.db.execute("SELECT original_value,normalized_value,evidence FROM published_label_correction WHERE entity_id=%s AND field='category'", (ident,)).fetchone()
            self.assertEqual(evidence[0].encode("utf-8"), raw.encode("utf-8"))
            self.assertEqual(evidence[1], expected)
            self.assertEqual(evidence[2]["method"], "exact-reviewed-label")
        self.assertEqual(self.db.execute("SELECT * FROM price_observation").fetchone(), quote_before)
        self.assertEqual(self.db.execute("SELECT * FROM historical_price").fetchone(), ("native-sha", "sheet!A5", "limon tahiti", Decimal("1234.567")))
        self.assertEqual(labels.drain(self.db)["changed"], 0)
        self.assertEqual(self.db.execute("SELECT count(*) FROM published_label_correction").fetchone()[0], 4)

    def test_rule_upgrade_preserves_old_audit_and_reprocesses_old_cursor(self):
        old_version = labels.LEXICON["version"] + ":" + labels.LEXICON_SHA256[:16]
        self.assertEqual(labels.VERSION, old_version + ":rules-v2")
        raw = "FRUTAS\u00a0>\u00a0CITRICOS"
        intermediate = "FRUTAS > CITRICOS"
        self.db.execute("INSERT INTO product VALUES('raw','Limón Tahití',%s),('intermediate','Limón Tahití',%s)", (raw, intermediate))
        self.db.execute("INSERT INTO published_label_correction(version,entity,entity_id,field,original_value,normalized_value,evidence) VALUES(%s,'product','raw','category',%s,%s,%s)",
                        (old_version, raw, intermediate, psycopg.types.json.Jsonb({"version": old_version, "original": raw, "normalized": intermediate, "method": "unicode-whitespace"})))
        self.db.execute("INSERT INTO published_label_scan(version,entity,after_id) VALUES(%s,'product','raw')", (old_version,))
        self.db.execute("INSERT INTO historical_price VALUES('original-sha','sheet!A5','limon tahiti',1234.567)")
        self.db.execute("INSERT INTO price_observation VALUES('raw','market-raw','dane','2020-01-31','monthly','kg',1234.567,'https://dane.gov.co/source.xlsx','original-sha','sheet!A5')")
        quote_before = self.db.execute("SELECT * FROM price_observation").fetchone()
        result = labels.drain(self.db)
        self.assertEqual((result["scanned"], result["changed"], result["cycle_complete"]), (2, 2, True))
        self.assertEqual(self.db.execute("SELECT category FROM product ORDER BY id").fetchall(),
                         [("Frutas > Cítricos",), ("Frutas > Cítricos",)])
        old = self.db.execute("SELECT original_value,normalized_value,evidence FROM published_label_correction WHERE version=%s", (old_version,)).fetchone()
        self.assertEqual(old[0].encode("utf-8"), raw.encode("utf-8"))
        self.assertEqual(old[1], intermediate)
        self.assertEqual(old[2]["method"], "unicode-whitespace")
        current = self.db.execute("SELECT entity_id,original_value,normalized_value,evidence FROM published_label_correction WHERE version=%s ORDER BY entity_id", (labels.VERSION,)).fetchall()
        self.assertEqual([(r[0], r[1], r[2]) for r in current],
                         [("intermediate", intermediate, "Frutas > Cítricos"), ("raw", raw, "Frutas > Cítricos")])
        self.assertTrue(all(r[3]["method"] == "exact-reviewed-label" for r in current))
        self.assertEqual(self.db.execute("SELECT after_id FROM published_label_scan WHERE version=%s", (old_version,)).fetchone()[0], "raw")
        self.assertEqual(self.db.execute("SELECT * FROM price_observation").fetchone(), quote_before)
        self.assertEqual(self.db.execute("SELECT * FROM historical_price").fetchone(), ("original-sha", "sheet!A5", "limon tahiti", Decimal("1234.567")))
        self.assertEqual(labels.drain(self.db)["changed"], 0)
        self.assertEqual(self.db.execute("SELECT count(*) FROM published_label_correction").fetchone()[0], 3)

    def test_keyset_resume_restarts_for_new_labels_at_earlier_ids(self):
        self.db.execute("INSERT INTO product VALUES('b','limon tahiti','Frutas'),('c','MARACUYA','Frutas')")
        self.assertEqual(labels.drain(self.db, limit=1)["changed"], 1)
        self.assertEqual(self.db.execute("SELECT after_id FROM published_label_scan").fetchone()[0], "b")
        self.db.execute("INSERT INTO product VALUES('a','BROCOLI','Verduras y hortalizas')")
        self.assertEqual(labels.drain(self.db, limit=1)["changed"], 1)
        self.assertTrue(labels.drain(self.db, limit=1)["cycle_complete"])
        self.assertEqual(labels.drain(self.db, limit=1)["changed"], 1)
        self.assertEqual(self.db.execute("SELECT name FROM product WHERE id='a'").fetchone()[0], "Brócoli")

    def test_failure_rolls_back_audit_label_and_cursor_together(self):
        self.db.execute("INSERT INTO product VALUES('a','MARACUYA','Frutas'),('b','BROCOLI','Verduras y hortalizas')")
        original = labels.product_label
        def fail_second(value):
            if value == "BROCOLI":
                raise ValueError("Injected second-row failure")
            return original(value)
        with patch.object(labels, "product_label", side_effect=fail_second):
            with self.assertRaisesRegex(ValueError, "second-row"):
                labels.drain(self.db)
        self.assertEqual(self.db.execute("SELECT name FROM product WHERE id='a'").fetchone()[0], "MARACUYA")
        self.assertEqual(self.db.execute("SELECT count(*) FROM published_label_correction").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT count(*) FROM published_label_scan").fetchone()[0], 0)
        self.assertEqual(labels.drain(self.db)["changed"], 2)

    def test_cienaga_metadata_cleanup_does_not_merge_products_or_change_prices(self):
        self.db.execute("INSERT INTO product VALUES"
                        "('limon-comun-de-cienaga','Limon comun de Cienaga','Frutas'),"
                        "('limon-comun-cienaga','Limón común Ciénaga','Frutas')")
        self.db.execute("INSERT INTO historical_price VALUES"
                        "('48218354878fcdbce40a6d321be20821ae64568bddd41e4540c759ea767d1b2e',"
                        "'PDF page 1,table 1,row 13,round 1','Limon comun de Cienaga',355000)")
        self.db.execute("INSERT INTO price_observation VALUES"
                        "('limon-comun-de-cienaga','barranquillita','dane','2022-01-05',"
                        "'city','50 Kilogramo',357500,'https://www.dane.gov.co/source.zip',"
                        "'48218354878fcdbce40a6d321be20821ae64568bddd41e4540c759ea767d1b2e',"
                        "'PDF page 1,table 1,row 13,round 1')")
        source_before = self.db.execute("SELECT * FROM historical_price").fetchall()
        price_before = self.db.execute("SELECT * FROM price_observation").fetchall()
        self.assertEqual(labels.drain(self.db)["changed"], 1)
        self.assertEqual(self.db.execute("SELECT id,name FROM product ORDER BY id").fetchall(),
                         [("limon-comun-cienaga", "Limón común Ciénaga"),
                          ("limon-comun-de-cienaga", "Limón común de Ciénaga")])
        self.assertEqual(self.db.execute("SELECT * FROM historical_price").fetchall(), source_before)
        self.assertEqual(self.db.execute("SELECT * FROM price_observation").fetchall(), price_before)
        self.assertEqual(self.db.execute(
            "SELECT entity_id,field,original_value,normalized_value "
            "FROM published_label_correction").fetchall(),
            [("limon-comun-de-cienaga", "name", "Limon comun de Cienaga", "Limón común de Ciénaga")])
        self.assertEqual(labels.drain(self.db)["changed"], 0)

    def test_new_monthly_source_publishes_clean_label_and_retains_original_identity(self):
        self.db.execute("INSERT INTO source_document(id) VALUES('original')")
        self.db.execute("INSERT INTO historical_price VALUES('original','sheet!A5','limon tahiti',1234.567)")
        row = ("sheet!A5", "dane-monthly", date(2020, 1, 31), "limon tahiti", "Bogotá, Corabastos", "kg", 1234.567, None, {"category":"Frutas"})
        self.assertEqual(worker.project(self.db, "original", "https://www.dane.gov.co/source.xlsx", "monthly", source_rows=[row]), 0)
        self.assertEqual(self.db.execute("SELECT id,name FROM product").fetchone(), ("limon-tahiti", "Limón Tahití"))
        self.assertEqual(self.db.execute("SELECT product_id,market_id,observed_on,unit,price,document_id,source_locator FROM price_observation").fetchone(),
                         ("limon-tahiti", "sipsa-bogota-corabastos", date(2020,1,31), "kg", Decimal('1234.567'), "original", "sheet!A5"))
        self.assertEqual(self.db.execute("SELECT product_name FROM historical_price").fetchone()[0], "limon tahiti")

    def test_deadline_and_unknown_names_are_not_claimed_cleaned(self):
        self.db.execute("INSERT INTO product VALUES('x','Pepinocohombro','unknown > category')")
        self.assertTrue(labels.drain(self.db, deadline=time.monotonic()-1)["deferred"])
        self.assertEqual(labels.drain(self.db)["changed"], 0)
        self.assertEqual(self.db.execute("SELECT name FROM product").fetchone()[0], "Pepinocohombro")

    def test_writer_cannot_rewrite_or_delete_correction_evidence(self):
        for privilege in ("UPDATE", "DELETE", "TRUNCATE"):
            self.assertFalse(self.db.execute("SELECT has_table_privilege('agro_ingestor',"
                "'published_label_correction',%s)", (privilege,)).fetchone()[0])
        self.assertTrue(self.db.execute("SELECT has_table_privilege('agro_ingestor',"
            "'published_label_correction','INSERT')").fetchone()[0])

    def test_committed_pages_survive_a_later_batch_failure(self):
        # Use real autocommit and a separate observer, not SAVEPOINT-only
        # evidence, to verify a bounded scan actually survives interruption.
        self.db.execute("ROLLBACK")
        try:
            with self.db.cursor() as cur:
                cur.executemany("INSERT INTO product VALUES(%s,%s,'Frutas')",
                    [(f"{i:03d}", "MARACUYA" if i < 64 else "BROCOLI") for i in range(65)])
            original = labels.product_label
            def fail_last(value):
                if value == "BROCOLI":
                    raise ValueError("Injected later batch failure")
                return original(value)
            with patch.object(labels, "product_label", side_effect=fail_last):
                with self.assertRaisesRegex(ValueError, "later batch"):
                    labels.drain(self.db)
            with psycopg.connect(self.db.info.dsn, autocommit=True) as observer:
                self.assertEqual(observer.execute("SELECT count(*) FROM product WHERE name='Maracuyá'").fetchone()[0], 64)
                self.assertEqual(observer.execute("SELECT after_id FROM published_label_scan").fetchone()[0], "063")
                self.assertEqual(observer.execute("SELECT count(*) FROM published_label_correction").fetchone()[0], 64)
            self.assertEqual(labels.drain(self.db)["changed"], 1)
            self.assertEqual(self.db.execute("SELECT name FROM product WHERE id='064'").fetchone()[0], "Brócoli")
        finally:
            self.db.execute("TRUNCATE product,published_label_correction,published_label_scan")
            self.db.execute("BEGIN")
