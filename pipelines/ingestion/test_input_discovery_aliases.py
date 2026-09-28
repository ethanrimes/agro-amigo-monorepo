"""Dated price PDFs retain typed discovery across literal/encoded hyperlinks."""

import os
import unittest
from datetime import date
from unittest.mock import patch

from . import input_references as sources
from . import test_queue_classification as queue_tests
from . import worker

BASE = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/"


class InputLinkIdentity(unittest.TestCase):
    def test_two_actual_encoding_aliases_preserve_explicit_period(self):
        for literal, encoded, day in [
            (
                "Bol_ Insumos_ene_2019.pdf",
                "Bol_%20Insumos_ene_2019.pdf",
                date(2019, 1, 31),
            ),
            (
                "insumos_factores_de_producción_agosto_2012.pdf",
                "insumos_factores_de_producci%C3%B3n_agosto_2012.pdf",
                date(2012, 8, 31),
            ),
        ]:
            self.assertEqual(
                sources.input_url_identity(BASE + literal),
                sources.input_url_identity(BASE + encoded),
            )
            self.assertEqual(sources.input_pdf_month("", BASE + encoded), day)

    def test_unknown_external_or_reserved_path_is_not_guessed(self):
        for url in [
            BASE + "informe-insumos.pdf",
            BASE + "informe-insumos-2019.pdf",
            "https://example.com/files/Bol_Insumos_ene_2019.pdf",
        ]:
            self.assertIsNone(sources.input_pdf_month("", url))
        self.assertNotEqual(
            sources.input_url_identity(BASE + "a%2fb.pdf"),
            sources.input_url_identity(BASE + "a/b.pdf"),
        )


@unittest.skipUnless(
    os.environ.get("AGRO_QUEUE_POSTGRES_TEST") == "1",
    "Isolated local PostgreSQL opt-in",
)
class InputAliasQueue(unittest.TestCase):
    setUp = queue_tests.QueueClassificationTests.setUp

    def test_normal_discovery_restores_only_observed_encoded_price_alias(self):
        literal = BASE + "Bol_ Insumos_ene_2019.pdf"
        encoded = BASE + "Bol_%20Insumos_ene_2019.pdf"
        unknown = BASE + "Bol_Insumos_ene_1999.pdf"
        worker.queue(self.db, encoded, "context-pdf")
        worker.queue(self.db, unknown, "context-pdf")
        self.db.execute("UPDATE ingestion_asset SET status='processed',records=17")
        root = worker.INPUTS + "/componente-insumos-historicos"
        with patch.object(
            worker,
            "links",
            side_effect=[[("Archivo", root)], [("Boletín enero de 2019", literal)]],
        ):
            worker.discover_input_sources(self.db)
        self.assertEqual(
            self.db.execute(
                "SELECT kind,observed_on,status,records FROM ingestion_asset WHERE url=%s",
                (encoded,),
            ).fetchone(),
            ("inputs-pdf", date(2019, 1, 31), "processed", 17),
        )
        self.assertEqual(
            self.db.execute(
                "SELECT kind FROM ingestion_asset WHERE url=%s", (unknown,)
            ).fetchone()[0],
            "context-pdf",
        )
        # Later generic discovery cannot demote the newly typed alias again.
        worker.queue(self.db, encoded, "context-pdf")
        self.assertEqual(
            self.db.execute(
                "SELECT kind FROM ingestion_asset WHERE url=%s", (encoded,)
            ).fetchone()[0],
            "inputs-pdf",
        )

    def test_context_workbook_first_discovery_retains_rows_and_types_price_link(self):
        self.db.execute(
            "CREATE TEMP TABLE input_reference_row(document_id text,source_locator text,kind text,name text,category text,details jsonb,PRIMARY KEY(document_id,source_locator))"
        )
        priced = BASE + "Bol_%20Insumos_ene_2019.pdf"
        context = BASE + "informe-insumos-sin-fecha.pdf"
        with patch.object(
            sources,
            "context_rows",
            return_value=[("Contexto", 7, ["Repollo"], [priced, context])],
        ):
            self.assertEqual(sources.extract_context(self.db, b"", "original"), 1)
        self.assertEqual(
            self.db.execute(
                "SELECT kind,observed_on FROM ingestion_asset WHERE url=%s", (priced,)
            ).fetchone(),
            ("inputs-pdf", date(2019, 1, 31)),
        )
        self.assertEqual(
            self.db.execute(
                "SELECT kind,observed_on FROM ingestion_asset WHERE url=%s", (context,)
            ).fetchone(),
            ("context-pdf", None),
        )
        self.assertEqual(
            self.db.execute(
                "SELECT details->'links' FROM input_reference_row"
            ).fetchone()[0],
            [priced, context],
        )
