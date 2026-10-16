"""Reparse a completed PDF's exact original when its parser is upgraded.

This does not check for a newer publisher revision or alter HTTP validators.
The next ordinary same-version refresh still checks the publisher. Review and
OCR-pending documents use their separate recovery paths.
"""

import hashlib
from datetime import date


# Only these source-bound readable prose originals were previously marked
# processed with zero grid rows. A changed pointer must take the ordinary
# publisher-validation path, never inherit their paragraph bindings.
PROSE_PROCESSED_ORIGINALS = {
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/mayoristas_febrero_04_2020.pdf":
        "9d73376d4a1297c7654bb7ccb0e865c099822843f4900be2fdeec1e3cfd3bf4a",
    "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSADiario-21ago2026.pdf":
        "2b9cd5e40d5b888bd965eedf0ce3f4e347698d80713795f841aea07c7e89769f",
}

WEEKLY_COMPLETED_ORIGINALS = {
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Semana_16jun_20jun_2014.pdf": "7c05255c9634e7f9fec2d482368c69bae544c027d49b20d7c4c99f2ac64f90a9",
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Sem_08ago_14ago_2015.pdf": "3660829203a4608502a1f0656cc7fdd7fe0ac6ad7ecf3fed8cd1ffa7d4e7e777",
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Sem_29oct_04nov_2016.pdf":
        "1a6d6a31c9beda79688b41bf72443c1ec28dcd42ab724c49673736703b82c177",
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Sem_7ene_2017_13ene_2017.pdf":
        "2075ff73d374815709ea72927d5981c81823c066a01a6dc9557cefa409902440",
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Sem_02nov_2019__08nov_2019.pdf":
        "4f038cbc3d2e2c55d1b3cbf09f22782ef451225c73dded1f7e987e3a0eca2134",
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Semana4_junio_2012.pdf":
        "dd059a09eecb1fa01cadb24a4f21a7768d97d9e31684dee6a57222c536faf6a8",
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/bol_02jul_al_08jul_2022.pdf":
        "9f428bddcef7ede04ba7d91b7e39d2a89413a70f4b132d1f516f4577330c271c",
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Sem_21ene_27ene_2017.pdf":
        "95072bb4d5c98fbb2b2635c8aa3dd50c22b4e3ab9c40abcb441662868b5f062e",
    "https://www.dane.gov.co/files/operaciones/SIPSA/bol-SIPSASemanal-23mar-27mar-2024.pdf":
        "218d83958d650f3b3035e008a35828aff6a6b2a0098d8ba84adc07596a26ca7e",
}

# These two registered originals are native-readable throughout. Their old
# parser stopped before publication and left an OCR-pending asset; only their
# exact immutable bytes may bypass that obsolete OCR resume path.
WEEKLY_NATIVE_PENDING_ORIGINALS = {
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/bol_01abr_al_05abr_2023.pdf":
        "ec95dc1b92689e54b52000a621dc87bad18d54392522bce748a56ce6003688e0",
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/bol_09jul_al_15jul_2022.pdf":
        "2ab314d876e586aafd8017a50d26762a1a96cbb489a57cc45a51007d63158304",
}

AUG2013_PAGE43_URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Semana_20ago_23ago_2013.pdf"
AUG2013_PAGE43_SHA = "5a8af3b10894d3241907e149a39451d09488bf827d79b52d3789e5a8cfa60f4d"
AUG2013_PAGE43_OLD_VERSION = "official-v2:dane-weekly-v24"
AUG2013_PAGE43_COMPLETED_M_VERSION = "official-v2:aug2013-page43-grid-article-period-v1:dane-weekly-v24"
AUG2013_PAGE43_COMPLETED_P_VERSION = (
    "official-v2:aug2013-page43-grid-article-period-v1:"
    "panela-article-60cells-v1:dane-weekly-v24"
)
AUG2013_PAGE43_UNIT_SUFFIX = ":aug2013-huevo-rojo-extra-unit-p27-v1"
AUG2013_PAGE43_OLD_ERROR = "ValueError: Weekly PDF page 43 has conflicting printed periods"

