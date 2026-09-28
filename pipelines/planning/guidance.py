"""Verify the specific retained ICA advisory before linking any public claim to it."""
import hashlib
import re
import unicodedata

from bs4 import BeautifulSoup
from psycopg.types.json import Jsonb

ICA_URL = "https://www.ica.gov.co/noticias/ica-vigilancia-fitosanitaria-cafe-santander"
ICA_ALIAS = "ica-coffee-santander"
ICA_TITLE = "El ICA fortalece la vigilancia fitosanitaria del café en Santander"
VERSION = "ica-guidance-v2"
# Exact retained extract independently confirmed to contain the 2025 potato article.
MISIDENTIFIED_EXTRACT_ID = "6c6ba3d7172a16b3afbfb8e1e2a65a2074e0e4e22144f84f20016b88b5da2a28"


def _fold(text):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip().casefold()


def verified_ica_text(html, url=ICA_URL):
    """This dated advisory is not a generic ICA article parser.

    The old similarly named URL resolves to a 2025 potato article. Check the
    actual article, rather than matching a coffee link in navigation or news.
    """
    if url != ICA_URL:
        raise ValueError("Unverified ICA advisory source URL")
    soup = BeautifulSoup(html, "html.parser", from_encoding="utf-8")
    candidates = [a for a in soup.select("article")
                  if a.find_parent("main") is not None and a.find_parent(["nav", "aside"]) is None
                  and any(_fold(h.get_text(" ", strip=True)) == _fold(ICA_TITLE)
                         for h in a.select("h1,h2"))]
    if len(candidates) != 1:
        raise ValueError("ICA coffee advisory article identity is not verified")
    article = candidates[0]
    for tag in article.select("script,style,nav,aside"):
        tag.decompose()
    text = article.get_text("\n", strip=True)
    plain = _fold(text)
    # These exact source statements support the fixed date, scope and number
    # in our advisory. A changed report must be reviewed, not relabeled.
    required = (
        "03 de septiembre de 2026",
        "Santander, 3 de septiembre de 2026.",
        "con corte a julio de 2026",
        "cinco talleres de comunicación del riesgo fitosanitario",
        "65 productores",
        "a julio de 2026 se realizaron 52 visitas iniciales",
        "se registraron seis brotes de broca",
    )
    if any(_fold(s) not in plain for s in required):
        raise ValueError("ICA coffee advisory period or literal claims changed")
    return text


def publish_ica(cur, html):
    """Append verified originals and atomically correct the current pointers.

    No network requests and no mutations to source_document. The old advisory,
    alias, and wrong source metadata remain retained for review. Calling this
    from an existing transaction preserves caller rollback semantics.
    """
    text = verified_ica_text(html).encode("utf-8")  # All validation precedes writes.
    original_id = hashlib.sha256(html).hexdigest()
    extract_id = hashlib.sha256(text).hexdigest()
    with cur.connection.transaction():
        for table, predicate in (("document_alias", "alias"), ("advisory", "id")):
            cur.execute(f"""INSERT INTO retained_record(table_name,fingerprint,record)
                SELECT %s,md5(to_jsonb(t)::text),to_jsonb(t) FROM {table} t
                WHERE {predicate}=%s ON CONFLICT DO NOTHING""", (table, ICA_ALIAS))
        old = cur.execute("SELECT document_id FROM document_alias WHERE alias=%s", (ICA_ALIAS,)).fetchone()
        for did, content, kind, media, metadata in (
            (original_id, html, "original", "text/html", {"validation_version": VERSION}),
            (extract_id, text, "extract", "text/plain", {"parents": [original_id], "validation_version": VERSION,
                "note": "Texto del artículo oficial verificado. Monitoreo de Santander hasta julio de 2026; no ubica un brote en tu predio."}),
        ):
            cur.execute("""INSERT INTO source_document
                (id,title,publisher,source_url,media_type,kind,reference_period,content,metadata)
                VALUES (%s,%s,'ICA',%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO NOTHING""",
                (did, ICA_TITLE, ICA_URL, media, kind,
                 "3 de septiembre de 2026; actividades con corte a julio de 2026", content, Jsonb(metadata)))
        if old and old[0] == MISIDENTIFIED_EXTRACT_ID:
            cur.execute("""INSERT INTO official_source_review
                (document_id,source_locator,parser_version,record,reason)
                VALUES (%s,'advisory source identity',%s,%s,%s) ON CONFLICT DO NOTHING""",
                (old[0], VERSION, Jsonb({"alias": ICA_ALIAS, "replacement_document_id": extract_id,
                    "replacement_original_id": original_id, "replacement_source_url": ICA_URL}),
                 "La identidad del documento anterior no respalda este aviso de café. Se conserva íntegro; el alias actual apunta al artículo verificado de ICA del 3 de septiembre de 2026."))
        cur.execute("""INSERT INTO document_alias(alias,document_id) VALUES (%s,%s)
            ON CONFLICT(alias) DO UPDATE SET document_id=excluded.document_id
            WHERE document_alias.document_id IS DISTINCT FROM excluded.document_id""", (ICA_ALIAS, extract_id))
        cur.execute("""INSERT INTO advisory
            (id,title,summary,action,crops,departments,published_on,valid_until,kind,document_id,source_page,source_url)
            VALUES (%s,%s,%s,%s,%s,%s,'2026-09-03','2026-12-03','monitoring',%s,NULL,%s)
            ON CONFLICT(id) DO UPDATE SET document_id=excluded.document_id,source_url=excluded.source_url,
                title=excluded.title,summary=excluded.summary,action=excluded.action,
                crops=excluded.crops,departments=excluded.departments,published_on=excluded.published_on,
                valid_until=excluded.valid_until,kind=excluded.kind,source_page=excluded.source_page
            WHERE advisory IS DISTINCT FROM excluded""",
            (ICA_ALIAS, "Revisa señales de broca en el café",
             "El ICA reportó acciones de vigilancia y seis brotes de broca en lugares visitados de Santander, con corte a julio de 2026.",
             "Observa los frutos y consulta con el servicio de extensión o el ICA si encuentras señales. El reporte no ubica un brote en tu predio.",
             Jsonb(["Café"]), Jsonb(["Santander"]), extract_id, ICA_URL))
        for table, predicate in (("document_alias", "alias"), ("advisory", "id")):
            cur.execute(f"""INSERT INTO retained_record(table_name,fingerprint,record)
                SELECT %s,md5(to_jsonb(t)::text),to_jsonb(t) FROM {table} t
                WHERE {predicate}=%s ON CONFLICT DO NOTHING""", (table, ICA_ALIAS))
    return {"original_id": original_id, "extract_id": extract_id, "source_url": ICA_URL}
