"""Article identity, immutable correction and idempotent publication checks."""
import os
from pathlib import Path
import unittest

import psycopg

try:
    from .guidance import ICA_URL, ICA_ALIAS, ICA_TITLE, MISIDENTIFIED_EXTRACT_ID, publish_ica, verified_ica_text
except ImportError:
    from guidance import ICA_URL, ICA_ALIAS, ICA_TITLE, MISIDENTIFIED_EXTRACT_ID, publish_ica, verified_ica_text


ARTICLE = f"""<main><article><span>03 de septiembre de 2026</span><h2>{ICA_TITLE}</h2>
<p>Santander, 3 de septiembre de 2026.</p>
<p>Durante la presente vigencia, con corte a julio de 2026, el ICA desarrolló
cinco talleres de comunicación del riesgo fitosanitario. Participaron 65 productores.</p>
<p>Como parte de las acciones de vigilancia, a julio de 2026 se realizaron 52 visitas iniciales.</p>
<p>Producto de las actividades de campo, se registraron seis brotes de broca.</p>
</article><aside>Other stories must not become evidence.</aside></main>""".encode()


class GuidanceIdentity(unittest.TestCase):
    def test_verified_article_contains_source_scope_and_no_sidebar(self):
        text = verified_ica_text(ARTICLE)
        self.assertIn("seis brotes de broca", text)
        self.assertNotIn("Other stories", text)

    def test_wrong_potato_article_cannot_borrow_sidebar_coffee_claims(self):
        wrong = ARTICLE.replace(ICA_TITLE.encode(), b"Vigilancia del cultivo de papa en Berlin")
        wrong += b"<aside>" + ARTICLE + b"</aside>"
        # A second coffee article embedded outside the main article must not validate.
        with self.assertRaises(ValueError):
            verified_ica_text(wrong.replace(b"<aside>", b"<nav>").replace(b"</aside>", b"</nav>"))

    def test_exact_report_period_and_claims_required(self):
        for altered in (ARTICLE.replace(b"2026", b"2025"),
                        ARTICLE.replace(b"seis brotes", b"siete brotes"),
                        ARTICLE.replace(b"65 productores", b"64 productores"),
                        ARTICLE.replace(b"<article>", b"<section>").replace(b"</article>", b"</section>")):
            with self.subTest(altered=altered), self.assertRaises(ValueError):
                verified_ica_text(altered)

    def test_ambiguous_duplicate_articles_and_wrong_url_rejected(self):
        with self.assertRaises(ValueError):
            verified_ica_text(ARTICLE + ARTICLE)
        with self.assertRaises(ValueError):
            verified_ica_text(ARTICLE, "https://www.ica.gov.co/noticias/el-ica-fortalece-la-vigilancia-fitosanitaria-del-c")

    @unittest.skipUnless(os.environ.get("GUIDANCE_SOURCE_FIXTURES"), "actual downloaded articles are opt-in")
    def test_actual_replacement_accepts_and_wrong_retained_article_rejects(self):
        path = Path(os.environ["GUIDANCE_SOURCE_FIXTURES"])
        self.assertIn("seis brotes de broca", verified_ica_text((path/'ICA-correct.html').read_bytes()))
        with self.assertRaises(ValueError):
            verified_ica_text((path/'ICA.html').read_bytes())