JUL2022_PENDING_URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/bol_09jul_al_15jul_2022.pdf"
JUL2022_OLD_ASSET_VERSION = "official-v2:dane-weekly-v23"
JUL2022_NEW_ASSET_VERSION = "official-v2:dane-weekly-v24:native-readable-layout-v1"
JUL2022_QUOTE_VERSION = "official-v2:dane-weekly-v24"
JUL2022_PENDING_ERRORS = (
    "Official source validated; committed quote batches will resume",
    "Committed official quote batches retained; next batch deferred",
    "Committed official batches retained; next work deferred",
    "Official quote batches retained; catalog completion will resume",
)
JAN2017_PENDING_URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Sem_7ene_2017_13ene_2017.pdf"
JAN2017_NEW_VERSION = "official-v2:jan2017-market-wrap-v3:dane-weekly-v24"
JAN2017_OLD_VERSION = "official-v2:dane-weekly-v24"
NOV2016_PENDING_URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Sem_29oct_04nov_2016.pdf"
NOV2016_NEW_VERSION = "official-v2:nov2016-medellin-market-wrap-v2:dane-weekly-v24"
NOV2016_OLD_VERSIONS = (
    "official-v2:dane-weekly-v24",
    "official-v2:dane-weekly-v24:nov2016-medellin-market-wrap-v1",
)
AUG2015_PENDING_URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Sem_08ago_14ago_2015.pdf"
AUG2015_NEW_VERSION = "official-v2:aug2015-medellin-market-wrap-v1:dane-weekly-v24"
AUG2015_OLD_VERSION = "official-v2:dane-weekly-v24"
MAY2013_PENDING_URL = "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Semana_18may_24may_2013.pdf"
MAY2013_PENDING_DID = "d7bbfdb46fcba969ebcdbad7f17960b8fdc7ba1df8e376cd89883f692330cd04"
MAY2013_PENDING_OLD_VERSION = "official-v2:dane-weekly-v24"
MAY2013_PENDING_NEW_VERSION = "official-v2:may2013-white-corn-heading-v1:dane-weekly-v24"
MAY2013_PENDING_ERROR = "Official catalog refresh deferred after 256 of 4201 identities"
MAY2013_PENDING_STEP = "official:catalog-start:official-catalog-v1:2026-10-05"
WEEKLY_EXACT_PENDING = {
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/Semana_16jun_20jun_2014.pdf": (
        "7c05255c9634e7f9fec2d482368c69bae544c027d49b20d7c4c99f2ac64f90a9",
        ("official-v2:dane-weekly-v24",
         "official-v2:dane-weekly-v24:panela-article-boundary-jun2014-v1"),
        "official-v2:jun2014-panela-article-single-price-v1:dane-weekly-v24"),
    AUG2015_PENDING_URL: (WEEKLY_COMPLETED_ORIGINALS[AUG2015_PENDING_URL],
                          (AUG2015_OLD_VERSION,), AUG2015_NEW_VERSION),
    JAN2017_PENDING_URL: (WEEKLY_COMPLETED_ORIGINALS[JAN2017_PENDING_URL],
                            (JAN2017_OLD_VERSION,), JAN2017_NEW_VERSION),
    NOV2016_PENDING_URL: (WEEKLY_COMPLETED_ORIGINALS[NOV2016_PENDING_URL],
                            NOV2016_OLD_VERSIONS, NOV2016_NEW_VERSION),
}
def retained_pdf_upgrade(db, url, kind, expected_version, quote_version=None):
    """Return verified local bytes for this registered pointer, or None.

    Never recover an alias, redirect, different kind, or different source URL.
    A corrupt retained pointer is an error, not permission to fetch and replace
    its evidence. The caller rechecks immediately before ordinary publication.
    """
    if kind not in ("daily-pdf", "monthly-pdf", "dane-weekly-pdf"):
        return None
    if kind == "dane-weekly-pdf" and url not in (WEEKLY_COMPLETED_ORIGINALS | WEEKLY_NATIVE_PENDING_ORIGINALS):
        return None
    row = db.execute(
        """SELECT d.id,d.content FROM ingestion_asset a
        JOIN source_document d ON d.id=a.document_id
        WHERE a.url=%s AND a.kind=%s AND (
          (a.status='complete' AND (%s='' OR a.document_id=%s)) OR
          (a.status='processed' AND a.records=0 AND a.document_id=%s) OR
          (a.status='awaiting-ocr' AND a.records=0 AND a.document_id=%s
           AND a.processor_version='official-v2:dane-weekly-v23'))
          AND a.processor_version IS DISTINCT FROM %s
          AND d.kind='original' AND d.source_url=a.url
          AND d.media_type='application/pdf'
          AND d.metadata->>'ingestion_kind'=a.kind""",
        (url, kind,
         (WEEKLY_COMPLETED_ORIGINALS | WEEKLY_NATIVE_PENDING_ORIGINALS).get(url, ''),
         (WEEKLY_COMPLETED_ORIGINALS | WEEKLY_NATIVE_PENDING_ORIGINALS).get(url, ''),
         PROSE_PROCESSED_ORIGINALS.get(url, ''),
         WEEKLY_NATIVE_PENDING_ORIGINALS.get(url, ''), expected_version),
    ).fetchone()
    # Keep the pending continuation in a separate query. Other retained PDF
    # upgrades need not touch the official checkpoint relation at all.
    if (row is None and url == JUL2022_PENDING_URL and kind == 'dane-weekly-pdf'
            and expected_version == JUL2022_NEW_ASSET_VERSION
            and quote_version == JUL2022_QUOTE_VERSION):
        row = db.execute(
            """SELECT d.id,d.content FROM ingestion_asset a
            JOIN source_document d ON d.id=a.document_id
            WHERE a.url=%s AND a.kind='dane-weekly-pdf'
              AND a.status='pending' AND a.records=0
              AND a.document_id=%s AND a.processor_version=%s
              AND (a.error=ANY(%s::text[]) OR
                   a.error ~ '^Official catalog refresh deferred after [0-9]+ of [0-9]+ identities$')
              AND NOT EXISTS (
                SELECT 1 FROM ingestion_checkpoint c
                WHERE c.document_id=a.document_id AND c.processor_version=%s
                  AND c.step='official:complete')
              AND d.kind='original' AND d.source_url=a.url
              AND d.media_type='application/pdf'
              AND d.metadata->>'ingestion_kind'=a.kind""",
            (url, WEEKLY_NATIVE_PENDING_ORIGINALS[JUL2022_PENDING_URL],
             JUL2022_OLD_ASSET_VERSION, list(JUL2022_PENDING_ERRORS), quote_version),
        ).fetchone()
    if (row is None and url == MAY2013_PENDING_URL and kind == "dane-weekly-pdf"
            and expected_version == MAY2013_PENDING_NEW_VERSION
            and quote_version == MAY2013_PENDING_NEW_VERSION):
        row = db.execute(
            """SELECT d.id,d.content FROM ingestion_asset a JOIN source_document d
            ON d.id=a.document_id WHERE a.url=%s AND a.kind='dane-weekly-pdf'
              AND a.status='pending' AND a.records=0 AND a.document_id=%s
              AND a.processor_version='' AND a.observed_on='2013-05-24'
              AND a.error=%s AND EXISTS (
                SELECT 1 FROM ingestion_checkpoint c WHERE c.document_id=a.document_id
                  AND c.processor_version=%s AND c.step=%s AND c.records=4201)
              AND NOT EXISTS (
                SELECT 1 FROM ingestion_checkpoint c WHERE c.document_id=a.document_id
                  AND c.processor_version=%s AND c.step='official:complete')
              AND d.kind='original' AND d.source_url=a.url
              AND d.media_type='application/pdf'
              AND d.metadata->>'ingestion_kind'=a.kind""",
            (url, MAY2013_PENDING_DID, MAY2013_PENDING_ERROR,
             MAY2013_PENDING_OLD_VERSION, MAY2013_PENDING_STEP,
             MAY2013_PENDING_NEW_VERSION),
        ).fetchone()
    # A source-local quote upgrade may already have committed some of its
    # 256-row batches when the worker budget expires. Continue from the same
    # immutable original before any HTTP refresh; never treat a partial batch
    # as a completed source revision.
    pending = WEEKLY_EXACT_PENDING.get(url)
    if (row is None and pending is not None and kind == 'dane-weekly-pdf'
            and expected_version == pending[2]
            and quote_version == pending[2]):
        row = db.execute(
            """SELECT d.id,d.content FROM ingestion_asset a
            JOIN source_document d ON d.id=a.document_id
            WHERE a.url=%s AND a.kind='dane-weekly-pdf'
              AND a.status='pending' AND a.document_id=%s
              AND a.processor_version=ANY(%s::text[])
              AND NOT EXISTS (
                SELECT 1 FROM ingestion_checkpoint c
                WHERE c.document_id=a.document_id AND c.processor_version=%s
                  AND c.step='official:complete')
              AND d.kind='original' AND d.source_url=a.url
              AND d.media_type='application/pdf'
              AND d.metadata->>'ingestion_kind'=a.kind""",
            (url, pending[0], [*pending[1], pending[2]], quote_version),
        ).fetchone()
    if row is None:
        return None
    document_id, content = row
    body = bytes(content or b"")
    if not body.startswith(b"%PDF-") or hashlib.sha256(body).hexdigest() != document_id:
        raise ValueError("Retained PDF parser upgrade has an invalid original SHA or PDF signature")
    return body


