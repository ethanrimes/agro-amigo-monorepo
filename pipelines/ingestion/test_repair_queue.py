"""Bounded source-version repair lane; opt-in PostgreSQL writes use TEMP only."""

import hashlib
import os
import unittest
from pathlib import Path

from psycopg.types.json import Jsonb

from . import queue_plan, worker
from .reviewed_wuxal_apr2015 import URL as WUXAL_URL, VERSION as WUXAL_VERSION
from .reviewed_quindio_sep2014 import (
    URL as SEPT2014_URL, SHA256 as SEPT2014_SHA, VERSION as SEPT2014_VERSION,
    retained_exact_quindio_pdf,
)

FIXTURES = Path(__file__).parent / "testdata"
ORIGINALS = {
    "milk-pdf": ("milk_nov2024_meta_narino_duplicate_original.pdf", "7bdeb21148f0ae14ef55259f30cd7f4806689bd67a149e4ccff59de226057343"),
    "input-april": ("6cba3d6b39f1-Bol_Insumos_abr_2016.pdf", "6cba3d6b39f171d2ae0f6e13b8afb7ab468e6dc4d2d807febc1f2a1c2731b2fc"),
    "input-february": ("cb2289b8dad52378bc04a9787c7560a93a1feccfd47c64a41e010a33a499f5ab.pdf", "cb2289b8dad52378bc04a9787c7560a93a1feccfd47c64a41e010a33a499f5ab"),
    "daily": ("bbb69b2938848e95c9728a34c9204dd9fb19e720d54b05dd2f9b8289079a0f0f.xls", "bbb69b2938848e95c9728a34c9204dd9fb19e720d54b05dd2f9b8289079a0f0f"),
    "pork": ("3b9009dd742d30db945636b203a20729df4d7aec19b5ffad64173f6cdba62084.pdf", "3b9009dd742d30db945636b203a20729df4d7aec19b5ffad64173f6cdba62084"),
}


def pinned_original(label):
    expected_sha = ORIGINALS[label][1]
    matching = [row for row in queue_plan.PRIORITY_SOURCE_REPAIRS if row[2] == expected_sha]
    if len(matching) != 1:
        raise AssertionError(f"Exactly one audited priority source is required for {label}")
    return matching[0]


class SourceRepairVersionTests(unittest.TestCase):
    def test_only_audited_original_urls_receive_source_specific_asset_versions(self):
        for url, kind, _ in queue_plan.PRIORITY_SOURCE_REPAIRS:
            with self.subTest(url=url):
                expected = worker.asset_parser_version(kind, url)
                if expected != worker.parser_version(kind):
                    self.assertNotEqual(expected, worker.parser_version(kind))
                    self.assertEqual(queue_plan.expected_versions().obj["url:" + url], expected)
                else:
                    self.assertEqual(expected, worker.parser_version(kind))
                    self.assertNotIn("url:" + url, queue_plan.expected_versions().obj)
        self.assertEqual(
            worker.asset_parser_version("colombia-pork-pdf", "https://porkcolombia.co/unrelated.pdf"),
            worker.parser_version("colombia-pork-pdf"),
        )
        armenia = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/sipsa-11-01-2022.zip"
        self.assertEqual(worker.asset_parser_version("city-zip", armenia),
                         "city-v8:jan2022-native-geometry-v1")
        self.assertEqual(queue_plan.expected_versions().obj["url:" + armenia],
                         "city-v8:jan2022-native-geometry-v1")
        self.assertIn((armenia, "city-zip", "343f20fb88142be933f1fbc537257f427d40aecd6f59fdb69589b5c05da1c6ed"),
                      queue_plan.PRIORITY_SOURCE_REPAIRS)
        self.assertEqual(worker.asset_parser_version("city-zip", armenia + "?different-revision"),
                         worker.parser_version("city-zip"))
        self.assertEqual(worker.asset_parser_version("daily", armenia), worker.parser_version("daily"))
        self.assertEqual(worker.asset_parser_version("inputs-pdf", WUXAL_URL), WUXAL_VERSION)
        self.assertEqual(queue_plan.expected_versions().obj["url:" + WUXAL_URL], WUXAL_VERSION)
        self.assertEqual(worker.asset_parser_version("inputs-pdf", WUXAL_URL + "?changed"),
                         worker.parser_version("inputs-pdf"))
        self.assertEqual(worker.asset_parser_version("daily-pdf", WUXAL_URL),
                         worker.parser_version("daily-pdf"))
        self.assertEqual(worker.asset_parser_version("inputs-pdf", SEPT2014_URL), SEPT2014_VERSION)
        self.assertEqual(queue_plan.expected_versions().obj["url:" + SEPT2014_URL], SEPT2014_VERSION)
        self.assertEqual(worker.asset_parser_version("inputs-pdf", SEPT2014_URL + "?different"),
                         worker.parser_version("inputs-pdf"))
        self.assertEqual(worker.asset_parser_version("daily-pdf", SEPT2014_URL),
                         worker.parser_version("daily-pdf"))

    def test_nov16_city_revision_is_exact_and_appended_after_existing_priority_pins(self):
        url = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/sipsa-16-11-2021.zip"
        did = "e4a8aa221892eb1d7eebb80e23e6d5419d406b87fa4243f205ee1f32b1fa8d10"
        repairs = queue_plan.PRIORITY_SOURCE_REPAIRS
        nov16_index = repairs.index((url, "city-zip", did))
        jan2020 = tuple(row[0] for row in repairs if "/mayoristas_enero_" in row[0] and row[0].endswith("_2020.xlsx"))
        self.assertLess(nov16_index, repairs.index((jan2020[0], "daily", "73e9e87255acfdae1c851920d084f00ed90d21baf754f848c88da6112971fe72")))
        self.assertEqual(jan2020, tuple(
            f"https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_enero_{day:02d}_2020.xlsx"
            for day in (7, 8, 9, 10, 13, 14, 15, 16)
        ))
        self.assertEqual(tuple(row[0] for row in queue_plan.PRIORITY_SOURCE_REPAIRS[:4]), (
            "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_febrero_04_2020.pdf",
            "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-21ago2026.pdf",
            "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/bol_01abr_al_05abr_2023.pdf",
            "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/bol_09jul_al_15jul_2022.pdf",
        ))
        expected = queue_plan.expected_versions().obj
        self.assertEqual(expected["url:" + url],
                         "city-v8:nov2021-unit-category-exact-v1")
        neighbour = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/sipsa-17-11-2021.zip"
        self.assertNotIn("url:" + neighbour, expected)
        self.assertEqual(worker.asset_parser_version("city-zip", neighbour), "city-v8")


