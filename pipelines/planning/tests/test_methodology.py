import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from pypdf import PdfReader

from pipelines.planning import methodology


class MethodologyTests(unittest.TestCase):
    def test_pdf_explains_current_chart_and_preserves_units(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = methodology.render(Path(tmp) / "method.pdf")
            reader = PdfReader(path)
            text = " ".join(" ".join(p.extract_text().split()) for p in reader.pages)
        self.assertEqual(len(reader.pages), 2)
        for phrase in [
            "promedio de sus 12 precios mensuales",
            "multiplica por 100",
            "mediana de los índices",
            "al menos 3 años completos",
            "no multiplica los índices",
            "no calcula precios futuros",
            "no ajusta por inflación",
            "COP nominales por kilogramo",
            "125 kg",
            "no ofrece calculadoras manuales",
            "SHA-256",
        ]:
            self.assertIn(phrase, text)
        for removed in ["percentiles 25", "Cosecha vendible =", "Saldo =", "±20"]:
            self.assertNotIn(removed, text)

    def test_render_reproducible_for_immutable_source_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = methodology.render(Path(tmp) / "a.pdf").read_bytes()
            b = methodology.render(Path(tmp) / "b.pdf").read_bytes()
        self.assertEqual(a, b)

    def test_publication_keeps_prior_document_and_retains_alias_revision(self):
        old = "a" * 64
        cur = Mock()
        cur.execute.return_value.fetchone.return_value = (old,)
        with tempfile.TemporaryDirectory() as tmp:
            path = methodology.render(Path(tmp) / "method.pdf")
            expected = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(methodology.publish(cur, path), expected)
        calls = cur.execute.call_args_list
        self.assertEqual(len(calls), 4)
        inserted = calls[1].args[1]
        self.assertEqual(inserted[5], "methodology")
        self.assertEqual(inserted[9].obj["parents"], [old])
        self.assertEqual(calls[2].args[1][1].obj["document_id"], old)
        self.assertEqual(calls[2].args[1][1].obj["replacement_document_id"], expected)
        sql = " ".join(c.args[0].upper() for c in calls)
        self.assertNotIn("DELETE", sql)
        self.assertNotIn("UPDATE SOURCE_DOCUMENT", sql)
        cur.reset_mock()
        cur.execute.return_value.fetchone.return_value = (expected,)
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(
                methodology.publish(cur, methodology.render(Path(tmp) / "m.pdf")),
                expected,
            )
        self.assertEqual(len(cur.execute.call_args_list), 3)


if __name__ == "__main__":
    unittest.main()