def retained_sep2013_page43_original(db, url, kind, expected_version, quote_version=None):
    """Return only the known failed Sep 2013 original for the reviewed repair."""
    from .dane_weekly import SEP2013_PAGE43_URL, SEP2013_PAGE43_SHA, SEP2013_PAGE43_SUFFIX
    from .worker import parser_version
    if url != SEP2013_PAGE43_URL or kind != "dane-weekly-pdf":
        return None
    exact_version = "official-v2" + SEP2013_PAGE43_SUFFIX + ":dane-weekly-v24"
    if (expected_version != exact_version or quote_version != exact_version
            or parser_version(kind, url) != exact_version):
        return None
    row = db.execute(
        """SELECT a.status,a.document_id,a.observed_on,a.processor_version,a.records,a.error,
                  d.id,d.title,d.publisher,d.source_url,d.media_type,d.kind,d.reference_period,
                  d.page_count,d.content,d.metadata
           FROM ingestion_asset a JOIN source_document d ON d.id=a.document_id
           WHERE a.url=%s AND a.kind=%s""", (url, kind),
    ).fetchone()
    if row is None:
        return None
    (status,did,observed,old_version,records,error,docid,title,publisher,source_url,
     media_type,doc_kind,period,page_count,content,metadata)=row
    body=bytes(content or b"")
    exact_old_failure=(status=="failed" and old_version=="official-v2:dane-weekly-v24"
        and records==0 and error=="ValueError: Weekly PDF page 43 has conflicting printed periods")
    if not exact_old_failure:
        return None
    exact_identity=(did==SEP2013_PAGE43_SHA and observed is None and docid==SEP2013_PAGE43_SHA
        and title=="DANE · SIPSA - Semana23_sep_27sep_2013.pdf"
        and publisher=="DANE · SIPSA" and source_url==url and media_type=="application/pdf"
        and doc_kind=="original" and period=="Serie histórica completa" and page_count==44
        and len(body)==1861427 and hashlib.sha256(body).hexdigest()==SEP2013_PAGE43_SHA
        and (metadata or {}).get("ingestion_kind")==kind)
    if not exact_identity:
        raise ValueError("Retained September 2013 weekly original source binding changed")
    checkpoint = db.execute(
        "SELECT records FROM ingestion_checkpoint WHERE document_id=%s AND processor_version=%s AND step='official:complete'",
        (SEP2013_PAGE43_SHA, exact_version),
    ).fetchone()
    if checkpoint is not None:
        if checkpoint[0] != 4336:
            raise ValueError("Retained September 2013 complete checkpoint has an unexpected record count")
        # A process can crash after publishing all quote batches and writing
        # official:complete but before finalizing ingestion_asset.  Return the
        # source-bound original so normal publication replay can verify and
        # reconcile the exact quote/review cohort without an HTTP fallback.
    return body