@unittest.skipUnless(os.environ.get("AGRO_REPAIR_QUEUE_POSTGRES_TEST") == "1",
                     "Explicit opt-in for isolated TEMP PostgreSQL source repair queue")
class SourceRepairQueuePostgresTests(unittest.TestCase):
    def setUp(self):
        self.db = worker.connect()
        self.addCleanup(self.db.close)
        self.assertTrue(self.db.info.host.startswith("/tmp/agro-"))
        self.db.execute("SET search_path=pg_temp; SET statement_timeout='30s'")
        for table in ("source_document", "ingestion_asset", "ingestion_checkpoint", "historical_price"):
            self.db.execute(f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL)")
            self.assertEqual(self.db.execute(
                "SELECT relpersistence FROM pg_class WHERE oid=to_regclass(%s)",
                (table,)).fetchone(), ("t",))

    def add_original(self, body, url, kind, status, version, *, hours=7, day="2024-11-30", archived_kind=None):
        did = hashlib.sha256(body).hexdigest()
        self.db.execute(
            "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content,metadata) "
            "VALUES(%s,'Original','Publisher',%s,'application/octet-stream','original',%s,%s,%s) "
            "ON CONFLICT DO NOTHING",
            (did, url, day, body, Jsonb({"ingestion_kind": archived_kind or kind})),
        )
        self.db.execute(
            "INSERT INTO ingestion_asset(url,kind,status,processor_version,document_id,observed_on,checked_at) "
            "VALUES(%s,%s,%s,%s,%s,%s::date,now()-(%s*interval '1 hour'))",
            (url, kind, status, version, did, day, hours),
        )
        return did

    def test_nov16_completed_checkpoint_is_selected_only_for_exact_old_original(self):
        url = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/sipsa-16-11-2021.zip"
        did = "e4a8aa221892eb1d7eebb80e23e6d5419d406b87fa4243f205ee1f32b1fa8d10"
        body = (FIXTURES / "nov16_city_unit_identity/parent.zip").read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(), did)
        generic = worker.parser_version("city-zip")
        reviewed = worker.asset_parser_version("city-zip", url)
        self.assertEqual((generic, reviewed),
                         ("city-v8", "city-v8:nov2021-unit-category-exact-v1"))

        def add_city(source_url, source_body, version, *, hours, day):
            source_id = hashlib.sha256(source_body).hexdigest()
            self.db.execute(
                "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content,metadata) "
                "VALUES(%s,%s,'DANE',%s,'application/zip','original',%s,%s,%s)",
                (source_id, "DANE - " + source_url.rsplit("/", 1)[-1], source_url,
                 day, source_body, Jsonb({"ingestion_kind": "city-zip", "retention": "permanent",
                                          "original_filename": source_url.rsplit("/", 1)[-1]})),
            )
            self.db.execute(
                "INSERT INTO ingestion_asset(url,kind,observed_on,checked_at,status,processor_version,document_id,records) "
                "VALUES(%s,'city-zip',%s::date,now()-(%s*interval '1 hour'),'complete',%s,%s,0)",
                (source_url, day, hours, version, source_id),
            )
            self.db.execute(
                "INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records) "
                "VALUES(%s,%s,'official:complete',0)", (source_id, version),
            )
            return source_id

        current_url = "https://example.invalid/current-city.zip"
        current_body = b"unrelated current original ZIP"
        stale_url = "https://example.invalid/older-city.zip"
        stale_body = b"unrelated stale original ZIP"
        current_did = add_city(current_url, current_body, generic, hours=20, day="2021-11-15")
        stale_did = add_city(stale_url, stale_body, "city-v7", hours=20, day="2021-11-14")
        add_city(url, body, generic, hours=8, day="2021-11-16")

        # Exact source pin outranks an older ordinary stale city at a one-row cap.
        selected = queue_plan.repair_candidates(self.db, 1)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0][:2], (url, "city-zip"))

        self.db.execute("UPDATE ingestion_asset SET processor_version=%s WHERE url=%s",
                        (reviewed, url))
        self.db.execute("INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records) "
                        "VALUES(%s,%s,'official:complete',0)", (did, reviewed))
        selected = queue_plan.repair_candidates(self.db, 1)
        self.assertEqual(selected[0][:2], (stale_url, "city-zip"))
        self.assertNotIn(current_url, [row[0] for row in selected])

        # With the stale v7 row removed, both city-v8 completed assets are current.
        self.db.execute("DELETE FROM ingestion_asset WHERE url=%s", (stale_url,))
        self.db.execute("DELETE FROM ingestion_checkpoint WHERE document_id=%s", (stale_did,))
        self.db.execute("DELETE FROM source_document WHERE id=%s", (stale_did,))
        self.assertEqual(queue_plan.repair_candidates(self.db, 8), [])
        self.assertEqual(self.db.execute("SELECT processor_version FROM ingestion_asset WHERE url=%s",
                                         (current_url,)).fetchone()[0], generic)

        # A changed body loses the exact pin. With an older generic stale ZIP
        # present it does not jump the FIFO lane; without that competitor the
        # changed body remains eligible through ordinary version drift because
        # its per-URL reviewed version differs from city-v8.
        self.db.execute("DELETE FROM ingestion_asset WHERE url=%s", (url,))
        self.db.execute("DELETE FROM ingestion_checkpoint WHERE document_id=%s", (did,))
        self.db.execute("DELETE FROM source_document WHERE id=%s", (did,))
        changed_body = b"changed publisher ZIP bytes"
        changed_did = hashlib.sha256(changed_body).hexdigest()
        self.assertNotEqual(changed_did, did)
        add_city(url, changed_body, generic, hours=8, day="2021-11-16")
        fallback_url = "https://example.invalid/older-generic-city.zip"
        fallback_body = b"older generic stale city ZIP"
        fallback_did = add_city(fallback_url, fallback_body, "city-v7", hours=20,
                                day="2021-11-13")
        selected = queue_plan.repair_candidates(self.db, 1)
        self.assertEqual(selected[0][:2], (fallback_url, "city-zip"))
        self.assertNotIn(url, [row[0] for row in selected])
        self.db.execute("DELETE FROM ingestion_asset WHERE url=%s", (fallback_url,))
        self.db.execute("DELETE FROM ingestion_checkpoint WHERE document_id=%s", (fallback_did,))
        self.db.execute("DELETE FROM source_document WHERE id=%s", (fallback_did,))
        selected = queue_plan.repair_candidates(self.db, 1)
        self.assertEqual(selected[0][:2], (url, "city-zip"))
        self.assertEqual(queue_plan.repair_candidates(self.db, 0), [])

    def test_crowded_backlog_reserves_exact_repair_then_advances_same_kind(self):
        with self.db.cursor() as cur:
            with cur.copy("COPY ingestion_asset(url,kind,status,processor_version) FROM STDIN") as copy:
                for number in range(2000):
                    copy.write_row((f"https://example.invalid/milk-pending-{number}",
                                    "milk-pdf", "pending", worker.parser_version("milk-pdf")))
                for number in range(120):
                    copy.write_row((f"https://example.invalid/current-root-{number}",
                                    "colombia-pork-pdf", "pending", worker.parser_version("colombia-pork-pdf")))
        urls = {}
        for label, (filename, _) in ORIGINALS.items():
            url, kind, sha = pinned_original(label)
            body = (FIXTURES / filename).read_bytes()
            self.assertEqual(hashlib.sha256(body).hexdigest(), sha)
            old_version = worker.parser_version(kind)
            if kind == "milk-pdf":
                old_version = "milk-pdf-v10:milk-macroregions-v2"
            elif kind == "inputs-pdf":
                old_version = "inputs-pdf-v13"
            did = self.add_original(body, url, kind,
                                    "failed" if kind in {"daily", "colombia-pork-pdf"} else "complete",
                                    old_version, day="2024-11-30" if kind == "milk-pdf" else "2016-04-30",
                                    archived_kind="context-pdf" if kind == "inputs-pdf" else None)
            self.assertEqual(did, sha)
            urls[label] = url
        # Recent deterministic/transport failure keeps its existing cooldown.
        self.db.execute("UPDATE ingestion_asset SET checked_at=now()-interval '1 hour' WHERE url=%s", (urls["pork"],))
        first = queue_plan.repair_candidates(self.db, 8)
        selected = [row[0] for row in first]
        self.assertEqual(len(selected), 3)
        # queue_plan explicitly prioritizes inputs-pdf within an equal-pin tie,
        # then advances one source per kind before the next cycle.
        self.assertEqual(selected[:3], [urls["input-april"], urls["milk-pdf"], urls["daily"]])
        self.assertNotIn(urls["input-february"], selected)  # one per kind
        self.assertNotIn(urls["pork"], selected)
        self.assertFalse(any("milk-pending" in row[0] or "current-root" in row[0] for row in first))
        self.db.execute("UPDATE ingestion_asset SET checked_at=now()-interval '7 hours' WHERE url=%s", (urls["pork"],))
        self.assertIn(urls["pork"], [row[0] for row in queue_plan.repair_candidates(self.db, 8)])
        self.db.execute("UPDATE ingestion_asset SET processor_version=%s WHERE url=%s",
                        (worker.asset_parser_version("inputs-pdf", urls["input-april"]), urls["input-april"]))
        self.assertIn(urls["input-february"], [row[0] for row in queue_plan.repair_candidates(self.db, 8)])
        self.assertEqual(queue_plan.repair_candidates(self.db, 0), [])

    def test_changed_original_loses_exact_priority_and_generic_lane_remains_safe(self):
        url, kind, sha = pinned_original("milk-pdf")
        body = (FIXTURES / ORIGINALS["milk-pdf"][0]).read_bytes()
        self.assertEqual(self.add_original(body, url, kind, "complete", "old-version"), sha)
        generic = "https://www.dane.gov.co/files/operaciones/SIPSA/other-old-milk.pdf"
        self.add_original(b"independent older original", generic, kind, "complete", "old-version", hours=20)
        self.assertEqual(queue_plan.repair_candidates(self.db, 8)[0][0], url)
        changed = hashlib.sha256(b"changed publisher bytes").hexdigest()
        self.db.execute("INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content,metadata) "
                        "VALUES(%s,'Changed','Publisher',%s,'application/pdf','original','2024-11',%s,%s)",
                        (changed, url, b"changed publisher bytes", Jsonb({"ingestion_kind": kind})))
        self.db.execute("UPDATE ingestion_asset SET document_id=%s WHERE url=%s", (changed, url))
        self.assertEqual(queue_plan.repair_candidates(self.db, 8)[0][0], generic)
        self.db.execute("UPDATE ingestion_asset SET processor_version=%s WHERE url=%s",
                        (worker.asset_parser_version(kind, generic), generic))
        self.assertEqual(queue_plan.repair_candidates(self.db, 8)[0][0], url)

    def test_exact_september_2014_source_respects_cooldown_and_changed_bytes(self):
        body = (FIXTURES / f"{SEPT2014_SHA}.pdf").read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(), SEPT2014_SHA)
        self.assertEqual(self.add_original(
            body, SEPT2014_URL, "inputs-pdf", "complete", "inputs-pdf-v14",
            day="2014-09-30"), SEPT2014_SHA)
        self.db.execute("UPDATE source_document SET media_type='application/pdf' WHERE id=%s",
                        (SEPT2014_SHA,))
        generic = "https://www.dane.gov.co/files/operaciones/SIPSA/other-old-input.pdf"
        self.add_original(b"independent older input PDF", generic, "inputs-pdf",
                          "complete", "old-version", hours=20)
        self.assertEqual(queue_plan.repair_candidates(self.db, 8)[0][0], SEPT2014_URL)
        self.assertEqual(retained_exact_quindio_pdf(
            self.db, SEPT2014_URL, "inputs-pdf", SEPT2014_VERSION), body)
        self.assertTrue(worker.retained_reparse_during_host_cooldown(
            self.db, SEPT2014_URL, "inputs-pdf"))
        self.db.execute("UPDATE ingestion_asset SET checked_at=now()-interval '1 hour' WHERE url=%s",
                        (SEPT2014_URL,))
        self.assertEqual(queue_plan.repair_candidates(self.db, 8)[0][0], generic)
        self.db.execute("UPDATE ingestion_asset SET checked_at=now()-interval '7 hours' WHERE url=%s",
                        (SEPT2014_URL,))
        self.assertEqual(queue_plan.repair_candidates(self.db, 8)[0][0], SEPT2014_URL)
        changed_body = b"different immutable publisher bytes"
        changed = hashlib.sha256(changed_body).hexdigest()
        self.db.execute(
            "INSERT INTO source_document(id,title,publisher,source_url,media_type,kind,reference_period,content,metadata) "
            "VALUES(%s,'Changed','DANE',%s,'application/pdf','original','2014-09',%s,%s)",
            (changed, SEPT2014_URL, changed_body, Jsonb({"ingestion_kind": "inputs-pdf"})),
        )
        self.db.execute("UPDATE ingestion_asset SET document_id=%s WHERE url=%s",
                        (changed, SEPT2014_URL))
        self.assertEqual(queue_plan.repair_candidates(self.db, 8)[0][0], generic)
        self.assertIsNone(retained_exact_quindio_pdf(
            self.db, SEPT2014_URL, "inputs-pdf", SEPT2014_VERSION))

    def test_january_2017_native_market_wrap_repair_advances_without_source_http(self):
        from .retained_pdf_upgrade import retained_pdf_upgrade

        url = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Sem_21ene_27ene_2017.pdf"
        kind = "dane-weekly-pdf"
        body = (FIXTURES / "dane_weekly_2017_01_21_original.pdf").read_bytes()
        sha = "95072bb4d5c98fbb2b2635c8aa3dd50c22b4e3ab9c40abcb441662868b5f062e"
        expected = worker.asset_parser_version(kind, url)
        self.assertEqual(expected, worker.parser_version(kind) + ":jan2017-market-wrap-v1")
        self.assertEqual(self.add_original(body, url, kind, "complete",
                                          "official-v2:dane-weekly-v21", day="2017-01-27"), sha)
        self.db.execute("UPDATE source_document SET media_type='application/pdf' WHERE id=%s", (sha,))
        older = "https://www.dane.gov.co/files/operaciones/SIPSA/other-older-weekly.pdf"
        self.add_original(b"other retained original", older, kind, "complete", "old-version", hours=20)
        self.assertEqual(queue_plan.repair_candidates(self.db, 8)[0][0], url)
        self.assertEqual(retained_pdf_upgrade(self.db, url, kind, expected), body)
        self.assertTrue(worker.retained_reparse_during_host_cooldown(self.db, url, kind))
        for column, changed in (("source_url", url + ".unverified"),
                                ("media_type", "application/octet-stream")):
            prior = self.db.execute(f"SELECT {column} FROM source_document WHERE id=%s", (sha,)).fetchone()[0]
            self.db.execute(f"UPDATE source_document SET {column}=%s WHERE id=%s", (changed, sha))
            self.assertIsNone(retained_pdf_upgrade(self.db, url, kind, expected))
            self.db.execute(f"UPDATE source_document SET {column}=%s WHERE id=%s", (prior, sha))
        self.db.execute("UPDATE ingestion_asset SET processor_version=%s WHERE url=%s", (expected, url))
        self.assertNotIn(url, [row[0] for row in queue_plan.repair_candidates(self.db, 8)])
        self.assertIsNone(retained_pdf_upgrade(self.db, url, kind, expected))
        self.db.execute("UPDATE ingestion_asset SET processor_version='old-version' WHERE url=%s", (url,))
        changed = self.add_original(b"changed weekly bytes", url + ".changed", kind, "complete", "old-version")
        self.db.execute("UPDATE ingestion_asset SET document_id=%s WHERE url=%s", (changed, url))
        self.assertEqual(queue_plan.repair_candidates(self.db, 8)[0][0], older)
        self.assertIsNone(retained_pdf_upgrade(self.db, url, kind, expected))
