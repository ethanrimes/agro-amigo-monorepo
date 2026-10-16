import "server-only";
import { database } from "./db";

const OLD_MILK_MARKET = "finca-bolivar-san-juan-nepomu-ceno";
const CANONICAL_MILK_MARKET = "finca-bolivar-san-juan-nepomuceno";
const MILK_ORIGINALS = [
  "a8e27086128ff3f2a3c67147dfa6782a947a6e3ad6c94b52af4c2d3537d1ab63",
  "4cf84658353b236e022d39c737e16975d94e22e5cde92dd96f308d3e042f6e0e",
];
const PDF_NATIVE_LOCATOR = "PDF page 5,col 2,line 18; parser milk-pdf-v12";
const XLS_WINNER_LOCATOR = "Precios leche en finca!row 53; precio en finca, COP/litro";

// Independent retained originals: PDF p5 prints rounded whole pesos, while
// the official coded annex row53 retains the more precise mean. Every field
// is a literal control from these two exact June/July source pairs.
const MILK_PAIRED_WINNERS = [
  [MILK_ORIGINALS[0], "4175c659c2c17c9119e2ce280afa9a2b57b9b9a420dff96abfa7802866eab74a", "2022-06-30", 1295, 1295.23, 1200, 1400],
  [MILK_ORIGINALS[1], "4ad00cdf760af47806e5f1abe1c386e5d02262dea02a354fe510aa2888bd8ae9", "2022-07-31", 1328, 1328.12, 1200, 1500],
] as const;

/** Resolve only a source-proven historical milk municipality bookmark. */
export async function resolveMarketAlias(
  db: ReturnType<typeof database>, id: string,
): Promise<string> {
  if (id !== OLD_MILK_MARKET) return id;
  const { rows } = await db.query<{ market_id: string }>(`
    WITH verified_pair(pdf_sha,xls_sha,observed_on,pdf_price,xls_price,min_price,max_price) AS (
      VALUES ($3::text,$4::text,$5::date,$6::numeric,$7::numeric,$8::numeric,$9::numeric),
             ($10::text,$11::text,$12::date,$13::numeric,$14::numeric,$15::numeric,$16::numeric)
    )
    SELECT DISTINCT candidate.market_id FROM (
    SELECT corrected.market_id
    FROM price_observation_review review
    JOIN price_observation old ON old.document_id=review.document_id
      AND old.source_locator=review.source_locator
      AND old.product_id=review.product_id AND old.market_id=review.market_id
      AND old.source_id=review.source_id AND old.observed_on=review.observed_on
      AND old.period=review.period AND old.unit=review.unit
    JOIN published_price_observation corrected
      ON corrected.document_id=review.document_id
      AND corrected.product_id=review.product_id
      AND corrected.source_id=review.source_id
      AND corrected.observed_on=review.observed_on
      AND corrected.period=review.period AND corrected.unit=review.unit
      AND corrected.source_locator=review.evidence->>'corrected_source_locator'
      AND corrected.price=old.price AND corrected.min_price=old.min_price
      AND corrected.max_price=old.max_price
    WHERE review.market_id=$1
      AND review.document_id=ANY($2::text[])
      AND review.reason='Verified DANE milk line-wrap municipality alias'
      AND review.source_id='dane-milk-farm'
      AND review.unit='litre' AND review.period='monthly'
      AND review.source_locator='PDF page 5,col 2,line 19; precio en finca, COP/litro'
      AND review.evidence->>'source_sha256'=review.document_id
      AND review.evidence->>'canonical_municipality'='San Juan Nepomuceno'
      AND review.evidence->>'original_retained'='true'
    UNION ALL
    SELECT winner.market_id
    FROM verified_pair pair
    JOIN price_observation_review review
      ON review.document_id=pair.pdf_sha
     AND review.observed_on=pair.observed_on
    JOIN price_observation old ON old.document_id=review.document_id
      AND old.source_locator=review.source_locator
      AND old.product_id=review.product_id AND old.market_id=review.market_id
      AND old.source_id=review.source_id AND old.observed_on=review.observed_on
      AND old.period=review.period AND old.unit=review.unit
    JOIN historical_price native ON native.document_id=pair.pdf_sha
      AND native.source_locator=$17
      AND native.series='dane-milk-farm'
      AND native.observed_on=pair.observed_on
      AND native.price=pair.pdf_price
      AND native.details->>'source_sha256'=pair.pdf_sha
      AND native.details->>'literal_municipality'='San Juan Nepomu- ceno'
      AND native.details->>'literal_source_locator'='PDF page 5,col 2,line 17-19'
      AND native.details->>'department'='Bolívar'
      AND native.details->>'municipality'='San Juan Nepomuceno'
      AND (native.details->>'min_price')::numeric=pair.min_price
      AND (native.details->>'max_price')::numeric=pair.max_price
    JOIN published_price_observation winner
      ON winner.document_id=pair.xls_sha
      AND winner.product_id=old.product_id
      AND winner.source_id=old.source_id
      AND winner.observed_on=pair.observed_on
      AND winner.period=old.period AND winner.unit=old.unit
      AND winner.market_id=$18
      AND winner.source_locator=$19
      AND winner.price=pair.xls_price
      AND winner.min_price=pair.min_price
      AND winner.max_price=pair.max_price
    WHERE review.market_id=$1
      AND review.reason='Verified DANE milk line-wrap municipality alias'
      AND review.source_id='dane-milk-farm'
      AND review.unit='litre' AND review.period='monthly'
      AND review.source_locator='PDF page 5,col 2,line 19; precio en finca, COP/litro'
      AND review.evidence->>'source_sha256'=pair.pdf_sha
      AND review.evidence->>'canonical_municipality'='San Juan Nepomuceno'
      AND review.evidence->>'corrected_source_locator'=$17 || '; precio en finca, COP/litro'
      AND review.evidence->>'original_retained'='true'
      AND old.price=pair.pdf_price
      AND old.min_price=pair.min_price AND old.max_price=pair.max_price
      AND native.product_name='Leche cruda en finca'
      AND native.market_name='San Juan Nepomuceno'
      AND native.unit='litre'
    ) candidate
    LIMIT 2`, [id, MILK_ORIGINALS, ...MILK_PAIRED_WINNERS.flat(),
      PDF_NATIVE_LOCATOR, CANONICAL_MILK_MARKET, XLS_WINNER_LOCATOR]);
  return rows.length === 1 && rows[0].market_id === CANONICAL_MILK_MARKET
    ? CANONICAL_MILK_MARKET : id;
}