@unittest.skipUnless(os.environ.get("GUIDANCE_TEST_PG"), "isolated local PostgreSQL only")
class GuidancePublication(unittest.TestCase):
    def setUp(self):
        self.db = psycopg.connect(os.environ["GUIDANCE_TEST_PG"], autocommit=True)
        self.addCleanup(self.db.close)
        self.db.execute("CREATE TEMP TABLE source_document(id text PRIMARY KEY,title text,publisher text,source_url text,media_type text,kind text,reference_period text,content bytea,metadata jsonb)")
        self.db.execute("CREATE TEMP TABLE document_alias(alias text PRIMARY KEY,document_id text)")
        self.db.execute("CREATE TEMP TABLE advisory(id text PRIMARY KEY,title text,summary text,action text,crops jsonb,departments jsonb,published_on date,valid_until date,kind text,document_id text,source_page integer,source_url text)")
        self.db.execute("CREATE TEMP TABLE retained_record(table_name text,fingerprint text,record jsonb,PRIMARY KEY(table_name,fingerprint))")
        self.db.execute("CREATE TEMP TABLE official_source_review(document_id text,source_locator text,parser_version text,record jsonb,reason text,PRIMARY KEY(document_id,source_locator,parser_version))")
        self.db.execute("SET search_path=pg_temp")
        self.db.execute("INSERT INTO source_document(id,title,source_url,content,metadata) VALUES ('6c6ba3d7172a16b3afbfb8e1e2a65a2074e0e4e22144f84f20016b88b5da2a28','Wrong coffee title','old-url','potato article','{}')")
        self.db.execute("INSERT INTO document_alias VALUES (%s,'6c6ba3d7172a16b3afbfb8e1e2a65a2074e0e4e22144f84f20016b88b5da2a28')", (ICA_ALIAS,))
        self.db.execute("INSERT INTO advisory(id,summary,document_id,source_url) VALUES (%s,'old coffee claim','6c6ba3d7172a16b3afbfb8e1e2a65a2074e0e4e22144f84f20016b88b5da2a28','old-url')", (ICA_ALIAS,))

    def test_correction_retains_old_evidence_and_replay_does_not_rewrite(self):
        before = self.db.execute("SELECT to_jsonb(d) FROM source_document d WHERE id='6c6ba3d7172a16b3afbfb8e1e2a65a2074e0e4e22144f84f20016b88b5da2a28'").fetchone()[0]
        with self.db.cursor() as cur:
            result = publish_ica(cur, ARTICLE)
        self.assertEqual(self.db.execute("SELECT to_jsonb(d) FROM source_document d WHERE id='6c6ba3d7172a16b3afbfb8e1e2a65a2074e0e4e22144f84f20016b88b5da2a28'").fetchone()[0], before)
        self.assertEqual(self.db.execute("SELECT count(*) FROM source_document").fetchone()[0], 3)
        self.assertEqual(self.db.execute("SELECT document_id FROM document_alias").fetchone()[0], result['extract_id'])
        self.assertEqual(self.db.execute("SELECT source_url FROM advisory").fetchone()[0], ICA_URL)
        self.assertEqual(self.db.execute("SELECT document_id FROM official_source_review").fetchone()[0], '6c6ba3d7172a16b3afbfb8e1e2a65a2074e0e4e22144f84f20016b88b5da2a28')
        self.assertEqual(self.db.execute("SELECT count(*) FROM retained_record WHERE table_name='advisory'").fetchone()[0], 2)
        before_replay = self.db.execute("SELECT xmin::text FROM advisory").fetchone()[0]
        with self.db.cursor() as cur:
            self.assertEqual(publish_ica(cur, ARTICLE), result)
        self.assertEqual(self.db.execute("SELECT xmin::text FROM advisory").fetchone()[0], before_replay)
        self.assertEqual(self.db.execute("SELECT count(*) FROM retained_record").fetchone()[0], 4)

    def test_invalid_article_never_writes_and_outer_rollback_is_preserved(self):
        with self.db.cursor() as cur, self.assertRaises(ValueError):
            publish_ica(cur, ARTICLE.replace(b"seis brotes", b"siete brotes"))
        self.assertEqual(self.db.execute("SELECT count(*) FROM retained_record").fetchone()[0], 0)
        with self.assertRaisesRegex(RuntimeError, "caller rollback"):
            with self.db.transaction():
                with self.db.cursor() as cur:
                    publish_ica(cur, ARTICLE)
                raise RuntimeError("caller rollback")
        self.assertEqual(self.db.execute("SELECT count(*) FROM source_document").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT document_id FROM document_alias").fetchone()[0], '6c6ba3d7172a16b3afbfb8e1e2a65a2074e0e4e22144f84f20016b88b5da2a28')
        self.assertEqual(self.db.execute("SELECT count(*) FROM official_source_review").fetchone()[0], 0)

    def test_unrelated_prior_revision_is_not_falsely_reviewed_as_potato(self):
        self.db.execute("UPDATE document_alias SET document_id='another-valid-revision'")
        with self.db.cursor() as cur:
            publish_ica(cur, ARTICLE)
        self.assertEqual(self.db.execute("SELECT count(*) FROM official_source_review").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT count(*) FROM retained_record WHERE record->>'document_id'='another-valid-revision'").fetchone()[0], 1)


if __name__ == '__main__':
    unittest.main()
