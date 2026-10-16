"""PRIVATE exact native/raw subset guard before append-only missing locators."""

from .city_reports import _PRICE_FIELDS
from .city_reports import _publication_parity
from psycopg.types.json import Jsonb


def checked_missing_rows(db, did, rows):
    native = {}
    for row in rows:
        if len(row) != 17 or row[0] in native:
            raise ValueError('Duplicate or incomplete native city locator')
        native[row[0]] = row
    stored = {
        item[0]: tuple(item[1:]) for item in db.execute(
            f"SELECT source_locator,{','.join(_PRICE_FIELDS)} FROM regional_price "
            "WHERE document_id=%s ORDER BY source_locator", (did,),
        ).fetchall()
    }
    classes = dict(db.execute(
        "SELECT source_locator,category_path FROM regional_classification "
        "WHERE document_id=%s ORDER BY source_locator", (did,),
    ).fetchall())
    if set(stored) != set(classes):
        raise ValueError('Existing city price/classification locator sets differ')
    if set(stored) - set(native):
        raise ValueError('Existing city locator is absent from exact native original')
    for locator, values in stored.items():
        source = native[locator]
        if values != tuple(source[1:]):
            raise ValueError('Existing city 17-field row differs from exact native original')
        if classes[locator] != source[5].split(' > '):
            raise ValueError('Existing city category path differs from exact native original')
    return [native[k] for k in sorted(set(native) - set(stored))]


def hold_subset_conflict(db, did, rows, version, parent, entry, reason):
    """Persist review exclusion without editing immutable raw/class rows."""
    native_sha, stored_sha, details = _publication_parity(db, did, rows)
    details['source_local_subset_error'] = str(reason)
    db.execute(
        'INSERT INTO city_pdf_publication_conflict'
        '(document_id,archive_id,entry_name,processor_version,native_sha256,stored_sha256,details) '
        'VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
        (did,parent,entry,version,native_sha,stored_sha,Jsonb(details)),
    )
