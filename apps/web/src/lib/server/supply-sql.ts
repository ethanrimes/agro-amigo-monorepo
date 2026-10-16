/** Supply totals scan only narrow indexed values; detailed source rows load for one month. */
export function supplyQueries(product: string, market: string, dateWindow: string) {
  const values: string[] = [];
  const conditions: string[] = [dateWindow];
  if (product) {
    values.push(product);
    conditions.push(`product_id=$${values.length}`);
  }
  if (market) {
    values.push(market);
    conditions.push(`market_id=$${values.length}`);
  }
  const where = conditions.join(" AND ");
  return {
    history: {
      text: `SELECT period_start AS date,sum(quantity_kg) quantity_kg
        FROM supply_observation WHERE ${where} GROUP BY period_start ORDER BY period_start`,
      values,
    },
    month: (period: string) => ({
      text: `SELECT s.market_id,m.name market_name,m.region,s.food_id,s.food_name,s.product_id,
        s.period_start,s.observed_on,s.first_reported_on,s.quantity_kg,s.document_id,s.reporting_days
        FROM supply_observation s JOIN market m ON m.id=s.market_id
        WHERE ${where} AND period_start=$${values.length + 1}
        ORDER BY quantity_kg DESC,s.market_id,s.food_id`,
      values: [...values, period],
    }),
  };
}

/** Pick the last reported month inside the requested product and department. */
export function supplyMapQuery(product: string, departments: string[], dateWindow: string) {
  const values: (string | string[])[] = [];
  const conditions = [dateWindow];
  if (product) {
    values.push(product);
    conditions.push(`s.product_id=$${values.length}`);
  }
  if (departments.length) {
    values.push(departments);
    conditions.push(`m.region=ANY($${values.length}::text[])`);
  }
  const where = conditions.join(" AND ");
  return {
    text: `WITH latest_period AS (
      SELECT max(s.period_start) AS period_start
      FROM supply_observation s JOIN market m ON m.id=s.market_id
      WHERE ${where}
    )
    SELECT m.id,m.name,m.region,u.department_id,u.latitude,u.longitude,
      sum(s.quantity_kg) AS value,max(s.observed_on) AS date,'kg' AS unit,
      s.period_start::text AS period_start,
      jsonb_agg(DISTINCT jsonb_build_object('document_id',s.document_id,'title',d.title)) AS sources
    FROM supply_observation s JOIN market m ON m.id=s.market_id
      JOIN municipality u ON u.id=m.municipality_id
      JOIN latest_period p ON p.period_start=s.period_start
      LEFT JOIN source_document d ON d.id=s.document_id
    WHERE ${where}
    GROUP BY m.id,u.id,s.period_start ORDER BY m.id`,
    values,
  };
}
