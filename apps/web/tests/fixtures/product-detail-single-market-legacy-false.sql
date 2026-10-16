WITH selected AS MATERIALIZED (
        SELECT selected_market_quotes.* FROM unnest($7::text[]) AS requested_market(id)
        JOIN market selected_market ON selected_market.id=requested_market.id
        AND selected_market.id<>'sipsa-bogota-d-c-corabastos'
        CROSS JOIN LATERAL (
          WITH quotes AS (
  SELECT o.product_id,m.id AS market_id,m.id AS source_market_id,m.name AS market_name,m.city,m.region,
    p.name AS product_name,p.category,ARRAY[p.category]::text[] AS category_path,
    o.observed_on,o.price,o.min_price,o.max_price,o.unit,
    'Por unidad de medida'::text AS presentation,
    CASE o.unit WHEN 'kg' THEN '1 kg' WHEN 'litre' THEN '1 litro' WHEN 'unit' THEN '1 unidad' WHEN '125kg' THEN 'Carga de 125 kg' ELSE o.unit END AS units,
    CASE o.source_id WHEN 'dane-milk-farm' THEN 'farmgate' WHEN 'dane-rice-mill' THEN 'mill' WHEN 'fnc' THEN 'coffee' ELSE 'monthly' END AS series,
    o.document_id,o.source_locator,o.source_url,o.period,
    coalesce(substring(o.source_locator from '^PDF page ([1-9][0-9]{0,4})(?:[[:space:],;]|$)')::integer,1) AS source_page,
    NULL::text AS source_units
  FROM published_price_observation o JOIN market m ON m.id=o.market_id JOIN product p ON p.id=o.product_id
  UNION ALL

  SELECT product_id,market_id,source_market_id,market_name,city,region,product_name,category,category_path,
    observed_on,(coalesce(money.corrected_min_price,city.min_price)+coalesce(money.corrected_max_price,city.max_price))/2 AS price,
    coalesce(money.corrected_min_price,city.min_price) AS min_price,
    coalesce(money.corrected_max_price,city.max_price) AS max_price,
    comparison_unit AS unit,upper(left(presentation,1)) || lower(substr(presentation,2)) AS presentation,units,
    'city'::text AS series,city.document_id,city.source_locator,source_url,'daily'::text AS period,source_page,source_units FROM (
    
    SELECT DISTINCT ON(r.product_id,(CASE WHEN m.municipality_id='11001' AND m.name IN ('Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos') THEN 'sipsa-bogota-d-c-corabastos' ELSE m.id END),r.observed_on,lower(btrim(r.presentation)),r.quantity,CASE WHEN (r.product_id='arroz-de-primera'
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
    ELSE lower(btrim(r.source_unit)) END)
      r.*,CASE WHEN (r.product_id='arroz-de-primera'
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
      OR starts_with(d.source_url,'https://www.dane.gov.co/files/operaciones/SIPSA/'))) THEN '25 × 500 g' ELSE r.unit END AS comparison_unit,r.quantity::float8::text || ' ' || r.source_unit AS source_units,(CASE WHEN m.municipality_id='11001' AND m.name IN ('Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos') THEN 'sipsa-bogota-d-c-corabastos' ELSE m.id END) AS market_id,(CASE WHEN r.market_name='Bogotà, Corabastos' THEN NULL::text ELSE m.id END) AS source_market_id,m.city,m.region,
      string_to_array(r.category,' > ') AS category_path,
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
    ELSE r.quantity::float8::text || ' ' || upper(left(r.source_unit,1)) || lower(substr(r.source_unit,2)) END AS units,d.source_url
    FROM resolved_regional_price r JOIN market m ON m.name=(CASE WHEN r.market_name='Bogotà, Corabastos'
    THEN 'Bogotá, D.C., Corabastos' ELSE r.market_name END)
    JOIN source_document d ON d.id=r.document_id
    
    WHERE r.product_id=$1 AND r.market_name=selected_market.name AND m.id=selected_market.id
    AND lower(btrim(r.presentation))=lower(btrim($4))
    AND upper(left(r.presentation,1)) || lower(substr(r.presentation,2))=$4
    AND r.quantity::float8::text || ' ' || upper(left(r.source_unit,1)) || lower(substr(r.source_unit,2))=$5
    AND NOT coalesce((m.municipality_id='11001' AND m.name IN ('Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos')
    AND (SELECT count(DISTINCT latest.market_name)>1
                  AND count(DISTINCT (latest.min_price,latest.max_price,
                    latest.min_unit_price,latest.max_unit_price,latest.category_path))>1
      FROM (SELECT DISTINCT ON (rival.market_name)
          rival.market_name,rival.min_price,rival.max_price,
          (to_jsonb(rival)->>'min_unit_price')::numeric AS min_unit_price,
          (to_jsonb(rival)->>'max_unit_price')::numeric AS max_unit_price,
          coalesce(rival_class.category_path,string_to_array(rival.category,' > ')) AS category_path
        FROM published_regional_price rival
        JOIN source_document rival_d ON rival_d.id=rival.document_id
        LEFT JOIN regional_classification rival_class
          ON rival_class.document_id=rival.document_id AND rival_class.source_locator=rival.source_locator
        LEFT JOIN regional_price_product_correction rival_c
          ON rival_c.document_id=rival.document_id AND rival_c.source_locator=rival.source_locator
        WHERE rival.market_name IN ('Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos')
          AND rival.observed_on=r.observed_on
          AND coalesce(rival_c.corrected_product_id,rival.product_id)=r.product_id
          AND lower(btrim(rival.presentation))=lower(btrim(r.presentation))
          AND rival.quantity=r.quantity
          AND lower(btrim(rival.source_unit))=lower(btrim(r.source_unit))
          AND rival.unit=r.unit AND rival.round=r.round
        ORDER BY rival.market_name,rival_d.retrieved_at DESC,rival.document_id DESC,rival.source_locator
      ) latest)),false)
    ORDER BY r.product_id,(CASE WHEN m.municipality_id='11001' AND m.name IN ('Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos') THEN 'sipsa-bogota-d-c-corabastos' ELSE m.id END),r.observed_on,lower(btrim(r.presentation)),r.quantity,CASE WHEN (r.product_id='arroz-de-primera'
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
    ELSE lower(btrim(r.source_unit)) END,r.round DESC,d.retrieved_at DESC,r.source_locator
  ) city
  LEFT JOIN verified_city_pdf_price_overlay money ON money.document_id=city.document_id
    AND money.source_locator=city.source_locator)
          SELECT * FROM quotes WHERE product_id=$1 AND ($2='' OR translate(lower(btrim(region)),'ÁÉÍÓÚÜÑ','áéíóúüñ')=translate(lower(btrim($2)),'ÁÉÍÓÚÜÑ','áéíóúüñ')) AND series=$3 AND presentation=$4 AND units=$5 AND ($6='' OR market_id=$6) AND observed_on<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date AND market_id=selected_market.id OFFSET 0
        ) selected_market_quotes
        UNION ALL
        SELECT alias_quotes.* FROM market selected_market
        CROSS JOIN LATERAL (
          WITH quotes AS (
  SELECT o.product_id,m.id AS market_id,m.id AS source_market_id,m.name AS market_name,m.city,m.region,
    p.name AS product_name,p.category,ARRAY[p.category]::text[] AS category_path,
    o.observed_on,o.price,o.min_price,o.max_price,o.unit,
    'Por unidad de medida'::text AS presentation,
    CASE o.unit WHEN 'kg' THEN '1 kg' WHEN 'litre' THEN '1 litro' WHEN 'unit' THEN '1 unidad' WHEN '125kg' THEN 'Carga de 125 kg' ELSE o.unit END AS units,
    CASE o.source_id WHEN 'dane-milk-farm' THEN 'farmgate' WHEN 'dane-rice-mill' THEN 'mill' WHEN 'fnc' THEN 'coffee' ELSE 'monthly' END AS series,
    o.document_id,o.source_locator,o.source_url,o.period,
    coalesce(substring(o.source_locator from '^PDF page ([1-9][0-9]{0,4})(?:[[:space:],;]|$)')::integer,1) AS source_page,
    NULL::text AS source_units
  FROM published_price_observation o JOIN market m ON m.id=o.market_id JOIN product p ON p.id=o.product_id
  UNION ALL

  SELECT product_id,market_id,source_market_id,market_name,city,region,product_name,category,category_path,
    observed_on,(coalesce(money.corrected_min_price,city.min_price)+coalesce(money.corrected_max_price,city.max_price))/2 AS price,
    coalesce(money.corrected_min_price,city.min_price) AS min_price,
    coalesce(money.corrected_max_price,city.max_price) AS max_price,
    comparison_unit AS unit,upper(left(presentation,1)) || lower(substr(presentation,2)) AS presentation,units,
    'city'::text AS series,city.document_id,city.source_locator,source_url,'daily'::text AS period,source_page,source_units FROM (
    WITH alias_keys AS MATERIALIZED (
    SELECT rival.document_id,rival.source_locator,rival.observed_on,lower(btrim(rival.presentation)) AS presentation_key,
      rival.quantity,lower(btrim(rival.source_unit)) AS unit_key,rival.unit,rival.round,rival.market_name
    FROM regional_price rival
    LEFT JOIN regional_price_product_correction rival_c
      ON rival_c.document_id=rival.document_id AND rival_c.source_locator=rival.source_locator
    WHERE rival.product_id=$1 AND rival_c.document_id IS NULL
      AND rival.market_name IN ('Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos')
    UNION ALL
    SELECT rival.document_id,rival.source_locator,rival.observed_on,lower(btrim(rival.presentation)),rival.quantity,
      lower(btrim(rival.source_unit)),rival.unit,rival.round,rival.market_name
    FROM regional_price_product_correction rival_c
    JOIN regional_price rival ON rival.document_id=rival_c.document_id
      AND rival.source_locator=rival_c.source_locator
    WHERE rival_c.corrected_product_id=$1
      AND rival.market_name IN ('Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos')
  ), alias_overlap AS MATERIALIZED (
    SELECT 1 FROM alias_keys
    GROUP BY observed_on,presentation_key,quantity,unit_key,unit,round
    HAVING count(DISTINCT market_name)>1
    LIMIT 1
  ), alias_source_ids AS MATERIALIZED (
    SELECT DISTINCT document_id,source_locator FROM alias_keys
  ), alias_document_samples AS MATERIALIZED (
    SELECT document_id,min(source_locator) AS sample_locator
    FROM alias_source_ids GROUP BY document_id
  ), alias_eligible_documents AS MATERIALIZED (
    SELECT sample.document_id FROM alias_document_samples sample
    CROSS JOIN LATERAL (
      -- The published view is the authoritative quarantine/adjudication gate.
      -- Its rule is document-wide, so one retained candidate row proves it.
      SELECT 1 FROM published_regional_price published
      WHERE published.document_id=sample.document_id
        AND published.source_locator=sample.sample_locator OFFSET 0
    ) eligible
  ), alias_scoped AS MATERIALIZED (
    SELECT r.document_id,r.source_locator,r.observed_on,
      CASE WHEN c.document_id IS NULL THEN r.product_id ELSE c.corrected_product_id END AS product_id,
      CASE WHEN c.document_id IS NULL THEN r.product_name ELSE c.corrected_product_name END AS product_name,
      r.market_name,coalesce(o.corrected_category,r.category) AS category,
      r.presentation,r.quantity,r.source_unit,r.round,r.round_label,
      r.min_price,r.max_price,r.unit,r.min_unit_price,r.max_unit_price,r.source_page
    FROM alias_source_ids source_id
    JOIN alias_eligible_documents eligible ON eligible.document_id=source_id.document_id
    JOIN regional_price r ON r.document_id=source_id.document_id
      AND r.source_locator=source_id.source_locator
    LEFT JOIN regional_price_product_correction c ON c.document_id=r.document_id
      AND c.source_locator=r.source_locator
    LEFT JOIN verified_regional_category_overlay o ON o.document_id=r.document_id
      AND o.source_locator=r.source_locator
  ) 
    SELECT DISTINCT ON(r.product_id,(CASE WHEN m.municipality_id='11001' AND m.name IN ('Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos') THEN 'sipsa-bogota-d-c-corabastos' ELSE m.id END),r.observed_on,lower(btrim(r.presentation)),r.quantity,CASE WHEN (r.product_id='arroz-de-primera'
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
    ELSE lower(btrim(r.source_unit)) END)
      r.*,CASE WHEN (r.product_id='arroz-de-primera'
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
      OR starts_with(d.source_url,'https://www.dane.gov.co/files/operaciones/SIPSA/'))) THEN '25 × 500 g' ELSE r.unit END AS comparison_unit,r.quantity::float8::text || ' ' || r.source_unit AS source_units,(CASE WHEN m.municipality_id='11001' AND m.name IN ('Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos') THEN 'sipsa-bogota-d-c-corabastos' ELSE m.id END) AS market_id,(CASE WHEN r.market_name='Bogotà, Corabastos' THEN NULL::text ELSE m.id END) AS source_market_id,m.city,m.region,
      string_to_array(r.category,' > ') AS category_path,
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
    ELSE r.quantity::float8::text || ' ' || upper(left(r.source_unit,1)) || lower(substr(r.source_unit,2)) END AS units,d.source_url
    FROM alias_scoped r JOIN market m ON m.name=(CASE WHEN r.market_name='Bogotà, Corabastos'
    THEN 'Bogotá, D.C., Corabastos' ELSE r.market_name END)
    JOIN source_document d ON d.id=r.document_id
    
    WHERE r.product_id=$1 AND r.market_name IN ('Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos') AND m.municipality_id='11001'
    AND lower(btrim(r.presentation))=lower(btrim($4))
    AND upper(left(r.presentation,1)) || lower(substr(r.presentation,2))=$4
    AND r.quantity::float8::text || ' ' || upper(left(r.source_unit,1)) || lower(substr(r.source_unit,2))=$5
    AND CASE WHEN EXISTS(SELECT 1 FROM alias_overlap) THEN NOT coalesce((m.municipality_id='11001' AND m.name IN ('Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos')
    AND (SELECT count(DISTINCT latest.market_name)>1
                  AND count(DISTINCT (latest.min_price,latest.max_price,
                    latest.min_unit_price,latest.max_unit_price,latest.category_path))>1
      FROM (SELECT DISTINCT ON (rival.market_name)
          rival.market_name,rival.min_price,rival.max_price,
          (to_jsonb(rival)->>'min_unit_price')::numeric AS min_unit_price,
          (to_jsonb(rival)->>'max_unit_price')::numeric AS max_unit_price,
          coalesce(rival_class.category_path,string_to_array(rival.category,' > ')) AS category_path
        FROM published_regional_price rival
        JOIN source_document rival_d ON rival_d.id=rival.document_id
        LEFT JOIN regional_classification rival_class
          ON rival_class.document_id=rival.document_id AND rival_class.source_locator=rival.source_locator
        LEFT JOIN regional_price_product_correction rival_c
          ON rival_c.document_id=rival.document_id AND rival_c.source_locator=rival.source_locator
        WHERE rival.market_name IN ('Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos')
          AND rival.observed_on=r.observed_on
          AND coalesce(rival_c.corrected_product_id,rival.product_id)=r.product_id
          AND lower(btrim(rival.presentation))=lower(btrim(r.presentation))
          AND rival.quantity=r.quantity
          AND lower(btrim(rival.source_unit))=lower(btrim(r.source_unit))
          AND rival.unit=r.unit AND rival.round=r.round
        ORDER BY rival.market_name,rival_d.retrieved_at DESC,rival.document_id DESC,rival.source_locator
      ) latest)),false) ELSE TRUE END
    ORDER BY r.product_id,(CASE WHEN m.municipality_id='11001' AND m.name IN ('Bogotá, Corabastos','Bogotá D.C., Corabastos','Bogotá, D.C., Corabastos','Bogotà, Corabastos') THEN 'sipsa-bogota-d-c-corabastos' ELSE m.id END),r.observed_on,lower(btrim(r.presentation)),r.quantity,CASE WHEN (r.product_id='arroz-de-primera'
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
    ELSE lower(btrim(r.source_unit)) END,r.round DESC,d.retrieved_at DESC,r.source_locator
  ) city
  LEFT JOIN verified_city_pdf_price_overlay money ON money.document_id=city.document_id
    AND money.source_locator=city.source_locator)
          SELECT * FROM quotes WHERE product_id=$1 AND ($2='' OR translate(lower(btrim(region)),'ÁÉÍÓÚÜÑ','áéíóúüñ')=translate(lower(btrim($2)),'ÁÉÍÓÚÜÑ','áéíóúüñ')) AND series=$3 AND presentation=$4 AND units=$5 AND ($6='' OR market_id=$6) AND observed_on<=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Bogota')::date AND market_id=selected_market.id OFFSET 0
        ) alias_quotes
        WHERE selected_market.id='sipsa-bogota-d-c-corabastos'
          AND selected_market.id=ANY($7::text[])
      ), latest AS (
        SELECT DISTINCT ON(market_id) *,market_id AS id,market_name AS name,observed_on AS date
        FROM selected ORDER BY market_id,observed_on DESC
      ), history AS (
        SELECT observed_on AS date,avg(price) AS price,count(DISTINCT market_id) AS market_count,
          coalesce(jsonb_agg(DISTINCT jsonb_build_object(
            'document_id',document_id,'source_locator',source_locator,'source_page',source_page,
            'market_id',market_id,'source_market_id',source_market_id,'market_name',market_name,
            'source_units',source_units
          )) FILTER (WHERE document_id IS NOT NULL),'[]'::jsonb) AS sources
        FROM selected GROUP BY observed_on
      ) SELECT
        coalesce((SELECT jsonb_agg(latest ORDER BY market_id) FROM latest),'[]'::jsonb) AS markets,
        coalesce((SELECT jsonb_agg(history ORDER BY date) FROM history),'[]'::jsonb) AS history