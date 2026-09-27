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
