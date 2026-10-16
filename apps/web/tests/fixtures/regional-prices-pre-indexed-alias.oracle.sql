
  WITH RECURSIVE names(market_name) AS (
    (SELECT market_name FROM published_regional_price ORDER BY market_name LIMIT 1)
    UNION ALL
    SELECT n.market_name FROM names prior CROSS JOIN LATERAL (
      SELECT market_name FROM published_regional_price WHERE market_name>prior.market_name
      ORDER BY market_name LIMIT 1
    ) n
  ), latest AS MATERIALIZED (
    SELECT n.market_name,p.observed_on AS day FROM names n CROSS JOIN LATERAL (
      SELECT observed_on FROM published_regional_price r WHERE r.market_name=n.market_name
        AND observed_on<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date
      ORDER BY observed_on DESC LIMIT 1
    ) p
  ), dated AS MATERIALIZED (
    SELECT raw.* FROM latest l CROSS JOIN LATERAL (
      SELECT r.* FROM published_regional_price r
      WHERE r.market_name=l.market_name AND r.observed_on=l.day
      OFFSET 0
    ) raw
  ), ranked AS (
    SELECT r.document_id,r.source_locator,r.observed_on,
      coalesce(c.corrected_product_id,r.product_id) AS product_id,
      coalesce(c.corrected_product_name,r.product_name) AS product_name,
      r.market_name,coalesce((CASE WHEN m.municipality_id='11001' AND m.name IN ('Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos') THEN 'Bogotá, D.C., Corabastos' ELSE m.name END),r.market_name) AS display_market_name,
      coalesce(category_overlay.corrected_category,r.category) AS category,
      r.presentation,r.quantity,r.source_unit,
      r.round,r.round_label,r.min_price,r.max_price,r.unit,
      r.min_unit_price,r.max_unit_price,r.source_page,(CASE WHEN m.municipality_id='11001' AND m.name IN ('Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos') THEN 'sipsa-bogota-d-c-corabastos' ELSE m.id END) AS market_id,(CASE WHEN r.market_name='Bogotà, Corabastos' THEN NULL::text ELSE m.id END) AS source_market_id,
      m.region AS market_region,
      coalesce(string_to_array(category_overlay.corrected_category,' > '),
        cl.category_path,string_to_array(r.category,' > ')) AS category_path,
      row_number() OVER(PARTITION BY (CASE WHEN m.municipality_id='11001' AND m.name IN ('Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos') THEN 'sipsa-bogota-d-c-corabastos' ELSE m.id END),coalesce(c.corrected_product_name,r.product_name),
        r.presentation,r.quantity,r.source_unit,r.round
        ORDER BY r.observed_on DESC,d.retrieved_at DESC,r.document_id) rn
    FROM dated r JOIN source_document d ON d.id=r.document_id
    LEFT JOIN regional_price_product_correction c
      ON c.document_id=r.document_id AND c.source_locator=r.source_locator
    LEFT JOIN regional_classification cl
      ON cl.document_id=r.document_id AND cl.source_locator=r.source_locator
    LEFT JOIN verified_regional_category_overlay category_overlay
      ON category_overlay.document_id=r.document_id
      AND category_overlay.source_locator=r.source_locator
    LEFT JOIN market m ON m.name=(CASE WHEN r.market_name='Bogotà, Corabastos'
    THEN 'Bogotá, D.C., Corabastos' ELSE r.market_name END)
    WHERE NOT coalesce((m.municipality_id='11001' AND m.name IN ('Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos')
    AND (SELECT count(DISTINCT latest.market_name)>1
                  AND count(DISTINCT (latest.min_price,latest.max_price,
                    latest.min_unit_price,latest.max_unit_price,latest.category_path))>1
      FROM (SELECT DISTINCT ON (rival.market_name)
          rival.market_name,rival.min_price,rival.max_price,
          (to_jsonb(rival)->>'min_unit_price')::numeric AS min_unit_price,
          (to_jsonb(rival)->>'max_unit_price')::numeric AS max_unit_price,
          coalesce(string_to_array(rival_overlay.corrected_category,' > '),rival_class.category_path,string_to_array(rival.category,' > ')) AS category_path
        FROM published_regional_price rival
        JOIN source_document rival_d ON rival_d.id=rival.document_id
        LEFT JOIN regional_classification rival_class
          ON rival_class.document_id=rival.document_id AND rival_class.source_locator=rival.source_locator
        LEFT JOIN verified_regional_category_overlay rival_overlay
          ON rival_overlay.document_id=rival.document_id AND rival_overlay.source_locator=rival.source_locator
        LEFT JOIN regional_price_product_correction rival_c
          ON rival_c.document_id=rival.document_id AND rival_c.source_locator=rival.source_locator
        WHERE rival.market_name IN ('Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos')
          AND rival.observed_on=r.observed_on
          AND coalesce(rival_c.corrected_product_id,rival.product_id)=coalesce(c.corrected_product_id,r.product_id)
          AND lower(btrim(rival.presentation))=lower(btrim(r.presentation))
          AND rival.quantity=r.quantity
          AND lower(btrim(rival.source_unit))=lower(btrim(r.source_unit))
          AND rival.unit=r.unit AND rival.round=r.round
        ORDER BY rival.market_name,rival_d.retrieved_at DESC,rival.document_id DESC,rival.source_locator
      ) latest)),false)
  ) SELECT * FROM ranked WHERE rn=1 ORDER BY product_name,market_name,quantity,round