def retained_aug2013_page43_original(
    db, url, kind, asset_version, quote_version=None
):
    """Return the exact retained Aug 2013 PDF for its narrowly registered repair."""
    if url != AUG2013_PAGE43_URL or kind != "dane-weekly-pdf":
        return None
    from .dane_weekly import AUG2013_PAGE43_SUFFIX
    from .worker import parser_version

    expected = parser_version(kind, url)
    article_version = ":panela-article-60cells-v1"
    if (expected != ("official-v2" + AUG2013_PAGE43_SUFFIX + article_version
                     + AUG2013_PAGE43_UNIT_SUFFIX + ":dane-weekly-v24")
            or asset_version != expected or quote_version != expected):
        return None
    row = db.execute(
        """SELECT a.status,a.document_id,a.observed_on,a.processor_version,a.records,a.error,
                  d.id,d.title,d.publisher,d.source_url,d.media_type,d.kind,d.reference_period,
                  d.page_count,d.content,d.metadata
           FROM ingestion_asset a JOIN source_document d ON d.id=a.document_id
           WHERE a.url=%s AND a.kind=%s""",
        (url, kind),
    ).fetchone()
    if row is None:
        return None
    status, asset_did, observed_on, processor_version, records, error = row[:6]
    resumable_errors = {
        "Official source validated; committed quote batches will resume",
        "Official quote batches retained; catalog completion will resume",
        "Committed official batches retained; next work deferred",
        "Committed official quote batches retained; next batch deferred",
    }
    import re
    def recognized_resume_deferral(value):
        return value in resumable_errors or re.fullmatch(
            r"Official catalog refresh deferred after [0-9]+ of [0-9]+ identities",
            value or "",
        ) is not None
    old_failed = (
        status in ("failed", "pending") and asset_did == AUG2013_PAGE43_SHA
        and observed_on is not None and str(observed_on) == "2013-08-23"
        and processor_version == AUG2013_PAGE43_OLD_VERSION
        and records == 0 and error == AUG2013_PAGE43_OLD_ERROR
    )
    pending_resume = (
        status == "pending" and asset_did == AUG2013_PAGE43_SHA
        and observed_on is not None and str(observed_on) == "2013-08-23"
        and processor_version == expected
        and recognized_resume_deferral(error)
    )
    # WorkDeferred preserves the last completed asset's records/version while
    # marking it pending. Permit that exact prior M/P cohort to resume only
    # after proving its own complete checkpoint, full quote/review counts, and
    # a recognized deferral reason. The new revision must still lack a
    # complete checkpoint; all source identity/body checks below remain shared.
    prior_completed_counts = {
        AUG2013_PAGE43_COMPLETED_M_VERSION: 4163,
        AUG2013_PAGE43_COMPLETED_P_VERSION: 4223,
    }
    pending_prior_resume = (
        status == "pending" and asset_did == AUG2013_PAGE43_SHA
        and observed_on is not None and str(observed_on) == "2013-08-23"
        and processor_version in prior_completed_counts
        and records == prior_completed_counts[processor_version]
        and recognized_resume_deferral(error)
        and db.execute(
            "SELECT count(*) FROM official_price_quote WHERE document_id=%s "
            "AND parser_version=%s",
            (AUG2013_PAGE43_SHA, processor_version),
        ).fetchone() == (records,)
        and db.execute(
            "SELECT count(*) FROM official_source_review WHERE document_id=%s "
            "AND parser_version=%s",
            (AUG2013_PAGE43_SHA, processor_version),
        ).fetchone() == (134,)
        and db.execute(
            "SELECT records FROM ingestion_checkpoint WHERE document_id=%s "
            "AND processor_version=%s AND step='official:complete'",
            (AUG2013_PAGE43_SHA, processor_version),
        ).fetchone() == (records,)
        and not db.execute(
            "SELECT 1 FROM ingestion_checkpoint WHERE document_id=%s "
            "AND processor_version=%s AND step='official:complete'",
            (AUG2013_PAGE43_SHA, expected),
        ).fetchone()
    )
    completed_m = (
        status == "complete" and asset_did == AUG2013_PAGE43_SHA
        and observed_on is not None and str(observed_on) == "2013-08-23"
        and processor_version == AUG2013_PAGE43_COMPLETED_M_VERSION
        and records == 4163 and error is None
        and db.execute(
            "SELECT records FROM ingestion_checkpoint WHERE document_id=%s "
            "AND processor_version=%s AND step='official:complete'",
            (AUG2013_PAGE43_SHA, AUG2013_PAGE43_COMPLETED_M_VERSION),
        ).fetchone() == (4163,)
        and db.execute(
            "SELECT count(*) FROM official_price_quote WHERE document_id=%s "
            "AND parser_version=%s",
            (AUG2013_PAGE43_SHA, AUG2013_PAGE43_COMPLETED_M_VERSION),
        ).fetchone() == (4163,)
        and db.execute(
            "SELECT count(*) FROM official_source_review WHERE document_id=%s "
            "AND parser_version=%s",
            (AUG2013_PAGE43_SHA, AUG2013_PAGE43_COMPLETED_M_VERSION),
        ).fetchone() == (134,)
    )
    # O/P already published the exact article-aware 4,223-quote revision.
    # Accept it only with its complete checkpoint, exact quote/review counts,
    # and the common immutable source-document checks below.
    completed_p = (
        status == "complete" and asset_did == AUG2013_PAGE43_SHA
        and observed_on is not None and str(observed_on) == "2013-08-23"
        and processor_version == AUG2013_PAGE43_COMPLETED_P_VERSION
        and records == 4223 and error is None
        and db.execute(
            "SELECT records FROM ingestion_checkpoint WHERE document_id=%s "
            "AND processor_version=%s AND step='official:complete'",
            (AUG2013_PAGE43_SHA, AUG2013_PAGE43_COMPLETED_P_VERSION),
        ).fetchone() == (4223,)
        and db.execute(
            "SELECT count(*) FROM official_price_quote WHERE document_id=%s "
            "AND parser_version=%s",
            (AUG2013_PAGE43_SHA, AUG2013_PAGE43_COMPLETED_P_VERSION),
        ).fetchone() == (4223,)
        and db.execute(
            "SELECT count(*) FROM official_source_review WHERE document_id=%s "
            "AND parser_version=%s",
            (AUG2013_PAGE43_SHA, AUG2013_PAGE43_COMPLETED_P_VERSION),
        ).fetchone() == (134,)
    )
    if not (old_failed or pending_resume or pending_prior_resume or completed_m or completed_p):
        return None
    if pending_resume and db.execute(
        "SELECT 1 FROM ingestion_checkpoint WHERE document_id=%s "
        "AND processor_version=%s AND step='official:complete'",
        (AUG2013_PAGE43_SHA, expected),
    ).fetchone():
        return None
    (document_id,title,publisher,source_url,media_type,document_kind,
     reference_period,page_count,content,metadata) = row[6:]
    meta = metadata or {}
    if (
        document_id != AUG2013_PAGE43_SHA
        or title != "DANE · SIPSA - Semana_20ago_23ago_2013.pdf"
        or publisher != "DANE · SIPSA"
        or source_url != AUG2013_PAGE43_URL
        or media_type != "application/pdf"
        or document_kind != "original"
        or str(reference_period) != "2013-08-23"
        or page_count != 44
        or meta.get("retention") != "permanent"
        or meta.get("ingestion_kind") != "dane-weekly-pdf"
        or meta.get("original_filename") != "Semana_20ago_23ago_2013.pdf"
    ):
        raise ValueError("Exact August 2013 retained original metadata changed")
    body = bytes(content or b"")
    if not body.startswith(b"%PDF-") or hashlib.sha256(body).hexdigest() != AUG2013_PAGE43_SHA:
        raise ValueError("Exact August 2013 retained original SHA or PDF signature changed")
    return body


