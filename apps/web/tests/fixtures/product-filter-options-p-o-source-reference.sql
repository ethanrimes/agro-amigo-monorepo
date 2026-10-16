
  WITH alias_candidates AS MATERIALIZED (
    SELECT rival.document_id,rival.source_locator,rival.observed_on,rival.market_name,
      lower(btrim(rival.presentation)) AS presentation_key,rival.quantity,
      lower(btrim(rival.source_unit)) AS unit_key,rival.unit,rival.round,
      rival.min_price,rival.max_price,
      (to_jsonb(rival)->>'min_unit_price')::numeric AS min_unit_price,
      (to_jsonb(rival)->>'max_unit_price')::numeric AS max_unit_price,
      coalesce(rival_class.category_path,string_to_array(rival.category,' > ')) AS category_path,
      rival_d.retrieved_at
    FROM published_regional_price rival
    JOIN source_document rival_d ON rival_d.id=rival.document_id
    LEFT JOIN regional_classification rival_class
      ON rival_class.document_id=rival.document_id AND rival_class.source_locator=rival.source_locator
    LEFT JOIN regional_price_product_correction rival_c
      ON rival_c.document_id=rival.document_id AND rival_c.source_locator=rival.source_locator
    WHERE rival.product_id=$1 AND rival_c.document_id IS NULL
      AND rival.market_name IN ('Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos')
    UNION ALL
    SELECT rival.document_id,rival.source_locator,rival.observed_on,rival.market_name,
      lower(btrim(rival.presentation)),rival.quantity,
      lower(btrim(rival.source_unit)),rival.unit,rival.round,
      rival.min_price,rival.max_price,
      (to_jsonb(rival)->>'min_unit_price')::numeric,
      (to_jsonb(rival)->>'max_unit_price')::numeric,
      coalesce(rival_class.category_path,string_to_array(rival.category,' > ')),
      rival_d.retrieved_at
    FROM regional_price_product_correction rival_c
    JOIN published_regional_price rival
      ON rival.document_id=rival_c.document_id AND rival.source_locator=rival_c.source_locator
    JOIN source_document rival_d ON rival_d.id=rival.document_id
    LEFT JOIN regional_classification rival_class
      ON rival_class.document_id=rival.document_id AND rival_class.source_locator=rival.source_locator
    WHERE rival_c.corrected_product_id=$1
      AND rival.market_name IN ('Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos')
  ), alias_latest AS MATERIALIZED (
    SELECT DISTINCT ON (observed_on,presentation_key,quantity,unit_key,unit,round,market_name)
      observed_on,presentation_key,quantity,unit_key,unit,round,market_name,
      min_price,max_price,min_unit_price,max_unit_price,category_path
    FROM alias_candidates
    ORDER BY observed_on,presentation_key,quantity,unit_key,unit,round,market_name,
      retrieved_at DESC,document_id DESC,source_locator
  ), alias_conflicts AS MATERIALIZED (
    SELECT observed_on,presentation_key,quantity,unit_key,unit,round
    FROM alias_latest
    GROUP BY observed_on,presentation_key,quantity,unit_key,unit,round
    HAVING count(DISTINCT market_name)>1
      AND count(DISTINCT (min_price,max_price,min_unit_price,max_unit_price,category_path))>1
  ), city_dimensions AS MATERIALIZED (
    SELECT DISTINCT (CASE WHEN m.municipality_id='11001' AND m.name IN ('Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos') THEN 'sipsa-bogota-d-c-corabastos' ELSE m.id END) AS market_id,(CASE WHEN m.municipality_id='11001' AND m.name IN ('Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos') THEN 'Bogotá, D.C., Corabastos' ELSE m.name END) AS market_name,
      lower(btrim(r.presentation)) AS presentation_key,r.quantity,
      lower(btrim(r.source_unit)) AS unit_key,
      upper(left(r.presentation,1)) || lower(substr(r.presentation,2)) AS presentation,
      CASE WHEN (r.product_id='arroz-de-primera'
    AND r.market_name='Cali, Santa Elena'
    AND lower(btrim(r.presentation))='bolsa'
    AND r.quantity=25
    AND lower(btrim(r.source_unit)) IN ('unidad 500 gr','unidades 500 gr')
    AND lower(btrim(r.unit))=lower(btrim(r.source_unit))
    AND r.source_locator IS NOT NULL AND r.source_locator<>''
    AND d.id=r.document_id AND d.kind='original'
    AND d.media_type IN ('application/pdf',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    AND (starts_with(d.source_url,'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/')
      OR starts_with(d.source_url,'https://www.dane.gov.co/files/operaciones/SIPSA/'))) THEN '25 × 500 g'
    ELSE r.quantity::float8::text || ' ' || upper(left(r.source_unit,1)) || lower(substr(r.source_unit,2)) END AS units,
      min(r.observed_on) OVER (PARTITION BY (CASE WHEN m.municipality_id='11001' AND m.name IN ('Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos') THEN 'sipsa-bogota-d-c-corabastos' ELSE m.id END),
        upper(left(r.presentation,1)) || lower(substr(r.presentation,2)),CASE WHEN (r.product_id='arroz-de-primera'
    AND r.market_name='Cali, Santa Elena'
    AND lower(btrim(r.presentation))='bolsa'
    AND r.quantity=25
    AND lower(btrim(r.source_unit)) IN ('unidad 500 gr','unidades 500 gr')
    AND lower(btrim(r.unit))=lower(btrim(r.source_unit))
    AND r.source_locator IS NOT NULL AND r.source_locator<>''
    AND d.id=r.document_id AND d.kind='original'
    AND d.media_type IN ('application/pdf',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    AND (starts_with(d.source_url,'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/')
      OR starts_with(d.source_url,'https://www.dane.gov.co/files/operaciones/SIPSA/'))) THEN '25 × 500 g'
    ELSE r.quantity::float8::text || ' ' || upper(left(r.source_unit,1)) || lower(substr(r.source_unit,2)) END) AS first_report_on,
      max(r.observed_on) OVER (PARTITION BY (CASE WHEN m.municipality_id='11001' AND m.name IN ('Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos') THEN 'sipsa-bogota-d-c-corabastos' ELSE m.id END),
        upper(left(r.presentation,1)) || lower(substr(r.presentation,2)),CASE WHEN (r.product_id='arroz-de-primera'
    AND r.market_name='Cali, Santa Elena'
    AND lower(btrim(r.presentation))='bolsa'
    AND r.quantity=25
    AND lower(btrim(r.source_unit)) IN ('unidad 500 gr','unidades 500 gr')
    AND lower(btrim(r.unit))=lower(btrim(r.source_unit))
    AND r.source_locator IS NOT NULL AND r.source_locator<>''
    AND d.id=r.document_id AND d.kind='original'
    AND d.media_type IN ('application/pdf',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    AND (starts_with(d.source_url,'https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/')
      OR starts_with(d.source_url,'https://www.dane.gov.co/files/operaciones/SIPSA/'))) THEN '25 × 500 g'
    ELSE r.quantity::float8::text || ' ' || upper(left(r.source_unit,1)) || lower(substr(r.source_unit,2)) END) AS last_report_on
    FROM resolved_regional_price r JOIN market m ON m.name=(CASE WHEN r.market_name='Bogotà, Corabastos'
    THEN 'Bogotá, D.C., Corabastos' ELSE r.market_name END)
    JOIN source_document d ON d.id=r.document_id
    WHERE r.product_id=$1 AND ($2='' OR translate(lower(btrim(m.region)),'ÁÉÍÓÚÜÑ','áéíóúüñ')=translate(lower(btrim($2)),'ÁÉÍÓÚÜÑ','áéíóúüñ'))
      AND r.observed_on<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date
      AND NOT coalesce((m.municipality_id='11001' AND m.name IN ('Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos')
        AND EXISTS (SELECT 1 FROM alias_conflicts conflict
          WHERE conflict.observed_on=r.observed_on
            AND conflict.presentation_key=lower(btrim(r.presentation))
            AND conflict.quantity=r.quantity
            AND conflict.unit_key=lower(btrim(r.source_unit))
            AND conflict.unit=r.unit AND conflict.round=r.round)),false)
  ), ambiguity AS (
    SELECT (EXISTS(SELECT 1 FROM city_dimensions
      GROUP BY market_id,presentation_key,quantity,unit_key HAVING count(*)>1)
      OR EXISTS(SELECT 1 FROM city_dimensions
      GROUP BY market_id,presentation_key,quantity,units
      HAVING count(DISTINCT unit_key)>1)) AS requires_revision_resolution
  ), options AS (
    SELECT DISTINCT
      CASE o.source_id WHEN 'dane-milk-farm' THEN 'farmgate' WHEN 'dane-rice-mill' THEN 'mill' WHEN 'fnc' THEN 'coffee' ELSE 'monthly' END AS series,
      m.id AS market_id,m.name AS market_name,'Por unidad de medida'::text AS presentation,
      CASE o.unit WHEN 'kg' THEN '1 kg' WHEN 'litre' THEN '1 litro' WHEN 'unit' THEN '1 unidad' WHEN '125kg' THEN 'Carga de 125 kg' ELSE o.unit END AS units,
      NULL::date AS first_report_on,NULL::date AS last_report_on
    FROM published_price_observation o JOIN market m ON m.id=o.market_id
    WHERE o.product_id=$1 AND ($2='' OR translate(lower(btrim(m.region)),'ÁÉÍÓÚÜÑ','áéíóúüñ')=translate(lower(btrim($2)),'ÁÉÍÓÚÜÑ','áéíóúüñ'))
      AND o.observed_on<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date
    UNION
    SELECT 'city',market_id,market_name,presentation,units,first_report_on,last_report_on FROM city_dimensions
  ) SELECT options.*,ambiguity.requires_revision_resolution FROM options CROSS JOIN ambiguity
    ORDER BY series,market_name,presentation,units