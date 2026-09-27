"""All 12 formerly unclassified links retain context, with no invented dates."""

import unittest
from unittest.mock import patch

from .dane_context import is_context_source, queue_context_sources

ROOT = "https://www.dane.gov.co/files/operaciones/SIPSA/"


class ContextDiscovery(unittest.TestCase):
    def test_all_current_reference_families_are_queued_once_without_periods(self):
        names = [
            "Acerca-de-SIPSA-mensual.pdf",
            *[
                f"Inf-MonitoreoMesaTecnicaNacionalComprasPublicas-{quarter}trim{year}.pdf"
                for year, quarters in [
                    (2025, ["I", "II", "III", "IV"]),
                    (2026, ["I", "II"]),
                ]
                for quarter in quarters
            ],
            "informe-especial-SIPSA-comportamiento-precios-mayoristas-abastecimiento-2021-mayo-01a28.pdf",
            "cp_sipsa_jun_2012.pdf",
            "presentacion_sipsa_jun_2012.pdf",
            "Nota-tecnica-certificacion-SIPSA-abastecimiento.pdf",
            "cp_mensual_abr_20133.pdf",
        ]
        entries = [("Reference", ROOT + name) for name in names]
        with patch("pipelines.ingestion.worker.queue") as queue:
            self.assertEqual(queue_context_sources(None, entries + entries), 12)
        self.assertEqual(queue.call_count, 12)
        self.assertTrue(
            all(call.args[2:] == ("context-pdf",) for call in queue.call_args_list)
        )

    def test_regular_price_pdfs_and_untrusted_urls_cannot_be_reclassified(self):
        for url in [
            ROOT + "bol-SIPSAMensual-jul2026.pdf",
            ROOT + "bol-SIPSADiario-25sep2026.pdf",
            ROOT + "bol-SIPSA-Ins-ago2026.pdf",
            ROOT + "../../secret.pdf",
            "https://evil.test/files/Acerca-de-SIPSA-mensual.pdf",
            "https://www.dane.gov.co@evil.test/files/Acerca-de-SIPSA-mensual.pdf",
            "http://www.dane.gov.co/files/Acerca-de-SIPSA-mensual.pdf",
        ]:
            self.assertFalse(is_context_source(url), url)


if __name__ == "__main__":
    unittest.main()