def retained_may2013_white_corn_original(
    db, url, kind, asset_version, quote_version=None
):
    """Replay only the exact May 2013 failed heading revision from its original."""
    if url != MAY2013_PENDING_URL or kind != "dane-weekly-pdf":
        return None
    from .worker import asset_parser_version

    expected = MAY2013_PENDING_NEW_VERSION
    if asset_version != expected or quote_version != expected:
        return None
    state = db.execute(
        "SELECT status,document_id,processor_version,observed_on,records,error "
        "FROM ingestion_asset WHERE url=%s AND kind=%s",
        (url, kind),
    ).fetchone()
    if state is None or state not in (
        ("failed", MAY2013_PENDING_DID, expected, date(2013, 5, 24), 4201,
         "ValueError: May 2013 asset is outside the pinned pending/completed lifecycle"),
        ("pending", MAY2013_PENDING_DID, expected, date(2013, 5, 24), 4201,
         "ValueError: May 2013 asset is outside the pinned pending/completed lifecycle"),
    ):
        return None
    # The publisher original and every old quote must still satisfy the same
    # complete source-bound checks used immediately before publication.
    from .official_sources import _validate_may2013_heading_source

    body = _validate_may2013_heading_source(db, url, MAY2013_PENDING_DID, kind)
    if asset_parser_version(kind, url) != expected:
        return None
    return body
