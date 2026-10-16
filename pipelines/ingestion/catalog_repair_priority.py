"""Bounded priority for identities changed by completed, exact-source repairs.

This only chooses dirty catalog keys. ``official_catalog.refresh_dirty`` retains
its own eligibility check and the other 96 FIFO places in a 100-key batch.
"""

import time

from .resumable_inputs import WorkDeferred


# Resolve the finite source/checkpoint registry before traversing its quotes.
# Otherwise PostgreSQL can repeat original-document validation for every row.
SQL = """WITH repaired(url,kind,asset_version,quote_version) AS (
  VALUES {values}
), eligible AS MATERIALIZED (
  SELECT a.document_id,r.quote_version
  FROM repaired r JOIN ingestion_asset a ON a.url=r.url AND a.kind=r.kind
  JOIN source_document d ON d.id=a.document_id
    AND d.source_url=r.url AND d.kind='original'
  JOIN ingestion_checkpoint cp ON cp.document_id=a.document_id
    AND cp.processor_version=r.quote_version AND cp.step='official:complete'
  WHERE a.status='complete' AND a.processor_version=r.asset_version
), changed_locators AS MATERIALIZED (
  -- Coarse, source-scoped test only. A changed identity must contain at least
  -- two distinct historical quote keys at this exact original/locator.
  -- The exact current-version/newest/strictly-older guards remain below.
  SELECT q.document_id,q.source_locator
  FROM eligible e JOIN official_price_quote q ON q.document_id=e.document_id
  GROUP BY q.document_id,q.source_locator
  HAVING min(q.quote_key)<>max(q.quote_key)
), changed AS (
  SELECT DISTINCT current_quote.quote_key
  FROM eligible e JOIN changed_locators g ON g.document_id=e.document_id
  JOIN official_price_quote current_quote ON current_quote.document_id=e.document_id
    AND current_quote.source_locator=g.source_locator
    AND current_quote.parser_version=e.quote_version
  WHERE NOT EXISTS (
    SELECT 1 FROM official_price_quote newer
    WHERE newer.document_id=current_quote.document_id
      AND newer.source_locator=current_quote.source_locator
      AND newer.parsed_at>current_quote.parsed_at
  ) AND EXISTS (
    SELECT 1 FROM official_price_quote previous_quote
    WHERE previous_quote.document_id=current_quote.document_id
      AND previous_quote.source_locator=current_quote.source_locator
      AND previous_quote.parsed_at<current_quote.parsed_at
      AND previous_quote.quote_key<>current_quote.quote_key
  )
)
SELECT c.quote_key FROM changed JOIN official_catalog_current c USING(quote_key)
WHERE c.dirty OR c.version<>%s
ORDER BY CASE WHEN c.dirty THEN c.dirty_since ELSE c.refreshed_at END NULLS FIRST,
  c.quote_key LIMIT 4"""


def changed_identity_priority(db, repairs, asset_version, quote_version, *,
                              catalog_version, deadline=None):
    """Return <=4 oldest dirty changed keys from completed registered originals.

    ``repairs`` is the worker's finite exact-URL registry. A failed SQL read is
    deliberately visible, rather than silently weakening publication guards.
    """
    if deadline is not None and time.monotonic() >= deadline:
        raise WorkDeferred("Official catalog repair priority deferred before source check")
    if not repairs:
        return ()
    if len(repairs) > 64:
        raise ValueError("Official catalog repair registry must remain bounded")
    rows = []
    for url, (kind, _) in repairs.items():
        rows.append((url, kind, asset_version(kind, url), quote_version(kind, url)))
    placeholders = ",".join(["(%s,%s,%s,%s)"] * len(rows))
    remaining_ms = 4000 if deadline is None else min(
        4000, max(1, int((deadline - time.monotonic()) * 1000))
    )
    with db.transaction():
        db.execute("SELECT set_config('statement_timeout',%s,true)", (f"{remaining_ms}ms",))
        selected = db.execute(
            SQL.format(values=placeholders),
            (*[part for row in rows for part in row], catalog_version),
        ).fetchall()
    if deadline is not None and time.monotonic() >= deadline:
        raise WorkDeferred("Official catalog repair priority deferred after source check")
    return tuple(row[0] for row in selected)
